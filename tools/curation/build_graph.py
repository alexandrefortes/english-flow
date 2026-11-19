import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from tools import DOIST_CATALOG, ROOT as PROJECT, WIKI
from graph_reader import TOPICS, SITUATIONS, open_read_only, find_examples, read_node
from tools.curation.learning_patterns import classify
from tools.curation.review_records import read_receipt


DOIST_ALIASES = {
    "pedido-atualizacao-newsletter": "doist-pedir-atualizacao",
    "feedback-rascunho-google-docs": "doist-dar-feedback",
    "prazo-imagem-todoist": "doist-combinar-prazo",
}
SCHEMA = """
CREATE TABLE nos (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    fonte TEXT,
    origem TEXT,
    url TEXT,
    caminho TEXT,
    texto TEXT,
    estado TEXT,
    ordem INTEGER
);
CREATE TABLE ligacoes (
    origem TEXT NOT NULL REFERENCES nos(id),
    destino TEXT NOT NULL REFERENCES nos(id),
    relacao TEXT NOT NULL,
    trecho TEXT,
    PRIMARY KEY (origem, destino, relacao)
) WITHOUT ROWID;
CREATE TABLE entradas (arquivo TEXT PRIMARY KEY, itens INTEGER NOT NULL);
"""
INSERT_NODE = "INSERT OR IGNORE INTO nos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
INSERT_EDGE = "INSERT OR IGNORE INTO ligacoes VALUES (?, ?, ?, ?)"
BLOCK = 3000


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def record_topics(db):
    nos = [(slug, "tema", titulo, None, None, None, f"wiki/{slug}.md", None, None, None)
           for slug, titulo in TOPICS.items()]
    nos.extend((slug, "situacao", titulo, None, None, None, f"wiki/situacoes.md#{slug}", None, None, None)
               for slug, titulo in SITUATIONS.items())
    db.executemany(INSERT_NODE, nos)


def classify_node(identificador, texto):
    return [(identificador, slug, "candidato", trecho) for slug, trecho in classify(texto)
            if slug in TOPICS or slug in SITUATIONS]


def record_messages(db, filas, registro, threads):
    for stream, canal, topico, numero, texto, url in filas:
        identificador = f"zulip-msg-{numero}"
        conversa = threads.get((stream, topico))
        if conversa is None:
            chave = json.dumps([stream, topico], ensure_ascii=False).encode("utf-8")
            conversa = "zulip-topico-" + hashlib.sha256(chave).hexdigest()[:24]
            threads[stream, topico] = conversa
            db.execute(INSERT_NODE, (conversa, "conversa", f"{canal} · {topico or 'Sem tópico'}", "Zulip",
                                    registro, url.rsplit("/near/", 1)[0], None, None, None, None))
        cursor = db.execute(INSERT_NODE, (identificador, "mensagem", f"{canal} · {topico or 'Sem tópico'}",
                                       "Zulip", registro, url, None, texto, None, numero))
        if cursor.rowcount:
            yield identificador, conversa, "pertence", None
            yield from classify_node(identificador, texto)


def record_zulip(db, dados):
    threads = {}
    for registro in ("zulip", "zulip-piloto"):
        path = dados / registro / "coleta.sqlite3"
        if not path.is_file():
            continue
        vistos = 0
        with open_read_only(path) as coleta:
            cursor = coleta.execute("SELECT stream_id, channel, topic, id, content, url FROM mensagens ORDER BY id")
            while bloco := cursor.fetchmany(BLOCK):
                db.executemany(INSERT_EDGE, record_messages(db, bloco, registro, threads))
                vistos += len(bloco)
        db.execute("INSERT INTO entradas VALUES (?, ?)", (f"{registro}/coleta.sqlite3", vistos))
        print(f'{registro}: read {vistos:,} messages', flush=True)

    for path in sorted(dados.glob("zulip-*.json")):
        amostra = load_json(path)
        url = amostra["fonte"]
        local = re.search(r"/(?:channel|stream)/(\d+)(?:-([^/]+))?/", url)
        if local is None:
            raise ValueError(f'Unknown channel in {path.name}.')
        stream, nome = local.groups()
        canal = nome or f"Canal {stream}"
        topico = amostra["topico"]
        filas = [(int(stream), canal, topico, msg["id"], msg["texto"],
                  f"{url.rsplit('/', 1)[0]}/{msg['id']}") for msg in amostra["mensagens"]]
        db.executemany(INSERT_EDGE, record_messages(db, filas, path.stem, threads))
        db.execute("INSERT INTO entradas VALUES (?, ?)", (path.name, len(filas)))


