import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlsplit

from tools.curation.build_graph import PROJECT, WIKI, open_read_only, classify_node
from tools.curation.review_records import read_receipt, needs_review
from tools.curation.build_wiki import (
    ATTACHMENT_LINK,
    WikiEdition,
    page_header,
    inline_code,
    copy_topics,
    read_classifications,
    rotulo,
    source_text,
)


ATTACHMENT_ID = re.compile(r"zulip-anexo-[0-9a-f]{32}")
TOPIC_ID = re.compile(r"zulip-topico-[0-9a-f]{24}")
CHANNEL_URL = re.compile(r"/(?:channel|stream)/(\d+)(?:-|/)")
HAS_TEXT = {"extraido", "transcrito", "parcial"}
NO_TEXT = {"erro", "indisponivel", "sem_audio", "vazio"}
PER_PAGE = 100
LINK_STATES = "anexos/topicos.json"


def read_downloads(pasta):
    estado = pasta / "estado.sqlite3"
    if not estado.is_file():
        return {}, {}
    with open_read_only(estado) as db:
        db.execute("BEGIN")
        arquivos = {
            url: (chave, mime, tamanho, resumo)
            for url, chave, mime, tamanho, resumo in db.execute(
                "SELECT url, id, mime, bytes, sha256 FROM arquivos WHERE estado='baixado' ORDER BY id"
            )
        }
        referencias = defaultdict(list)
        for url, mid in db.execute(
            "SELECT r.url, r.mensagem_id FROM referencias r JOIN arquivos a ON a.url = r.url "
            "WHERE a.estado='baixado' ORDER BY r.url, r.mensagem_id"
        ):
            referencias[url].append(f"zulip-msg-{mid}")
    return arquivos, referencias


def read_transcripts(pasta):
    caminho = pasta / "transcricoes.sqlite3"
    if not caminho.is_file():
        return {}
    with open_read_only(caminho) as db:
        return {
            (chave, resumo): (estado, texto, metodo, detalhe)
            for chave, resumo, estado, texto, metodo, detalhe in db.execute(
                "SELECT id, sha256, estado, texto, metodo, detalhe FROM transcricoes"
            )
        }


def read_manual_reviews(pasta):
    caminho = pasta / "revisoes-manuais.json"
    registros = json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else []
    if not isinstance(registros, list):
        raise ValueError("Manual reviews must be a list.")
    revisoes = {}
    for numero, registro in enumerate(registros, 1):
        if not isinstance(registro, dict):
            raise ValueError(f'Invalid manual review at position {numero}.')
        chave, resumo = registro.get("id"), registro.get("sha256")
        estado, texto = registro.get("estado"), registro.get("texto")
        metodo, detalhe = registro.get("metodo"), registro.get("detalhe")
        manual = registro.get("manual", True)
        if (not isinstance(chave, str) or not ATTACHMENT_ID.fullmatch(chave)
                or not isinstance(resumo, str) or not re.fullmatch(r"[0-9a-f]{64}", resumo)
                or not isinstance(estado, str) or estado not in HAS_TEXT | NO_TEXT
                or not isinstance(metodo, str) or not metodo.strip()
                or not isinstance(detalhe, str) or not detalhe.strip()
                or not isinstance(manual, bool)):
            raise ValueError(f'Invalid metadata for manual review {numero}.')
        if estado in HAS_TEXT:
            if not isinstance(texto, str) or not texto.strip():
                raise ValueError(f'Manual review at position {numero} has no text.')
        elif texto is not None:
            raise ValueError(f'The review at position {numero} specifies no text but includes a transcript.')
        if (chave, resumo) in revisoes:
            raise ValueError(f'Duplicate manual reviews for {chave}.')
        revisoes[chave, resumo] = (estado, texto, metodo, detalhe), manual
    for caminho in (pasta.parent.parent / "revisao-ocr" / "terra").glob("zulip-anexo-*.json"):
        try:
            item = read_receipt(caminho)
        except (OSError, ValueError) as erro:
            print(f'Skipped review {caminho.name}: {erro}', flush=True)
            continue
        if needs_review(item):
            continue
        revisoes[item["id"], item["sha256"]] = (
            (item["estado"], item["texto"], item["metodo"], item["detalhe"]), True
        )
    return revisoes


