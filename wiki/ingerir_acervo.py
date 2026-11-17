"""Gera e verifica uma edição local da wiki a partir do grafo e das fontes."""

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

from construir_grafo import PROJETO, SITUACOES, TEMAS, WIKI, abrir_leitura


DOIST_HOSTS = {"async.twist.com", "twist.com", "www.todoist.com"}
ZULIP_HOSTS = {"chat.zulip.org"}
RASTER = {".png", ".jpg", ".jpeg", ".webp"}
MARCA = "workplace-english-practice-local-v1"
RESUMO = {**TEMAS, **SITUACOES}
GRAFIA_MARKDOWN = re.compile(r"_|[^ \w,.’–—]")
CERCAS = re.compile(r"\x60+")
CONTROLE_URL = re.compile(r"[\s\x00-\x1f\x7f-\x9f]")


def rotulo(texto):
    """Protege títulos e nomes vindos da coleta quando usados como Markdown."""
    plano = " ".join(texto.split())
    return GRAFIA_MARKDOWN.sub(lambda char: f"&#{ord(char[0])};", plano)


def cerca(texto, minimo=3):
    return "\x60" * max(minimo, 1 + max((len(item[0]) for item in CERCAS.finditer(texto)), default=0))


def texto_original(texto):
    bloqueio = cerca(texto)
    quebra = "" if texto.endswith("\n") else "\n"
    return f"{bloqueio}text\n{texto}{quebra}{bloqueio}\n\n"


def codigo_inline(texto):
    linha = " ".join(texto.split())
    bloqueio = cerca(linha, minimo=1)
    return f"{bloqueio} {linha} {bloqueio}"


def link_oficial(url, hosts, texto):
    """Só transforma URLs de metadados dos provedores conhecidos em links."""
    if not url or CONTROLE_URL.search(url):
        return ""
    try:
        partes = urlsplit(url)
    except ValueError:
        return ""
    if partes.scheme != "https" or partes.netloc not in hosts:
        return ""
    uri = quote(url, safe=":/?#@!$&'()*+,;=%-._~")
    return f"[{texto}](<{uri}>)"


def cabecalho(kind, identificador, titulo, ligacoes, **metadados):
    slugs = {slug for grupo in ligacoes for slug, _, _ in grupo}
    manual = any(relacao == "curado" for grupo in ligacoes for _, relacao, _ in grupo)
    valores = {
        "kind": kind, "title": titulo, "source_id": identificador,
        "classification": "mixed" if manual else "automatic",
        "learning_uses": sorted(slugs) or ["leitura-contextual"],
        **metadados,
    }
    return "---\n" + "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in valores.items()) + "---\n\n"


def ler_classificacoes(db):
    por_id = defaultdict(list)
    for origem, destino, relacao, trecho in db.execute(
        "SELECT origem, destino, relacao, trecho FROM ligacoes WHERE relacao IN ('candidato', 'curado')"
    ):
        if destino in RESUMO:
            por_id[origem].append((destino, relacao, trecho))
    return por_id


def resumo_extrativo(fontes, ligacoes):
    por_sinal = defaultdict(list)
    for fonte, grupo in zip(fontes, ligacoes, strict=True):
        for slug, relacao, trecho in grupo:
            if relacao == "candidato" and trecho and trecho not in {item[1] for item in por_sinal[slug]}:
                if len(por_sinal[slug]) < 2:
                    por_sinal[slug].append((fonte, trecho))
    if not por_sinal:
        return ""
    linhas = ["## Sinais de inglês", "", "Resumo extrativo automático. Leia o contexto antes de usar os trechos.", ""]
    for slug in sorted(por_sinal):
        exemplos = []
        for fonte, trecho in por_sinal[slug]:
            literal = codigo_inline(trecho)
            exemplos.append(f"{literal} ([{fonte}](#{fonte}))" if fonte else literal)
        linhas.append(f"- **{RESUMO[slug]}** · " + " · ".join(exemplos))
    return "\n".join(linhas) + "\n\n"


def hash_arquivo(caminho):
    with caminho.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