def transcricoes(dados):
    path = dados / "doist" / "wiki-ocr.jsonl"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig") as arquivo:
        return {item["id"]: item for line in arquivo if line.strip() for item in (json.loads(line),)}


def apply_doist_reviews(db, dados):
    alterados = set()
    for caminho in sorted((dados / "revisao-ocr" / "terra").glob("doist-*.json")):
        try:
            item = read_receipt(caminho)
        except (OSError, ValueError) as erro:
            print(f'Skipped review {caminho.name}: {erro}', flush=True)
            continue
        linha = db.execute(
            "SELECT caminho, texto, estado FROM nos WHERE id=? AND tipo='captura'", (item["id"],)
        ).fetchone()
        if not linha or not linha[0]:
            continue
        imagem = (dados / linha[0]).resolve()
        if not imagem.is_relative_to(dados.resolve()) or not imagem.is_file():
            continue
        with imagem.open("rb") as arquivo:
            if hashlib.file_digest(arquivo, "sha256").hexdigest() != item["sha256"]:
                continue
        if (linha[1], linha[2]) == (item["texto"], item["estado"]):
            continue
        db.execute("UPDATE nos SET texto=?,estado=? WHERE id=?", (item["texto"], item["estado"], item["id"]))
        db.execute("DELETE FROM ligacoes WHERE origem=? AND relacao='candidato'", (item["id"],))
        if item["texto"]:
            db.executemany(INSERT_EDGE, classify_node(item["id"], item["texto"]))
        alterados.add(item["id"])
    return alterados


