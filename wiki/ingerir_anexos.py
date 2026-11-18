"""Materializa anexos públicos do Zulip na edição local da wiki."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlsplit

from construir_grafo import PROJETO, WIKI, abrir_leitura, classificar_no
from recibos_ocr import ler_recibo, precisa_releitura
from ingerir_acervo import (
    LINK_ANEXOS,
    Edicao,
    cabecalho,
    codigo_inline,
    copiar_topicos,
    ler_classificacoes,
    rotulo,
    texto_original,
)


ID_ANEXO = re.compile(r"zulip-anexo-[0-9a-f]{32}")
ID_TOPICO = re.compile(r"zulip-topico-[0-9a-f]{24}")
CANAL_URL = re.compile(r"/(?:channel|stream)/(\d+)(?:-|/)")
TEXTO_DISPONIVEL = {"extraido", "transcrito", "parcial"}
SEM_TEXTO = {"erro", "indisponivel", "sem_audio", "vazio"}
POR_PAGINA = 100
ESTADO_LIGACOES = "anexos/topicos.json"


def ler_downloads(pasta):
    estado = pasta / "estado.sqlite3"
    if not estado.is_file():
        return {}, {}
    with abrir_leitura(estado) as db:
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


def ler_transcricoes(pasta):
    caminho = pasta / "transcricoes.sqlite3"
    if not caminho.is_file():
        return {}
    with abrir_leitura(caminho) as db:
        return {
            (chave, resumo): (estado, texto, metodo, detalhe)
            for chave, resumo, estado, texto, metodo, detalhe in db.execute(
                "SELECT id, sha256, estado, texto, metodo, detalhe FROM transcricoes"
            )
        }


def ler_revisoes_manuais(pasta):
    caminho = pasta / "revisoes-manuais.json"
    registros = json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else []
    if not isinstance(registros, list):
        raise ValueError("As revisões manuais precisam estar em uma lista.")
    revisoes = {}
    for numero, registro in enumerate(registros, 1):
        if not isinstance(registro, dict):
            raise ValueError(f"Revisão manual inválida na posição {numero}.")
        chave, resumo = registro.get("id"), registro.get("sha256")
        estado, texto = registro.get("estado"), registro.get("texto")
        metodo, detalhe = registro.get("metodo"), registro.get("detalhe")
        manual = registro.get("manual", True)
        if (not isinstance(chave, str) or not ID_ANEXO.fullmatch(chave)
                or not isinstance(resumo, str) or not re.fullmatch(r"[0-9a-f]{64}", resumo)
                or not isinstance(estado, str) or estado not in TEXTO_DISPONIVEL | SEM_TEXTO
                or not isinstance(metodo, str) or not metodo.strip()
                or not isinstance(detalhe, str) or not detalhe.strip()
                or not isinstance(manual, bool)):
            raise ValueError(f"Metadados inválidos na revisão manual {numero}.")
        if estado in TEXTO_DISPONIVEL:
            if not isinstance(texto, str) or not texto.strip():
                raise ValueError(f"Revisão manual sem texto na posição {numero}.")
        elif texto is not None:
            raise ValueError(f"Estado sem texto possui transcrição na revisão manual {numero}.")
        if (chave, resumo) in revisoes:
            raise ValueError(f"Revisões manuais repetidas para {chave}.")
        revisoes[chave, resumo] = (estado, texto, metodo, detalhe), manual
    for caminho in (pasta.parent.parent / "revisao-ocr" / "terra").glob("zulip-anexo-*.json"):
        try:
            item = ler_recibo(caminho)
        except (OSError, ValueError) as erro:
            print(f"Revisão ignorada: {caminho.name}: {erro}", flush=True)
            continue
        if precisa_releitura(item):
            continue
        revisoes[item["id"], item["sha256"]] = (
            (item["estado"], item["texto"], item["metodo"], item["detalhe"]), True
        )
    return revisoes


def localizar_mensagem(db, mid):
    linha = db.execute(
        "SELECT l.destino, m.url, c.titulo FROM ligacoes l "
        "JOIN nos m ON m.id = l.origem AND m.tipo='mensagem' "
        "JOIN nos c ON c.id = l.destino AND c.tipo='conversa' "
        "WHERE l.origem=? AND l.relacao='pertence'", (mid,)
    ).fetchone()
    if not linha:
        return None
    chave_topico, url, titulo = linha
    canal = CANAL_URL.search(url or "")
    if canal is None or ID_TOPICO.fullmatch(chave_topico) is None:
        return None
    caminho = f"../zulip/canal-{canal[1]}/{chave_topico}.md#{mid}"
    return chave_topico, caminho, titulo


def escrever_pagina(edicao, chave, transcricao, referencias, classificacoes):
    estado, texto, metodo, _ = transcricao
    tem_texto = estado in TEXTO_DISPONIVEL and isinstance(texto, str) and bool(texto.strip())
    do_texto = [(slug, "candidato", trecho) for _, slug, _, trecho in classificar_no(chave, texto)] if tem_texto else []
    if tem_texto and metodo and "whisper-local" in metodo and texto.startswith("[Fala transcrita automaticamente]"):
        do_texto.append(("conversacao", "candidato", None))
    do_contexto = [sinal for mid, _, _ in referencias for sinal in classificacoes.get(mid, ())]
    slugs_texto = sorted({slug for slug, _, _ in do_texto})
    slugs_contexto = sorted({slug for slug, _, _ in do_contexto})
    partes = [
        cabecalho([do_texto, do_contexto], learning_from_text=slugs_texto, learning_from_context=slugs_contexto),
        "[Índice de anexos](index.md) · [Índice local](../index.md)\n\n",
    ]
    if slugs_texto:
        partes.append("Sinais no texto extraído · " + ", ".join(codigo_inline(slug) for slug in slugs_texto) + "\n\n")
    if slugs_contexto:
        partes.append("Sinais nas mensagens que citam o anexo · " + ", ".join(codigo_inline(slug) for slug in slugs_contexto) + "\n\n")
    if referencias:
        partes.append("## backlinks\n\n")
        partes.append("".join(f"- [{mid}]({caminho}) · {rotulo(titulo)}\n" for mid, caminho, titulo in referencias) + "\n")
    if tem_texto:
        partes.append("## Content\n\n")
        if estado == "parcial":
            partes.append("Transcrição parcial.\n\n")
        partes.append(texto_original(texto))
    edicao.escrever(f"anexos/{chave}.md", "".join(partes))
    return tem_texto


def escrever_lista(edicao, itens, totais):
    paginas = []
    total = len(itens)
    for inicio in range(0, total, POR_PAGINA):
        fim = min(inicio + POR_PAGINA, total)
        nome = f"pagina-{inicio // POR_PAGINA + 1:04d}.md"
        paginas.append(f"- [Anexos {inicio + 1} a {fim}]({nome})\n")
        linhas = [
            "# Anexos locais do Zulip\n\n",
            "[Todas as páginas](index.md) · [Índice local](../index.md)\n\n",
        ]
        linhas.extend(f"- [{rotulo(nome_anexo)}]({chave}.md)\n" for chave, nome_anexo in itens[inicio:fim])
        edicao.escrever(f"anexos/{nome}", "".join(linhas))
    edicao.escrever(
        "anexos/index.md",
        "# Anexos locais do Zulip\n\n[Índice local](../index.md)\n\n"
        f"{total:,} anexos processados nesta edição. "
        f"{totais['anexos_com_texto']:,} têm texto extraído ou fala transcrita.\n\n"
        + (f"{totais['anexos_aguardam_transcricao']:,} arquivos baixados aguardam processamento local.\n\n"
           if totais["anexos_aguardam_transcricao"] else "")
        + "".join(paginas),
    )


def integrar(dados, db, edicao, classificacoes):
    pasta = (dados / "zulip" / "anexos").resolve()
    arquivos, referencias = ler_downloads(pasta)
    transcricoes = ler_transcricoes(pasta)
    revisoes = ler_revisoes_manuais(pasta)
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
        if not isinstance(chave, str) or not ID_ANEXO.fullmatch(chave) or chave in chaves:
            raise ValueError(f"Identificador de anexo inválido ou repetido: {chave}.")
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
                localizacoes[mid] = localizar_mensagem(db, mid)
            local = localizacoes[mid]
            if local is None:
                totais["anexos_referencias_pendentes"] += 1
                continue
            topico, backlink, titulo = local
            topicos.add(topico)
            anexos_por_mensagem[mid].append((chave, nome))
            ligacoes.append((mid, backlink, titulo))
        tem_texto = escrever_pagina(edicao, chave, transcricao, ligacoes, classificacoes)
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
    escrever_lista(edicao, sorted(itens, key=lambda item: (item[1].casefold(), item[0])), totais)
    edicao.escrever("anexos/extracao.json", json.dumps(registros_extracao, ensure_ascii=False, indent=2) + "\n")
    edicao.escrever(ESTADO_LIGACOES, json.dumps(sorted(topicos), indent=2) + "\n")
    return anexos_por_mensagem, topicos, totais


def atualizar(dados, grafo, saida):
    edicao = Edicao(saida)
    arquivo_manifesto = edicao.pasta / "manifesto.json"
    if not arquivo_manifesto.is_file():
        raise ValueError("Gere a edição local com wiki/ingerir_acervo.py antes do complemento de anexos.")
    manifesto = json.loads(arquivo_manifesto.read_text(encoding="utf-8"))
    if manifesto.get("schema_version") != 1:
        raise ValueError("Versão desconhecida do manifesto da edição.")
    estado = dados / "zulip" / "anexos" / "estado.sqlite3"
    if manifesto["totais"].get("anexos") and not estado.is_file():
        raise ValueError("O banco original de anexos está ausente. A edição local permanece disponível.")
    edicao.arquivos.update(
        (nome, resumo) for nome, resumo in manifesto["arquivos"].items() if not nome.startswith("anexos/")
    )
    anteriores = edicao.pasta / ESTADO_LIGACOES
    topicos_anteriores = set(json.loads(anteriores.read_text(encoding="utf-8"))) if anteriores.is_file() else set()
    with abrir_leitura(grafo) as db:
        classificacoes = ler_classificacoes(db)
        anexos, novos, totais = integrar(dados, db, edicao, classificacoes)
        envolvidos = novos | topicos_anteriores
        if envolvidos:
            copiar_topicos(db, dados, edicao, classificacoes, anexos_por_mensagem=anexos, topicos=envolvidos)
    indice = (edicao.pasta / "index.md").read_text(encoding="utf-8")
    if LINK_ANEXOS not in indice:
        destino = "[Grafo SQLite]"
        if destino in indice:
            indice = indice.replace(destino, f"{LINK_ANEXOS} · {destino}", 1)
        else:
            indice += f"\n{LINK_ANEXOS}\n"
        edicao.escrever("index.md", indice)
    totais = {**manifesto["totais"], **totais}
    totais["markdown"] = sum(nome.endswith(".md") for nome in edicao.arquivos)
    edicao.finalizar(totais)
    return {**totais, "arquivos_escritos": edicao.escritos, "topicos_reprocessados": len(envolvidos)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=PROJETO / "dados")
    parser.add_argument("--grafo", type=Path)
    args = parser.parse_args()
    dados = args.dados.resolve()
    saida = WIKI / "local"
    grafo = (args.grafo or saida / "grafo.sqlite3").resolve()
    try:
        resultado = atualizar(dados, grafo, saida)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