class Edicao:
    def __init__(self, pasta):
        if pasta.is_symlink() or (pasta.exists() and not pasta.is_dir()):
            raise ValueError("Escolha uma pasta local real para a edição.")
        pasta.mkdir(parents=True, exist_ok=True)
        self.pasta = pasta.resolve()
        marca = self.pasta / ".edicao-local"
        if marca.exists():
            if marca.is_symlink() or marca.read_text(encoding="utf-8").strip() != MARCA:
                raise ValueError("Pasta de edição local com identificação desconhecida.")
        elif any(self.pasta.iterdir()):
            raise ValueError("A pasta da edição contém material que não foi gerado pela ingestão.")
        else:
            marca.write_text(MARCA + "\n", encoding="utf-8")
        self.arquivos = {}
        self.diretorios = {self.pasta}
        self.escritos = 0

    def destino(self, caminho):
        destino = self.pasta / caminho
        if destino.parent not in self.diretorios:
            if not destino.parent.resolve().is_relative_to(self.pasta):
                raise ValueError("Caminho da edição fora da pasta local.")
            destino.parent.mkdir(parents=True, exist_ok=True)
            self.diretorios.add(destino.parent)
        if destino.is_symlink():
            raise ValueError("Caminho da edição aponta para um link simbólico.")
        return destino

    def armazenar(self, destino, gravar):
        with NamedTemporaryFile(dir=destino.parent, delete=False) as arquivo:
            temporario = Path(arquivo.name)
        try:
            gravar(temporario)
            temporario.replace(destino)
        finally:
            temporario.unlink(missing_ok=True)
        self.escritos += 1

    def escrever(self, caminho, valor):
        destino = self.destino(caminho)
        dados = valor.encode("utf-8") if isinstance(valor, str) else valor
        if not destino.is_file() or destino.read_bytes() != dados:
            self.armazenar(destino, lambda arquivo: arquivo.write_bytes(dados))
        self.arquivos[caminho] = hashlib.sha256(dados).hexdigest()

    def copiar(self, caminho, origem):
        destino = self.destino(caminho)
        resumo = hash_arquivo(origem)
        if not destino.is_file() or hash_arquivo(destino) != resumo:
            self.armazenar(destino, lambda arquivo: shutil.copyfile(origem, arquivo))
        self.arquivos[caminho] = resumo

    def finalizar(self, totais):
        manifesto = {"schema_version": 1, "totais": totais, "arquivos": self.arquivos.copy()}
        self.escrever("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def copiar_capturas(db, dados, edicao, classificacoes):
    paginas = []
    temas = defaultdict(list)
    caminho_sinais = WIKI / "sinais-doist.json"
    sinais = json.loads(caminho_sinais.read_text(encoding="utf-8-sig")) if caminho_sinais.is_file() else {}
    for chave, titulo, url, caminho, texto, estado in db.execute(
        "SELECT id, titulo, url, caminho, texto, estado FROM nos WHERE tipo='captura' ORDER BY id"
    ):
        if not re.fullmatch(r"doist-[a-z0-9-]+", chave) or not caminho:
            raise ValueError(f"Captura sem caminho local válido no grafo: {chave}.")
        imagem = (dados / caminho).resolve()
        if not imagem.is_relative_to(dados) or imagem.suffix.lower() not in RASTER or not imagem.is_file():
            raise ValueError(f"Imagem indisponível para a captura {chave}.")
        if estado != "extraido" or not texto:
            raise ValueError(f"OCR indisponível para a captura {chave}.")
        nome_imagem = chave + imagem.suffix.lower()
        edicao.copiar(f"doist/imagens/{nome_imagem}", imagem)
        rotulos_ocr = [(slug, "ocr-catalogo", None) for slug in sinais.get(chave, []) if slug in RESUMO]
        grupo = [classificacoes.get(chave, []) + rotulos_ocr]
        original = link_oficial(url, DOIST_HOSTS, "Publicação original")
        partes = [
            cabecalho("capture", chave, titulo, grupo, source="Doist", original_url=url,
                      image=f"imagens/{nome_imagem}", transcription="ocr",
                      **({"additional_evidence": "ocr-catalogue"} if rotulos_ocr else {})),
            f"# {rotulo(titulo)}\n\n",
            "[Índice local](../index.md) · [Capturas Doist](index.md)\n\n",
            f"ID {codigo_inline(chave)}" + (f" · {original}\n\n" if original else "\n\n"),
            f"[Abrir imagem local](imagens/{nome_imagem})\n\n",
            f"![Captura Doist](imagens/{nome_imagem})\n\n",
            resumo_extrativo([None], grupo),
            "## Texto extraído da imagem\n\nOCR automático. Confira nomes, pontuação e formatação na captura.\n\n",
            texto_original(texto),
        ]
        edicao.escrever(f"doist/{chave}.md", "".join(partes))
        paginas.append(f"- [{rotulo(titulo)}]({chave}.md)")
        for slug in {slug for slug, _, _ in grupo[0]}:
            temas[slug].append((titulo, chave))
    edicao.escrever("doist/index.md", "# Capturas Doist\n\n[Índice local](../index.md)\n\n" + "\n".join(paginas) + "\n")
    return len(paginas), temas


def ler_mensagens(db, dados):
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
    return db.execute(f"""
        SELECT l.destino, m.ordem, m.texto, m.url, c.titulo, c.url, {campos}
        FROM ligacoes l CROSS JOIN nos m ON m.id = l.origem AND m.tipo = 'mensagem'
        CROSS JOIN nos c ON c.id = l.destino AND c.tipo = 'conversa'
        {joins}
        WHERE l.relacao = 'pertence'
        ORDER BY l.destino
    """)


def copiar_topicos(db, dados, edicao, classificacoes):
    canais = defaultdict(list)
    total = 0
    for indice, (chave, linhas) in enumerate(groupby(ler_mensagens(db, dados), key=lambda linha: linha[0]), start=1):
        if not re.fullmatch(r"zulip-topico-[0-9a-f]{24}", chave):
            raise ValueError(f"ID de tópico inesperado no grafo: {chave}.")
        mensagens = sorted(linhas, key=lambda linha: linha[1])
        _, primeiro_id, _, link_mensagem, titulo, url, canal_id, canal, topico, _, _ = mensagens[0]
        if canal_id is None:
            match = re.search(r"/(?:channel|stream)/(\d+)(?:-|/)", link_mensagem)
            if match is None:
                raise ValueError(f"Canal não identificado para a mensagem {primeiro_id}.")
            canal_id = int(match[1])
            canal, _, topico = titulo.partition(" · ")
        topico = topico or "Sem tópico"
        fontes = [f"zulip-msg-{linha[1]}" for linha in mensagens]
        grupos = [classificacoes.get(fonte, []) for fonte in fontes]
        rotulos_mensagem = {fonte: sorted({slug for slug, _, _ in grupo})
                            for fonte, grupo in zip(fontes, grupos, strict=True) if grupo}
        sinais = {}
        original = link_oficial(url, ZULIP_HOSTS, "Discussão no Zulip")
        partes = [
            cabecalho("conversation", chave, topico, grupos, source="Zulip",
                      channel_id=canal_id, channel=canal, message_count=len(mensagens), original_url=url,
                      message_learning_default="leitura-contextual", learning_by_message=rotulos_mensagem),
            f"# {rotulo(topico)}\n\n",
            "[Índice local](../../index.md) · [Tópicos deste canal](index.md)\n\n",
            f"Canal {rotulo(canal)} · {len(mensagens)} mensagens" + (f" · {original}\n\n" if original else "\n\n"),
            resumo_extrativo(fontes, grupos),
        ]
        for fonte, linha in zip(fontes, mensagens, strict=True):
            _, _, texto, mensagem_url, _, _, _, _, _, autor, data = linha
            original = link_oficial(mensagem_url, ZULIP_HOSTS, "Mensagem original")
            partes.extend((f"## {fonte}\n\n",
                           " · ".join(filter(None, (rotulo(autor) if autor else "",
                                       rotulo(data) if data else "", original))) + "\n\n"))
            temas = rotulos_mensagem.get(fonte, [])
            if temas:
                partes.append("Sinais de inglês · " + ", ".join(codigo_inline(slug) for slug in temas) + "\n\n")
                for slug in temas:
                    sinais.setdefault(slug, fonte)
            partes.append(texto_original(texto))
        edicao.escrever(f"zulip/canal-{canal_id}/{chave}.md", "".join(partes))
        canais[canal_id].append((topico, chave, len(mensagens), canal, mensagens[-1][1], sinais))
        total += len(mensagens)
        if indice % 5000 == 0:
            print(f"{indice:,} tópicos e {total:,} mensagens em Markdown", flush=True)
    return canais, total


def escrever_indices(edicao, canais, mensagens, capturas):
    canais_raiz = []
    for canal_id, topicos in canais.items():
        canal = max(topicos, key=lambda item: item[4])[3]
        total = sum(item[2] for item in topicos)
        linhas = [f"# {rotulo(canal)}\n\n", "[Índice local](../../index.md)\n\n"]
        linhas.extend(f"- [{rotulo(topico)}]({chave}.md) · {quantidade} mensagens\n"
                      for topico, chave, quantidade, _, _, _ in sorted(topicos, key=lambda item: item[0].casefold()))
        edicao.escrever(f"zulip/canal-{canal_id}/index.md", "".join(linhas))
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
        "[Grafo SQLite](grafo.sqlite3) · "
        "[Manifesto de integridade](manifesto.json)\n\n"
        "## Canais públicos do Zulip\n\n"
    )
    edicao.escrever("index.md", introducao + "".join(linha for _, linha in sorted(canais_raiz)))
    return {"canais": len(canais), "topicos": topicos, "mensagens": mensagens, "capturas": capturas}