def find_message(db, mid):
    linha = db.execute(
        "SELECT l.destino, m.url, c.titulo FROM ligacoes l "
        "JOIN nos m ON m.id = l.origem AND m.tipo='mensagem' "
        "JOIN nos c ON c.id = l.destino AND c.tipo='conversa' "
        "WHERE l.origem=? AND l.relacao='pertence'", (mid,)
    ).fetchone()
    if not linha:
        return None
    chave_topico, url, titulo = linha
    canal = CHANNEL_URL.search(url or "")
    if canal is None or TOPIC_ID.fullmatch(chave_topico) is None:
        return None
    caminho = f"../zulip/canal-{canal[1]}/{chave_topico}.md#{mid}"
    return chave_topico, caminho, titulo


def write_attachment_page(edicao, chave, transcricao, referencias, classificacoes):
    estado, texto, metodo, _ = transcricao
    tem_texto = estado in HAS_TEXT and isinstance(texto, str) and bool(texto.strip())
    do_texto = [(slug, "candidato", trecho) for _, slug, _, trecho in classify_node(chave, texto)] if tem_texto else []
    if tem_texto and metodo and "whisper-local" in metodo and texto.startswith("[Fala transcrita automaticamente]"):
        do_texto.append(("conversacao", "candidato", None))
    do_contexto = [sinal for mid, _, _ in referencias for sinal in classificacoes.get(mid, ())]
    slugs_texto = sorted({slug for slug, _, _ in do_texto})
    slugs_contexto = sorted({slug for slug, _, _ in do_contexto})
    partes = [
        page_header([do_texto, do_contexto], learning_from_text=slugs_texto, learning_from_context=slugs_contexto),
        "[Índice de anexos](index.md) · [Índice local](../index.md)\n\n",
    ]
    if slugs_texto:
        partes.append("Sinais no texto extraído · " + ", ".join(inline_code(slug) for slug in slugs_texto) + "\n\n")
    if slugs_contexto:
        partes.append("Sinais nas mensagens que citam o anexo · " + ", ".join(inline_code(slug) for slug in slugs_contexto) + "\n\n")
    if referencias:
        partes.append("## backlinks\n\n")
        partes.append("".join(f"- [{mid}]({caminho}) · {rotulo(titulo)}\n" for mid, caminho, titulo in referencias) + "\n")
    if tem_texto:
        partes.append("## Content\n\n")
        if estado == "parcial":
            partes.append("Transcrição parcial.\n\n")
        partes.append(source_text(texto))
    edicao.write_page(f"anexos/{chave}.md", "".join(partes))
    return tem_texto


def write_list(edicao, itens, totais):
    paginas = []
    total = len(itens)
    for inicio in range(0, total, PER_PAGE):
        fim = min(inicio + PER_PAGE, total)
        nome = f"pagina-{inicio // PER_PAGE + 1:04d}.md"
        paginas.append(f"- [Anexos {inicio + 1} a {fim}]({nome})\n")
        linhas = [
            "# Anexos locais do Zulip\n\n",
            "[Todas as páginas](index.md) · [Índice local](../index.md)\n\n",
        ]
        linhas.extend(f"- [{rotulo(nome_anexo)}]({chave}.md)\n" for chave, nome_anexo in itens[inicio:fim])
        edicao.write_page(f"anexos/{nome}", "".join(linhas))
    edicao.write_page(
        "anexos/index.md",
        "# Anexos locais do Zulip\n\n[Índice local](../index.md)\n\n"
        f"{total:,} anexos processados nesta edição. "
        f"{totais['anexos_com_texto']:,} têm texto extraído ou fala transcrita.\n\n"
        + (f"{totais['anexos_aguardam_transcricao']:,} arquivos baixados aguardam processamento local.\n\n"
           if totais["anexos_aguardam_transcricao"] else "")
        + "".join(paginas),
    )


