import argparse
from collections import defaultdict
import hashlib
from itertools import groupby
import json
from pathlib import Path
import re
import shutil
import sqlite3
from tempfile import NamedTemporaryFile
from urllib.parse import quote, urlsplit

from tools.curation.build_graph import PROJECT, SITUATIONS, TOPICS, WIKI, open_read_only

from edition import file_hash, verify


DOIST_HOSTS = {"async.twist.com", "twist.com", "www.todoist.com"}
ZULIP_HOSTS = {"chat.zulip.org"}
RASTER = {".png", ".jpg", ".jpeg", ".webp"}
MARKER = "workplace-english-practice-local-v1"
ATTACHMENT_LINK = "[Anexos locais do Zulip](anexos/index.md)"
LEARNING_USES = {**TOPICS, **SITUATIONS}
MARKDOWN_ESCAPE = re.compile(r"_|[^ \w,.’–—]")
FENCES = re.compile(r"\x60+")
URL_CONTROL = re.compile(r"[\s\x00-\x1f\x7f-\x9f]")


def rotulo(texto):
    plano = " ".join(texto.split())
    return MARKDOWN_ESCAPE.sub(lambda char: f"&#{ord(char[0])};", plano)


def cerca(texto, minimo=3):
    return "\x60" * max(minimo, 1 + max((len(item[0]) for item in FENCES.finditer(texto)), default=0))


def source_text(texto):
    bloqueio = cerca(texto)
    quebra = "" if texto.endswith("\n") else "\n"
    return f"{bloqueio}text\n{texto}{quebra}{bloqueio}\n\n"


def inline_code(texto):
    linha = " ".join(texto.split())
    bloqueio = cerca(linha, minimo=1)
    return f"{bloqueio} {linha} {bloqueio}"


def source_link(url, hosts, texto):
    if not url or URL_CONTROL.search(url):
        return ""
    try:
        partes = urlsplit(url)
    except ValueError:
        return ""
    if partes.scheme != "https" or partes.netloc not in hosts:
        return ""
    uri = quote(url, safe=":/?#@!$&'()*+,;=%-._~")
    return f"[{texto}](<{uri}>)"


def page_header(ligacoes, **aprendizagem):
    slugs = {slug for grupo in ligacoes for slug, _, _ in grupo}
    valores = {"learning_uses": sorted(slugs) or ["leitura-contextual"], **aprendizagem}
    return "---\n" + "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in valores.items()) + "---\n\n"


def read_classifications(db):
    por_id = defaultdict(list)
    for origem, destino, relacao, trecho in db.execute(
        "SELECT origem, destino, relacao, trecho FROM ligacoes WHERE relacao IN ('candidato', 'curado')"
    ):
        if destino in LEARNING_USES:
            por_id[origem].append((destino, relacao, trecho))
    return por_id


def extract_summary(fontes, ligacoes):
    por_sinal = defaultdict(list)
    for fonte, grupo in zip(fontes, ligacoes, strict=True):
        for slug, relacao, trecho in grupo:
            if relacao == "candidato" and trecho and trecho not in {item[1] for item in por_sinal[slug]}:
                if len(por_sinal[slug]) < 2:
                    por_sinal[slug].append((fonte, trecho))
    if not por_sinal:
        return ""
    linhas = ["## Sinais de inglês", ""]
    for slug in sorted(por_sinal):
        exemplos = []
        for fonte, trecho in por_sinal[slug]:
            literal = inline_code(trecho)
            exemplos.append(f"{literal} ([{fonte}](#{fonte}))" if fonte else literal)
        linhas.append(f"- **{LEARNING_USES[slug]}** · " + " · ".join(exemplos))
    return "\n".join(linhas) + "\n\n"