def escrever_indices_tematicos(edicao, canais, capturas_por_tema):
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
    for slug, titulo in RESUMO.items():
        topicos_por_canal = topicos_por_tema[slug]
        capturas = capturas_por_tema.get(slug, [])
        total_topicos = sum(map(len, topicos_por_canal.values()))
        indice.append(f"- [{titulo}]({slug}/index.md) · {total_topicos} tópicos · {len(capturas)} capturas\n")
        estudo = f"../../../{slug}.md" if slug in TEMAS else f"../../../situacoes.md#{slug}"
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
                edicao.escrever(f"temas/{slug}/{caminho}", ancora + nav + lista)
            linhas.append(f"- {canal} · {len(topicos)} tópicos · " + " ".join(paginas) + "\n")
        if not capturas and not topicos_por_canal:
            linhas.append("Nenhum exemplo classificado neste recorte.\n")
        edicao.escrever(f"temas/{slug}/index.md", "".join(linhas))
    edicao.escrever("temas/index.md", "".join(indice))


def ingerir(dados, grafo, saida):
    edicao = Edicao(saida)
    with abrir_leitura(grafo) as db:
        classificacoes = ler_classificacoes(db)
        capturas, capturas_por_tema = copiar_capturas(db, dados, edicao, classificacoes)
        canais, mensagens = copiar_topicos(db, dados, edicao, classificacoes)
        esperadas = db.execute("SELECT count(*) FROM nos WHERE tipo='mensagem'").fetchone()[0]
        if mensagens != esperadas:
            raise ValueError(f"Renderizadas {mensagens} de {esperadas} mensagens do grafo.")
        edicao.copiar("grafo.sqlite3", grafo)
    totais = escrever_indices(edicao, canais, mensagens, capturas)
    escrever_indices_tematicos(edicao, canais, capturas_por_tema)
    totais["markdown"] = sum(caminho.endswith(".md") for caminho in edicao.arquivos)
    totais["imagens"] = capturas
    edicao.finalizar(totais)
    return {**totais, "arquivos_escritos": edicao.escritos}


def verificar(pasta):
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    if manifesto.get("schema_version") != 1:
        raise ValueError("Versão desconhecida do manifesto da edição.")
    for nome, resumo in manifesto["arquivos"].items():
        arquivo = (pasta / nome).resolve()
        if not arquivo.is_relative_to(pasta) or hash_arquivo(arquivo) != resumo:
            raise ValueError(f"Arquivo da edição divergente: {nome}.")
    return {**manifesto["totais"], "arquivos_verificados": len(manifesto["arquivos"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=PROJETO / "dados")
    parser.add_argument("--grafo", type=Path)
    parser.add_argument("--verificar", action="store_true", help="verifica a edição gerada sem consultar dados/")
    args = parser.parse_args()
    dados = args.dados.resolve()
    grafo = (args.grafo or dados / "wiki" / "grafo.sqlite3").resolve()
    saida = WIKI / "local"
    try:
        totais = verificar(saida.resolve()) if args.verificar else ingerir(dados, grafo, saida)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(totais, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