def integrate(dados, db, edicao, classificacoes):
    pasta = (dados / "zulip" / "anexos").resolve()
    arquivos, referencias = read_downloads(pasta)
    transcricoes = read_transcripts(pasta)
    revisoes = read_manual_reviews(pasta)
    itens = []
    registros_extracao = {}
    anexos_por_mensagem = defaultdict(list)
    topicos = set()
    localizacoes = {}
    chaves = set()
    totais = {"anexos": 0, "anexos_com_texto": 0, "anexos_referencias": 0,
              "anexos_referencias_pendentes": 0, "anexos_aguardam_transcricao": 0,
              "anexos_revisados_manualmente": 0}
    for url, (chave, mime, tamanho, resumo) in arquivos.items():
        if not isinstance(chave, str) or not ATTACHMENT_ID.fullmatch(chave) or chave in chaves:
            raise ValueError(f'Invalid or duplicate attachment ID: {chave}.')
        chaves.add(chave)
        transcricao, revisao_manual = revisoes.get((chave, resumo), (transcricoes.get((chave, resumo)), False))
        if transcricao is None:
            totais["anexos_aguardam_transcricao"] += 1
            continue
        nome = unquote(urlsplit(url).path.rsplit("/", 1)[-1]).strip() or chave
        mime = mime or "application/octet-stream"
        ligacoes = []
        for mid in referencias.get(url, ()):
            if mid not in localizacoes:
                localizacoes[mid] = find_message(db, mid)
            local = localizacoes[mid]
            if local is None:
                totais["anexos_referencias_pendentes"] += 1
                continue
            topico, backlink, titulo = local
            topicos.add(topico)
            anexos_por_mensagem[mid].append((chave, nome))
            ligacoes.append((mid, backlink, titulo))
        tem_texto = write_attachment_page(edicao, chave, transcricao, ligacoes, classificacoes)
        estado, _, metodo, detalhe = transcricao
        registro = {"name": nome, "mime": mime, "bytes": tamanho, "sha256": resumo,
                    "transcription": estado, "transcription_method": metodo}
        if detalhe:
            registro["note"] = detalhe
        if revisao_manual:
            registro["manual_review"] = True
        registros_extracao[chave] = registro
        itens.append((chave, nome))
        totais["anexos"] += 1
        totais["anexos_com_texto"] += tem_texto
        totais["anexos_revisados_manualmente"] += revisao_manual
        totais["anexos_referencias"] += len(ligacoes)
    write_list(edicao, sorted(itens, key=lambda item: (item[1].casefold(), item[0])), totais)
    edicao.write_page("anexos/extracao.json", json.dumps(registros_extracao, ensure_ascii=False, indent=2) + "\n")
    edicao.write_page(LINK_STATES, json.dumps(sorted(topicos), indent=2) + "\n")
    return anexos_por_mensagem, topicos, totais


def atualizar(dados, grafo, saida):
    edicao = WikiEdition(saida)
    arquivo_manifesto = edicao.pasta / "manifesto.json"
    if not arquivo_manifesto.is_file():
        raise ValueError("Run python -m tools.curation.build_wiki before you add attachments.")
    manifesto = json.loads(arquivo_manifesto.read_text(encoding="utf-8"))
    if manifesto.get("schema_version") != 1:
        raise ValueError("Unknown edition manifest version.")
    estado = dados / "zulip" / "anexos" / "estado.sqlite3"
    if manifesto["totais"].get("anexos") and not estado.is_file():
        raise ValueError("Original attachment database missing. The local edition is available.")
    edicao.arquivos.update(
        (nome, resumo) for nome, resumo in manifesto["arquivos"].items() if not nome.startswith("anexos/")
    )
    anteriores = edicao.pasta / LINK_STATES
    topicos_anteriores = set(json.loads(anteriores.read_text(encoding="utf-8"))) if anteriores.is_file() else set()
    with open_read_only(grafo) as db:
        classificacoes = read_classifications(db)
        anexos, novos, totais = integrate(dados, db, edicao, classificacoes)
        envolvidos = novos | topicos_anteriores
        if envolvidos:
            copy_topics(db, dados, edicao, classificacoes, anexos_por_mensagem=anexos, topicos=envolvidos)
    indice = (edicao.pasta / "index.md").read_text(encoding="utf-8")
    if ATTACHMENT_LINK not in indice:
        destino = "[Grafo SQLite]"
        if destino in indice:
            indice = indice.replace(destino, f"{ATTACHMENT_LINK} · {destino}", 1)
        else:
            indice += f"\n{ATTACHMENT_LINK}\n"
        edicao.write_page("index.md", indice)
    totais = {**manifesto["totais"], **totais}
    totais["markdown"] = sum(nome.endswith(".md") for nome in edicao.arquivos)
    edicao.finish(totais)
    return {**totais, "arquivos_escritos": edicao.escritos, "topicos_reprocessados": len(envolvidos)}


def main():
    parser = argparse.ArgumentParser(description='Add the attachment pages to the local wiki.')
    parser.add_argument("--data", type=Path, default=PROJECT / "dados")
    parser.add_argument("--graph", type=Path)
    args = parser.parse_args()
    dados = args.data.resolve()
    saida = WIKI / "local"
    grafo = (args.graph or saida / "grafo.sqlite3").resolve()
    try:
        resultado = atualizar(dados, grafo, saida)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