class WikiEdition:
    def __init__(self, pasta):
        if pasta.is_symlink() or (pasta.exists() and not pasta.is_dir()):
            raise ValueError("Select a real directory for the edition.")
        pasta.mkdir(parents=True, exist_ok=True)
        self.pasta = pasta.resolve()
        marca = self.pasta / ".edicao-local"
        if marca.exists():
            if marca.is_symlink() or marca.read_text(encoding="utf-8").strip() != MARKER:
                raise ValueError("Unknown local edition marker.")
        elif any(self.pasta.iterdir()):
            raise ValueError("The edition directory contains files from another process.")
        else:
            marca.write_text(MARKER + "\n", encoding="utf-8")
        self.arquivos = {}
        self.diretorios = {self.pasta}
        self.escritos = 0

    def destino(self, caminho):
        destino = self.pasta / caminho
        if destino.parent not in self.diretorios:
            if not destino.parent.resolve().is_relative_to(self.pasta):
                raise ValueError("The edition path is outside the local directory.")
            destino.parent.mkdir(parents=True, exist_ok=True)
            self.diretorios.add(destino.parent)
        if destino.is_symlink():
            raise ValueError("The edition path contains a symbolic link.")
        return destino

    def store_file(self, destino, write_file):
        with NamedTemporaryFile(dir=destino.parent, delete=False) as arquivo:
            temporario = Path(arquivo.name)
        try:
            write_file(temporario)
            temporario.replace(destino)
        finally:
            temporario.unlink(missing_ok=True)
        self.escritos += 1

    def write_page(self, caminho, valor):
        destino = self.destino(caminho)
        dados = valor.encode("utf-8") if isinstance(valor, str) else valor
        if not destino.is_file() or destino.read_bytes() != dados:
            self.store_file(destino, lambda arquivo: arquivo.write_bytes(dados))
        self.arquivos[caminho] = hashlib.sha256(dados).hexdigest()

    def copiar(self, caminho, origem):
        destino = self.destino(caminho)
        resumo = file_hash(origem)
        if not destino.is_file() or file_hash(destino) != resumo:
            self.store_file(destino, lambda arquivo: shutil.copyfile(origem, arquivo))
        self.arquivos[caminho] = resumo

    def finish(self, totais):
        manifesto = {"schema_version": 1, "totais": totais, "arquivos": self.arquivos.copy()}
        self.write_page("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def copy_images(db, dados, edicao, classificacoes):
    paginas = []
    temas = defaultdict(list)
    caminho_sinais = WIKI / "sinais-doist.json"
    sinais = json.loads(caminho_sinais.read_text(encoding="utf-8-sig")) if caminho_sinais.is_file() else {}
    for chave, titulo, url, caminho, texto, estado in db.execute(
        "SELECT id, titulo, url, caminho, texto, estado FROM nos WHERE tipo='captura' ORDER BY id"
    ):
        if not re.fullmatch(r"doist-[a-z0-9-]+", chave) or not caminho:
            raise ValueError(f'The graph has no valid local path for image {chave}.')
        imagem = (dados / caminho).resolve()
        if not imagem.is_relative_to(dados) or imagem.suffix.lower() not in RASTER or not imagem.is_file():
            raise ValueError(f'Source image unavailable for {chave}.')
        if estado not in {"extraido", "parcial", "vazio"} or (estado != "vazio" and not texto):
            raise ValueError(f'OCR unavailable for {chave}.')
        nome_imagem = chave + imagem.suffix.lower()
        edicao.copiar(f"doist/imagens/{nome_imagem}", imagem)
        rotulos_ocr = [(slug, "ocr-catalogo", None) for slug in sinais.get(chave, []) if slug in LEARNING_USES]
        grupo = [classificacoes.get(chave, []) + rotulos_ocr]
        original = source_link(url, DOIST_HOSTS, "Publicação original")
        partes = [
            page_header(grupo),
            f"# {rotulo(titulo)}\n\n",
            " · ".join(filter(None, ("[Índice local](../index.md)", "[Capturas Doist](index.md)", original))) + "\n\n",
            f"![Captura Doist](imagens/{nome_imagem})\n\n",
            extract_summary([None], grupo),
        ]
        if texto:
            partes.append("## Content\n\n")
            if estado == "parcial":
                partes.append("Transcrição parcial.\n\n")
            partes.append(source_text(texto))
        edicao.write_page(f"doist/{chave}.md", "".join(partes))
        paginas.append(f"- [{rotulo(titulo)}]({chave}.md)")
        for slug in {slug for slug, _, _ in grupo[0]}:
            temas[slug].append((titulo, chave))
    edicao.write_page("doist/index.md", "# Capturas Doist\n\n[Índice local](../index.md)\n\n" + "\n".join(paginas) + "\n")
    return len(paginas), temas


def read_messages(db, dados, topicos=None):
    bancos = []
    for nome, pasta in (("completo", "zulip"), ("piloto", "zulip-piloto")):
        caminho = dados / pasta / "coleta.sqlite3"
        if caminho.is_file():
            db.execute(f"ATTACH DATABASE ? AS {nome}", (caminho.as_uri() + "?mode=ro",))
            bancos.append(nome)
    colunas = ("stream_id", "channel", "topic", "sender_full_name", "datetime_utc")
    if len(bancos) == 2:
        campos = ", ".join(f"COALESCE(completo.{coluna}, piloto.{coluna})" for coluna in colunas)
    elif bancos:
        campos = ", ".join(f"{bancos[0]}.{coluna}" for coluna in colunas)
    else:
        campos = ", ".join("NULL" for _ in colunas)
    joins = "\n".join(f"LEFT JOIN {nome}.mensagens AS {nome} ON {nome}.id = m.ordem" for nome in bancos)
    ligacoes = "ligacoes l"
    if topicos is not None:
        db.execute("CREATE TEMP TABLE topicos_selecionados (id TEXT PRIMARY KEY) WITHOUT ROWID")
        db.executemany("INSERT INTO topicos_selecionados VALUES (?)", ((chave,) for chave in topicos))
        ligacoes = "topicos_selecionados t CROSS JOIN ligacoes l ON l.destino = t.id"
    return db.execute(f"""
        SELECT l.destino, m.ordem, m.texto, m.url, c.titulo, c.url, {campos}
        FROM {ligacoes} CROSS JOIN nos m ON m.id = l.origem AND m.tipo = 'mensagem'
        CROSS JOIN nos c ON c.id = l.destino AND c.tipo = 'conversa'
        {joins}
        WHERE l.relacao = 'pertence'
        ORDER BY l.destino
    """)


def copy_topics(db, dados, edicao, classificacoes, *, anexos_por_mensagem=None, topicos=None):
    canais = defaultdict(list)
    total = 0
    anexos_por_mensagem = anexos_por_mensagem or {}
    consultas = groupby(read_messages(db, dados, topicos), key=lambda linha: linha[0])
    for indice, (chave, linhas) in enumerate(consultas, start=1):
        if not re.fullmatch(r"zulip-topico-[0-9a-f]{24}", chave):
            raise ValueError(f'Unexpected topic ID in the graph: {chave}.')
        mensagens = sorted(linhas, key=lambda linha: linha[1])
        _, primeiro_id, _, link_mensagem, titulo, url, canal_id, canal, topico, _, _ = mensagens[0]
        if canal_id is None:
            match = re.search(r"/(?:channel|stream)/(\d+)(?:-|/)", link_mensagem)
            if match is None:
                raise ValueError(f'Unknown channel for message {primeiro_id}.')
            canal_id = int(match[1])
            canal, _, topico = titulo.partition(" · ")
        topico = topico or "Sem tópico"
        fontes = [f"zulip-msg-{linha[1]}" for linha in mensagens]
        grupos = [classificacoes.get(fonte, []) for fonte in fontes]
        rotulos_mensagem = {fonte: sorted({slug for slug, _, _ in grupo})
                            for fonte, grupo in zip(fontes, grupos, strict=True) if grupo}
        sinais = {}
        original = source_link(url, ZULIP_HOSTS, "Discussão no Zulip")
        partes = [
            page_header(grupos, message_learning_default="leitura-contextual", learning_by_message=rotulos_mensagem),
            f"# {rotulo(topico)}\n\n",
            " · ".join(filter(None, ("[Índice local](../../index.md)", f"[{rotulo(canal)}](index.md)", original))) + "\n\n",
            extract_summary(fontes, grupos),
        ]
        dia_anterior = None
        for fonte, linha in zip(fontes, mensagens, strict=True):
            _, _, texto, _, _, _, _, _, _, autor, data = linha
            partes.append(f"## {fonte}\n\n")
            dia = data.partition("T")[0] if data else None
            assinatura = [rotulo(autor)] if autor else []
            if dia and dia != dia_anterior:
                assinatura.append(rotulo(dia))
            dia_anterior = dia
            if assinatura:
                partes.append(" · ".join(assinatura) + "\n\n")
            for slug in rotulos_mensagem.get(fonte, ()):
                sinais.setdefault(slug, fonte)
            partes.append(source_text(texto))
            anexos = anexos_por_mensagem.get(fonte, ())
            if anexos:
                links = " · ".join(f"[{rotulo(nome)}](../../anexos/{identificador}.md)" for identificador, nome in anexos)
                partes.append(f"Anexos locais · {links}\n\n")
        edicao.write_page(f"zulip/canal-{canal_id}/{chave}.md", "".join(partes))
        canais[canal_id].append((topico, chave, len(mensagens), canal, mensagens[-1][1], sinais))
        total += len(mensagens)
        if indice % 5000 == 0:
            print(f'{indice:,} topics and {total:,} messages in Markdown', flush=True)
    return canais, total


def write_indices(edicao, canais, mensagens, capturas):
    canais_raiz = []
    for canal_id, topicos in canais.items():
        canal = max(topicos, key=lambda item: item[4])[3]
        total = sum(item[2] for item in topicos)
        linhas = [f"# {rotulo(canal)}\n\n", "[Índice local](../../index.md)\n\n"]
        linhas.extend(f"- [{rotulo(topico)}]({chave}.md) · {quantidade} mensagens\n"
                      for topico, chave, quantidade, _, _, _ in sorted(topicos, key=lambda item: item[0].casefold()))
        edicao.write_page(f"zulip/canal-{canal_id}/index.md", "".join(linhas))
        canais_raiz.append((canal.casefold(), f"- [{rotulo(canal)}](zulip/canal-{canal_id}/index.md) · "
                                          f"{len(topicos)} tópicos · {total} mensagens\n"))
    topicos = sum(map(len, canais.values()))
    introducao = (
        "# Edição local do acervo\n\n[Índice de estudo](../index.md)\n\n"
        f"Esta edição contém {mensagens:,} mensagens coletadas, {topicos:,} tópicos e {capturas} capturas "
        "com OCR. O conteúdo, as imagens e a navegação estão dentro da wiki. Os links externos indicam a origem.\n\n"
        "As mensagens do Zulip mantêm o texto integral da coleta, incluindo citações, Markdown e referências a anexos, "
        "em blocos de texto. Consulte a imagem ao usar o OCR da Doist.\n\n"
        f"[Ver as {capturas} capturas da Doist](doist/index.md) · [Procurar por tema ou situação](temas/index.md) · "
        f"{ATTACHMENT_LINK} · "
        "[Grafo SQLite](grafo.sqlite3) · "
        "[Manifesto de integridade](manifesto.json)\n\n"
        "## Canais públicos do Zulip\n\n"
    )
    edicao.write_page("index.md", introducao + "".join(linha for _, linha in sorted(canais_raiz)))
    return {"canais": len(canais), "topicos": topicos, "mensagens": mensagens, "capturas": capturas}


def write_topic_indices(edicao, canais, capturas_por_tema):
    topicos_por_tema = defaultdict(lambda: defaultdict(list))
    nomes_canais = {}
    for canal_id, topicos in canais.items():
        nomes_canais[canal_id] = max(topicos, key=lambda item: item[4])[3]
        for topico, chave, _, _, _, sinais in topicos:
            for slug, fonte in sinais.items():
                topicos_por_tema[slug][canal_id].append((topico, chave, fonte))

    indice = [
        "# Temas e situações no acervo\n\n[Índice local](../index.md)\n\n",
        "As páginas incluem tópicos com sinais automáticos ou com exemplos conferidos. "
        "Para leitura contextual de toda a coleta, abra um canal no índice local.\n\n",
    ]
    for slug, titulo in LEARNING_USES.items():
        topicos_por_canal = topicos_por_tema[slug]
        capturas = capturas_por_tema.get(slug, [])
        total_topicos = sum(map(len, topicos_por_canal.values()))
        indice.append(f"- [{titulo}]({slug}/index.md) · {total_topicos} tópicos · {len(capturas)} capturas\n")
        estudo = f"../../../{slug}.md" if slug in TOPICS else f"../../../situacoes.md#{slug}"
        linhas = [
            f"# {titulo}\n\n",
            f"[Temas e situações](../index.md) · [Página de estudo]({estudo})\n\n",
        ]
        if capturas:
            linhas.append("## Capturas Doist\n\n")
            linhas.extend(f"- [{rotulo(nome)}](../../doist/{chave}.md)\n" for nome, chave in capturas)
            linhas.append("\n")
        if topicos_por_canal:
            linhas.append("## Tópicos do Zulip por canal\n\n")
        for canal_id in sorted(topicos_por_canal, key=lambda id_: nomes_canais[id_].casefold()):
            canal = rotulo(nomes_canais[canal_id])
            topicos = sorted(topicos_por_canal[canal_id], key=lambda item: item[0].casefold())
            paginas = []
            for posicao in range(0, len(topicos), 250):
                numero = posicao // 250 + 1
                caminho = f"canal-{canal_id}-{numero}.md"
                paginas.append(f"[{numero}]({caminho})")
                ancora = f"# {titulo} no canal {canal}\n\n"
                nav = f"[{titulo}](index.md) · [Todos os tópicos do canal](../../zulip/canal-{canal_id}/index.md)\n\n"
                lista = "".join(f"- [{rotulo(topico)}](../../zulip/canal-{canal_id}/{chave}.md#{fonte})\n"
                                for topico, chave, fonte in topicos[posicao:posicao + 250])
                edicao.write_page(f"temas/{slug}/{caminho}", ancora + nav + lista)
            linhas.append(f"- {canal} · {len(topicos)} tópicos · " + " ".join(paginas) + "\n")
        if not capturas and not topicos_por_canal:
            linhas.append("Nenhum exemplo classificado neste recorte.\n")
        edicao.write_page(f"temas/{slug}/index.md", "".join(linhas))
    edicao.write_page("temas/index.md", "".join(indice))


def ingest(dados, grafo, saida):
    from tools.curation.build_attachments import integrate

    edicao = WikiEdition(saida)
    with open_read_only(grafo) as db:
        classificacoes = read_classifications(db)
        capturas, capturas_por_tema = copy_images(db, dados, edicao, classificacoes)
        anexos, _, totais_anexos = integrate(dados, db, edicao, classificacoes)
        canais, mensagens = copy_topics(db, dados, edicao, classificacoes, anexos_por_mensagem=anexos)
        esperadas = db.execute("SELECT count(*) FROM nos WHERE tipo='mensagem'").fetchone()[0]
        if mensagens != esperadas:
            raise ValueError(f'Wrote {mensagens} of {esperadas} graph messages.')
        edicao.copiar("grafo.sqlite3", grafo)
    totais = write_indices(edicao, canais, mensagens, capturas)
    totais.update(totais_anexos)
    write_topic_indices(edicao, canais, capturas_por_tema)
    totais["markdown"] = sum(caminho.endswith(".md") for caminho in edicao.arquivos)
    totais["imagens"] = capturas
    edicao.finish(totais)
    return {**totais, "arquivos_escritos": edicao.escritos}


def main():
    parser = argparse.ArgumentParser(description='Build or verify the local wiki from the sources.')
    parser.add_argument("--data", type=Path, default=PROJECT / "dados")
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--verify", action="store_true", help="Verify the generated edition without the original collection.")
    args = parser.parse_args()
    dados = args.data.resolve()
    grafo = (args.graph or dados / "wiki" / "grafo.sqlite3").resolve()
    saida = WIKI / "local"
    try:
        totais = verify(saida.resolve()) if args.verify else ingest(dados, grafo, saida)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(totais, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