def record_doist(db, dados):
    capturas = {arquivo.stem: arquivo for arquivo in sorted((dados / "doist" / "capturas").glob("*"))
                if arquivo.is_file() and arquivo.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")}
    ocr = transcricoes(dados)
    catalogo = load_json(DOIST_CATALOG)
    elegiveis = [item for item in catalogo["itens"] if item["estado"] == "elegível"]
    for item in elegiveis:
        chave = item["id"]
        alias = DOIST_ALIASES.get(chave)
        identificador = alias or f"doist-{chave}"
        captura = capturas.get(chave)
        if captura is None and alias:
            captura = next((path for path in sorted(dados.glob(f"{alias}.*"))
                            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")), None)
        leitura = ocr.get(chave, {})
        texto = leitura.get("texto", "")
        estado = leitura.get("estado", "pendente") if captura else "ausente"
        caminho = captura.relative_to(dados).as_posix() if captura else None
        db.execute(INSERT_NODE, (identificador, "captura", item["titulo"], "Doist", chave, item["url_secao"],
                                caminho, texto, estado, None))
        if estado == "extraido":
            db.executemany(INSERT_EDGE, classify_node(identificador, texto))
    apply_doist_reviews(db, dados)
    db.execute("INSERT INTO entradas VALUES (?, ?)", ("doist-catalog.json (eligible)", len(elegiveis)))
    db.execute("INSERT INTO entradas VALUES (?, ?)", ("doist/wiki-ocr.jsonl", len(ocr)))
    print(f'Doist: {len(elegiveis)} catalog images, {len(ocr)} OCR results', flush=True)


def record_reviews(db):
    curadoria = load_json(WIKI / "curadoria.json")
    for origem, exemplos in curadoria.items():
        if not db.execute("SELECT 1 FROM nos WHERE id=?", (origem,)).fetchone():
            continue
        texto, = db.execute("SELECT texto FROM nos WHERE id=?", (origem,)).fetchone()
        for exemplo in exemplos:
            if isinstance(exemplo, str):
                db.execute(INSERT_EDGE, (origem, exemplo, "curado", None))
            elif exemplo["trecho"] in (texto or ""):
                db.executemany(INSERT_EDGE, ((origem, destino, "curado", exemplo["trecho"])
                                                 for destino in exemplo["usos"]))


def build(dados, grafo):
    if grafo.exists():
        with open_read_only(grafo) as existente:
            tabelas = {linha[0] for linha in existente.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        if tabelas != {"nos", "ligacoes", "entradas"}:
            raise ValueError(f'The destination is not a graph index: {grafo}')
    grafo.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=grafo.parent, suffix=".sqlite3", delete=False) as arquivo:
        temporario = Path(arquivo.name)
    try:
        with closing(sqlite3.connect(temporario)) as db, db:
            db.executescript("PRAGMA journal_mode=OFF; PRAGMA foreign_keys=ON;" + SCHEMA)
            record_topics(db)
            record_doist(db, dados)
            record_zulip(db, dados)
            record_reviews(db)
            db.execute("CREATE INDEX ligacoes_destino ON ligacoes(destino, relacao, origem)")
            db.execute("CREATE INDEX nos_tipo ON nos(tipo, estado)")
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("SQLite verification failed.")
        temporario.replace(grafo)
    finally:
        temporario.unlink(missing_ok=True)


def update_reviews(grafo):
    with closing(sqlite3.connect(grafo.resolve().as_uri() + "?mode=rw", uri=True)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM ligacoes WHERE relacao='curado'")
        record_reviews(db)


def resumo(db):
    totais = dict(db.execute("SELECT tipo, count(*) FROM nos GROUP BY tipo"))
    ocr = dict(db.execute("SELECT estado, count(*) FROM nos WHERE tipo='captura' GROUP BY estado"))
    ligacoes = dict(db.execute("SELECT relacao, count(*) FROM ligacoes GROUP BY relacao"))
    classificados = dict(db.execute("""
        SELECT n.tipo, count(*) FROM nos n
        WHERE EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.relacao IN ('candidato','curado'))
        GROUP BY n.tipo
    """))
    entradas = dict(db.execute("SELECT arquivo, itens FROM entradas ORDER BY arquivo"))
    print_json({"nos": totais, "ocr": ocr, "ligacoes": ligacoes,
                   "itens_com_classificacao": classificados, "entradas": entradas})


def buscar(db, args):
    resultados = find_examples(db, WIKI, tema=args.topic, situacao=args.situation, fonte=args.source,
                                 texto=args.text, curados=args.verified_only, limite=args.limit, pular=args.offset)
    if args.format == "markdown":
        print_results(resultados)
    else:
        print_json(resultados)


def print_results(resultados):
    if not resultados:
        print("No examples match these filters.")
    for item in resultados:
        destino = item["pagina_local"] or item["url"]
        print(f"- [{item['titulo']}]({destino}) · {item['fonte']} · `{item['id']}`")
        if item["estado"]:
            print(f"  - Image status: {item['estado']}")
        for ligacao in item["classificacao"]:
            trecho = " ".join((ligacao["trecho"] or "").split())
            exemplo = f" · {trecho}" if trecho else ""
            print(f"  - {ligacao['destino']} ({ligacao['relacao']}){exemplo}")


def print_json(objeto):
    print(json.dumps(objeto, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Build or read the graph for the local sources.')
    parser.add_argument("--data", type=Path, help="Root of the source collection.")
    parser.add_argument("--graph", type=Path, help="Path to the SQLite index.")
    modos = parser.add_subparsers(dest="command", required=True)
    modos.add_parser("build", help="Build the index from the local collection.")
    modos.add_parser("update-reviews", help="Update the verified links in the source graph.")
    modos.add_parser("summary", help="Show coverage and link types.")
    busca = modos.add_parser("search", help="Find examples and candidates.")
    busca.add_argument("--topic", choices=TOPICS)
    busca.add_argument("--situation", choices=SITUATIONS)
    busca.add_argument("--source", choices=("Zulip", "Doist"))
    busca.add_argument("--text")
    busca.add_argument("--verified-only", action="store_true", help="Show verified items only.")
    busca.add_argument("--format", choices=("json", "markdown"), default="json")
    busca.add_argument("--limit", type=int, default=10)
    busca.add_argument("--offset", type=int, default=0, help="Skip results on previous pages.")
    detalhe = modos.add_parser("show", help="Show a node and its links.")
    detalhe.add_argument("id")
    args = parser.parse_args()
    dados = (args.data or PROJECT / "dados").resolve()
    padrão = dados / "wiki" / "grafo.sqlite3"
    portátil = WIKI / "local" / "grafo.sqlite3"
    if args.data is None and args.command not in ("build", "update-reviews") and portátil.is_file():
        padrão = portátil
    grafo = (args.graph or padrão).resolve()
    if args.command == "build":
        try:
            build(dados, grafo)
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(str(exc))
    if not grafo.is_file():
        parser.error("Index missing. Run the build command.")
    if args.command == "update-reviews":
        try:
            update_reviews(grafo)
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(str(exc))
    indice = grafo.with_name("consulta.sqlite3") if grafo.resolve() == portátil.resolve() else None
    with open_read_only(grafo, indice) as db:
        db.row_factory = sqlite3.Row
        if args.command in ("build", "update-reviews", "summary"):
            resumo(db)
        elif args.command == "search":
            if not (1 <= args.limit <= 200) or args.offset < 0:
                parser.error("Set the limit between 1 and 200. Use a nonnegative offset.")
            buscar(db, args)
        else:
            try:
                print_json(read_node(db, WIKI, args.id))
            except ValueError as exc:
                parser.error(str(exc))


if __name__ == "__main__":
    main()
