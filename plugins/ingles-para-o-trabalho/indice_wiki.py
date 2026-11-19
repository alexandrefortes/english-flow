import gzip
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3

from consulta_grafo import abrir_leitura


TIPOS = ("mensagem", "topico", "captura", "anexo", "didatica", "indice", "catalogo", "guia")
ESTADOS = ("conferido", "apoio", "sem-uso", "pendente")
CATALOGOS = {
    "fontes.md": "Fontes das conversas",
    "curadoria.json": "Ligações conferidas por ID",
    "sinais-doist.json": "Sinais didáticos das capturas da Doist",
    "local/anexos/extracao.json": "Qualidade e método de transcrição dos anexos",
    "local/anexos/topicos.json": "Tópicos que contêm anexos",
    "local/manifesto.json": "Manifesto de integridade da edição local",
}
DECISOES = "decisoes.tsv.gz"
EXTRACAO = "local/anexos/extracao.json"
GRAFO = "local/grafo.sqlite3"
CONTROLES = {DECISOES, GRAFO, EXTRACAO, "curadoria.json"}
BLOCO = re.compile(r"^(`{3,})text\n(.*?)^\1[ \t]*$", re.M | re.S)
MENSAGEM = re.compile(r"^## (zulip-msg-\d+)\n\n([^\n]*\n\n)?(`{3,})text\n(.*?)^\3[ \t]*$", re.M | re.S)
LINK_MSG = re.compile(r"^- \[(zulip-msg-\d+)\]\(", re.M)
TITULO = re.compile(r"^# (.+)$", re.M)
ORIGEM = re.compile(r"\[(?:Discussão no Zulip|Publicação original)\]\(<(https://[^>]+)>\)")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS paginas (pagina TEXT PRIMARY KEY, versao TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS itens (
 id TEXT PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT NOT NULL, fonte TEXT NOT NULL,
 pagina TEXT NOT NULL, url TEXT, texto TEXT NOT NULL, qualidade TEXT,
 rotulos TEXT NOT NULL, pai TEXT, ordem INTEGER, assinatura TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS por_pagina ON itens(pagina);
CREATE INDEX IF NOT EXISTS por_pai ON itens(pai,ordem);
CREATE INDEX IF NOT EXISTS por_tipo ON itens(tipo);
CREATE TABLE IF NOT EXISTS usos_anexo (id TEXT PRIMARY KEY, do_texto TEXT, do_contexto TEXT);
CREATE TABLE IF NOT EXISTS backlinks (anexo TEXT, mensagem TEXT, PRIMARY KEY(anexo,mensagem)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS por_mensagem ON backlinks(mensagem);
CREATE TABLE IF NOT EXISTS decisoes (id TEXT PRIMARY KEY, tipo TEXT, assinatura TEXT, estado TEXT, motivo TEXT);
CREATE INDEX IF NOT EXISTS por_estado ON decisoes(estado,id);
CREATE TABLE IF NOT EXISTS evidencias (id TEXT, trecho TEXT, funcao TEXT, usos TEXT, PRIMARY KEY(id,trecho));
CREATE VIEW IF NOT EXISTS inventario AS
 SELECT i.*, coalesce(d.estado,'pendente') AS estado,d.motivo FROM itens i
 LEFT JOIN decisoes d ON d.id=i.id AND d.tipo=i.tipo AND d.assinatura=i.assinatura;
"""


def arquivos(pasta, prefixo=""):
    with os.scandir(pasta) as entradas:
        for entrada in entradas:
            nome = prefixo + entrada.name
            if entrada.is_dir(follow_symlinks=False) and not entrada.name.startswith("."):
                yield from arquivos(entrada.path, nome + "/")
            elif (nome in CONTROLES or nome.endswith((".md", ".json"))) and entrada.is_file(follow_symlinks=False):
                s = entrada.stat()
                yield nome, f"{s.st_mtime_ns}/{s.st_ctime_ns}/{s.st_size}"


def rotulos(texto, chave):
    campo = re.search(rf"^{chave}: (.+)$", texto, re.M)
    if not campo:
        return []
    valor = campo[1]
    if valor.startswith("{"):
        return json.loads(valor)
    return [s.strip(' "\'') for s in valor.strip("[]").split(",") if s.strip()]


def rotular(usos):
    return " ".join(sorted(set(usos)))


def assinatura(*campos):
    return hashlib.blake2s("\x00".join(campos).encode(), digest_size=12).hexdigest()


def inserir(db, chave, tipo, titulo, fonte, pagina, *, url=None, texto="", qualidade=None,
            usos=(), pai=None, ordem=None, contexto=""):
    selo = assinatura(titulo, texto, contexto, qualidade or "", url or "")
    db.execute("INSERT INTO itens VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (chave, tipo, titulo, fonte, pagina, url, texto, qualidade, rotular(usos), pai, ordem, selo))


def ler_topico(db, pagina, chave, titulo, url, corpo, usos):
    mensagens = list(MENSAGEM.finditer(corpo))
    por_id = rotulos(corpo.partition("\n---\n")[0], "learning_by_message")
    inserir(db, chave, "topico", titulo, "Zulip", pagina, url=url, usos=usos,
            contexto=assinatura(*(m[0] for m in mensagens)))
    textos = [m[4].removesuffix("\n") for m in mensagens]
    for n, (m, texto) in enumerate(zip(mensagens, textos)):
        numero = int(m[1].removeprefix("zulip-msg-"))
        antes = textos[n-1] if n else ""
        depois = textos[n+1] if n+1 < len(textos) else ""
        inserir(db, m[1], "mensagem", titulo, "Zulip", pagina, pai=chave, ordem=numero,
                texto=texto, usos=por_id.get(m[1], ()) if por_id else (),
                url=f"{url}/near/{numero}" if url else None,
                contexto=assinatura(antes, depois, m[2] or ""))


def pagina_id(pagina):
    return "wiki/" + pagina


def indexar(db, wiki, pagina, extracao, capturas):
    path = wiki / pagina
    if path.suffix == ".json":
        titulo = CATALOGOS.get(pagina, path.stem.replace("-", " "))
        inserir(db, pagina_id(pagina), "catalogo", titulo, "Projeto", pagina, texto=titulo)
        return
    corpo = path.read_text(encoding="utf-8-sig")
    header, separador, corpo_sem_yaml = corpo.removeprefix("---\n").partition("\n---\n")
    if corpo.startswith("---\n") and separador:
        usos = rotulos(header, "learning_uses")
        principal = corpo_sem_yaml
    else:
        usos = []
        principal = corpo
    match = TITULO.search(principal)
    titulo = html.unescape(match[1]) if match else path.stem
    original = ORIGEM.search(principal)
    url = original[1] if original else None
    chave = path.stem
    if chave.startswith("zulip-topico-"):
        ler_topico(db, pagina, chave, titulo, url, corpo, usos)
        return
    if chave.startswith(("zulip-anexo-", "doist-")) and pagina.startswith(("local/anexos/", "local/doist/")):
        bloco = BLOCO.search(principal.partition("\n## Content\n")[2])
        texto = bloco[2].removesuffix("\n") if bloco else ""
        if pagina.startswith("local/doist/"):
            qualidade = capturas.get(chave) or ("parcial" if "Transcrição parcial." in principal else "extraido" if texto else "vazio")
            inserir(db, chave, "captura", titulo, "Doist", pagina, url=url, texto=texto, qualidade=qualidade, usos=usos)
        else:
            info = extracao.get(chave, {})
            db.execute("INSERT INTO usos_anexo VALUES (?,?,?)",
                       (chave, rotular(rotulos(header, "learning_from_text")),
                        rotular(rotulos(header, "learning_from_context"))))
            origens = LINK_MSG.findall(principal.partition("\n## Content\n")[0])
            referencias = [db.execute("SELECT assinatura FROM itens WHERE id=?", (mid,)).fetchone() for mid in origens]
            contexto = " ".join(mid + (ref[0] if ref else "") for mid, ref in zip(origens, referencias))
            inserir(db, chave, "anexo", info.get("name", chave), "Zulip", pagina, texto=texto,
                    qualidade=info.get("transcription"), usos=usos, contexto=contexto)
            db.executemany("INSERT OR IGNORE INTO backlinks VALUES (?,?)", ((chave, mid) for mid in origens))
        return
    if pagina in CATALOGOS:
        tipo = "catalogo"
    elif pagina in {"AGENTS.md", "grafo.md"}:
        tipo = "guia"
    elif pagina.startswith("local/") or path.name == "index.md":
        tipo = "indice"
    else:
        tipo = "didatica"
    fonte = "Doist" if pagina.startswith("local/doist/") else "Zulip" if pagina.startswith(("local/zulip/", "local/anexos/")) else "Projeto"
    inserir(db, pagina_id(pagina), tipo, titulo, fonte, pagina, texto=principal, usos=usos)


def carregar_decisoes(db, wiki):
    db.execute("DELETE FROM decisoes")
    if (wiki / DECISOES).is_file():
        with gzip.open(wiki / DECISOES, "rt", encoding="utf-8") as arq:
            db.executemany("INSERT INTO decisoes VALUES (?,?,?,?,?)",
                           (linha.rstrip("\n").split("\t") for linha in arq))


def carregar_exemplos(db, wiki):
    db.execute("DELETE FROM evidencias")
    if (wiki / "curadoria.json").is_file():
        for chave, exemplos in json.loads((wiki / "curadoria.json").read_bytes()).items():
            for e in exemplos:
                if isinstance(e, dict):
                    db.execute("INSERT INTO evidencias VALUES (?,?,?,?)",
                               (chave, e["trecho"], e["funcao"], rotular(e["usos"])))


def sincronizar(db, wiki):
    db.execute("BEGIN IMMEDIATE")
    atuais = dict(arquivos(wiki))
    anteriores = dict(db.execute("SELECT * FROM paginas"))
    alteradas = {p for p in atuais if anteriores.get(p) != atuais[p]}
    removidas = anteriores.keys() - atuais.keys()
    if EXTRACAO in alteradas or EXTRACAO in removidas:
        alteradas.update(p for p in atuais if p.startswith("local/anexos/zulip-anexo-"))
    if GRAFO in alteradas or GRAFO in removidas:
        alteradas.update(p for p in atuais if p.startswith("local/doist/doist-"))
    if not alteradas and not removidas:
        return
    topicos = [p for p in removidas | alteradas if "/zulip-topico-" in p]
    if topicos:
        db.execute("CREATE TEMP TABLE IF NOT EXISTS topicos_alterados (pagina TEXT PRIMARY KEY)")
        db.execute("DELETE FROM topicos_alterados")
        db.executemany("INSERT OR IGNORE INTO topicos_alterados VALUES (?)", ((p,) for p in topicos))
        alteradas.update(r[0] for r in db.execute("""
            SELECT DISTINCT a.pagina FROM topicos_alterados t JOIN itens m ON m.pagina=t.pagina
            JOIN backlinks b ON b.mensagem=m.id JOIN itens a ON a.id=b.anexo
        """) if r[0] in atuais)
        if anteriores:
            db.execute("CREATE TEMP TABLE IF NOT EXISTS mensagens_alteradas (id TEXT PRIMARY KEY)")
            db.execute("DELETE FROM mensagens_alteradas")
            for p in topicos:
                if p in alteradas:
                    corpo = (wiki / p).read_text(encoding="utf-8-sig")
                    db.executemany("INSERT OR IGNORE INTO mensagens_alteradas VALUES (?)",
                                   ((m[1],) for m in MENSAGEM.finditer(corpo)))
            alteradas.update(r[0] for r in db.execute("""
                SELECT DISTINCT a.pagina FROM mensagens_alteradas m JOIN backlinks b ON b.mensagem=m.id
                JOIN itens a ON a.id=b.anexo
            """) if r[0] in atuais)
    for p in removidas | alteradas:
        db.execute("DELETE FROM backlinks WHERE anexo IN (SELECT id FROM itens WHERE pagina=?)", (p,))
        if p.startswith("local/anexos/zulip-anexo-"):
            db.execute("DELETE FROM usos_anexo WHERE id=?", (Path(p).stem,))
        db.execute("DELETE FROM itens WHERE pagina=?", (p,))
        db.execute("DELETE FROM paginas WHERE pagina=?", (p,))
    extracao = {}
    if EXTRACAO in atuais and any(p.startswith("local/anexos/zulip-anexo-") for p in alteradas):
        extracao = json.loads((wiki / EXTRACAO).read_bytes())
    capturas = {}
    if GRAFO in atuais and any(p.startswith("local/doist/doist-") for p in alteradas):
        with abrir_leitura(wiki / GRAFO) as grafo:
            capturas = dict(grafo.execute("SELECT id,estado FROM nos WHERE tipo='captura'"))
    for p in sorted(alteradas, key=lambda p: (p.startswith("local/anexos/zulip-anexo-"), p)):
        if p not in (DECISOES, GRAFO):
            indexar(db, wiki, p, extracao, capturas)
        db.execute("INSERT INTO paginas VALUES (?,?)", (p, atuais[p]))
    if DECISOES in alteradas or DECISOES in removidas:
        carregar_decisoes(db, wiki)
    if "curadoria.json" in alteradas or "curadoria.json" in removidas:
        carregar_exemplos(db, wiki)
    if ({"curadoria.json", DECISOES} & (alteradas | removidas)):
        db.execute("DELETE FROM decisoes WHERE estado='conferido' AND id NOT IN (SELECT id FROM evidencias)")
        db.execute("DELETE FROM decisoes WHERE id IN (SELECT id FROM evidencias) AND estado!='conferido'")
        if "curadoria.json" in atuais:
            revisao = json.loads((wiki / "curadoria.json").read_bytes())
            for chave, exemplos in revisao.items():
                item = db.execute("SELECT texto,assinatura FROM itens WHERE id=?", (chave,)).fetchone()
                if item and any(isinstance(e, dict) and
                                (e["trecho"] not in item[0] or e.get("assinatura") != item[1]) for e in exemplos):
                    db.execute("DELETE FROM decisoes WHERE id=?", (chave,))



def conectar(wiki):
    if not (wiki / "local").is_dir():
        raise ValueError("Edição local ausente. Execute preparar_nuvem.py na raiz do projeto.")
    db = sqlite3.connect(wiki / "local/consulta.sqlite3", timeout=180)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(ESQUEMA)
        with db:
            sincronizar(db, wiki)
    except BaseException:
        db.close()
        raise
    return db
