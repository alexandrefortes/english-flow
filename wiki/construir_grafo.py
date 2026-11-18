"""Indexa as fontes locais e liga trechos candidatos às páginas Markdown."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from consulta_grafo import TEMAS, SITUACOES, abrir_leitura, buscar_exemplos, ler_no
from regras import classificar
from recibos_ocr import ler_recibo


WIKI = Path(__file__).resolve().parent
PROJETO = WIKI.parent
DOIST_ALIASES = {
    "pedido-atualizacao-newsletter": "doist-pedir-atualizacao",
    "feedback-rascunho-google-docs": "doist-dar-feedback",
    "prazo-imagem-todoist": "doist-combinar-prazo",
}
ESQUEMA = """
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
INSERIR_NO = "INSERT OR IGNORE INTO nos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
INSERIR_LIGACAO = "INSERT OR IGNORE INTO ligacoes VALUES (?, ?, ?, ?)"
BLOCO = 3000


def carregar_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def registrar_topicos(db):
    nos = [(slug, "tema", titulo, None, None, None, f"wiki/{slug}.md", None, None, None)
           for slug, titulo in TEMAS.items()]
    nos.extend((slug, "situacao", titulo, None, None, None, f"wiki/situacoes.md#{slug}", None, None, None)
               for slug, titulo in SITUACOES.items())
    db.executemany(INSERIR_NO, nos)


def classificar_no(identificador, texto):
    return [(identificador, slug, "candidato", trecho) for slug, trecho in classificar(texto)
            if slug in TEMAS or slug in SITUACOES]


def registrar_mensagens(db, filas, registro, threads):
    for stream, canal, topico, numero, texto, url in filas:
        identificador = f"zulip-msg-{numero}"
        conversa = threads.get((stream, topico))
        if conversa is None:
            chave = json.dumps([stream, topico], ensure_ascii=False).encode("utf-8")
            conversa = "zulip-topico-" + hashlib.sha256(chave).hexdigest()[:24]
            threads[stream, topico] = conversa
            db.execute(INSERIR_NO, (conversa, "conversa", f"{canal} · {topico or 'Sem tópico'}", "Zulip",
                                    registro, url.rsplit("/near/", 1)[0], None, None, None, None))
        cursor = db.execute(INSERIR_NO, (identificador, "mensagem", f"{canal} · {topico or 'Sem tópico'}",
                                       "Zulip", registro, url, None, texto, None, numero))
        if cursor.rowcount:
            yield identificador, conversa, "pertence", None
            yield from classificar_no(identificador, texto)


def registrar_zulip(db, dados):
    threads = {}
    for registro in ("zulip", "zulip-piloto"):
        path = dados / registro / "coleta.sqlite3"
        if not path.is_file():
            continue
        vistos = 0
        with abrir_leitura(path) as coleta:
            cursor = coleta.execute("SELECT stream_id, channel, topic, id, content, url FROM mensagens ORDER BY id")
            while bloco := cursor.fetchmany(BLOCO):
                db.executemany(INSERIR_LIGACAO, registrar_mensagens(db, bloco, registro, threads))
                vistos += len(bloco)
        db.execute("INSERT INTO entradas VALUES (?, ?)", (f"{registro}/coleta.sqlite3", vistos))
        print(f"{registro}: {vistos:,} mensagens lidas", flush=True)

    for path in sorted(dados.glob("zulip-*.json")):
        amostra = carregar_json(path)
        url = amostra["fonte"]
        local = re.search(r"/(?:channel|stream)/(\d+)(?:-([^/]+))?/", url)
        if local is None:
            raise ValueError(f"Canal não reconhecido em {path.name}.")
        stream, nome = local.groups()
        canal = nome or f"Canal {stream}"
        topico = amostra["topico"]
        filas = [(int(stream), canal, topico, msg["id"], msg["texto"],
                  f"{url.rsplit('/', 1)[0]}/{msg['id']}") for msg in amostra["mensagens"]]
        db.executemany(INSERIR_LIGACAO, registrar_mensagens(db, filas, path.stem, threads))
        db.execute("INSERT INTO entradas VALUES (?, ?)", (path.name, len(filas)))


def transcricoes(dados):
    path = dados / "doist" / "wiki-ocr.jsonl"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig") as arquivo:
        return {item["id"]: item for line in arquivo if line.strip() for item in (json.loads(line),)}


def aplicar_revisoes_doist(db, dados):
    alterados = set()
    for caminho in sorted((dados / "revisao-ocr" / "terra").glob("doist-*.json")):
        try:
            item = ler_recibo(caminho)
        except (OSError, ValueError) as erro:
            print(f"Revisão ignorada: {caminho.name}: {erro}", flush=True)
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
            db.executemany(INSERIR_LIGACAO, classificar_no(item["id"], item["texto"]))
        alterados.add(item["id"])
    return alterados


def registrar_doist(db, dados):
    capturas = {arquivo.stem: arquivo for arquivo in sorted((dados / "doist" / "capturas").glob("*"))
                if arquivo.is_file() and arquivo.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")}
    ocr = transcricoes(dados)
    catalogo = carregar_json(PROJETO / "fontes" / "doist.json")
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
        db.execute(INSERIR_NO, (identificador, "captura", item["titulo"], "Doist", chave, item["url_secao"],
                                caminho, texto, estado, None))
        if estado == "extraido":
            db.executemany(INSERIR_LIGACAO, classificar_no(identificador, texto))
    aplicar_revisoes_doist(db, dados)
    db.execute("INSERT INTO entradas VALUES (?, ?)", ("fontes/doist.json (elegíveis)", len(elegiveis)))
    db.execute("INSERT INTO entradas VALUES (?, ?)", ("doist/wiki-ocr.jsonl", len(ocr)))
    print(f"Doist: {len(elegiveis)} capturas no catálogo, {len(ocr)} resultados de OCR", flush=True)


def registrar_curadoria(db):
    curadoria = carregar_json(WIKI / "curadoria.json")
    for origem, exemplos in curadoria.items():
        if not db.execute("SELECT 1 FROM nos WHERE id=?", (origem,)).fetchone():
            continue  # O índice também pode ser criado com uma coleta parcial.
        texto, = db.execute("SELECT texto FROM nos WHERE id=?", (origem,)).fetchone()
        for exemplo in exemplos:
            if isinstance(exemplo, str):
                db.execute(INSERIR_LIGACAO, (origem, exemplo, "curado", None))
            elif exemplo["trecho"] in (texto or ""):
                db.executemany(INSERIR_LIGACAO, ((origem, destino, "curado", exemplo["trecho"])
                                                 for destino in exemplo["usos"]))


def construir(dados, grafo):
    if grafo.exists():
        with abrir_leitura(grafo) as existente:
            tabelas = {linha[0] for linha in existente.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        if tabelas != {"nos", "ligacoes", "entradas"}:
            raise ValueError(f"O destino não é um índice do grafo: {grafo}")
    grafo.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=grafo.parent, suffix=".sqlite3", delete=False) as arquivo:
        temporario = Path(arquivo.name)
    try:
        with closing(sqlite3.connect(temporario)) as db, db:
            db.executescript("PRAGMA journal_mode=OFF; PRAGMA foreign_keys=ON;" + ESQUEMA)
            registrar_topicos(db)
            registrar_doist(db, dados)
            registrar_zulip(db, dados)
            registrar_curadoria(db)
            db.execute("CREATE INDEX ligacoes_destino ON ligacoes(destino, relacao, origem)")
            db.execute("CREATE INDEX nos_tipo ON nos(tipo, estado)")
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("Falha na verificação do SQLite.")
        temporario.replace(grafo)
    finally:
        temporario.unlink(missing_ok=True)


def atualizar_curadoria(grafo):
    with closing(sqlite3.connect(grafo.resolve().as_uri() + "?mode=rw", uri=True)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM ligacoes WHERE relacao='curado'")
        registrar_curadoria(db)


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
    imprimir_json({"nos": totais, "ocr": ocr, "ligacoes": ligacoes,
                   "itens_com_classificacao": classificados, "entradas": entradas})


def buscar(db, args):
    resultados = buscar_exemplos(db, WIKI, tema=args.tema, situacao=args.situacao, fonte=args.fonte,
                                 texto=args.texto, curados=args.curados, limite=args.limite, pular=args.pular)
    if args.formato == "markdown":
        imprimir_resultados(resultados)
    else:
        imprimir_json(resultados)


def imprimir_resultados(resultados):
    if not resultados:
        print("Nenhum exemplo encontrado para esses filtros.")
    for item in resultados:
        destino = item["pagina_local"] or item["url"]
        print(f"- [{item['titulo']}]({destino}) · {item['fonte']} · `{item['id']}`")
        if item["estado"]:
            print(f"  - Estado da imagem: {item['estado']}")
        for ligacao in item["classificacao"]:
            trecho = " ".join((ligacao["trecho"] or "").split())
            exemplo = f" · {trecho}" if trecho else ""
            print(f"  - {ligacao['destino']} ({ligacao['relacao']}){exemplo}")


def imprimir_json(objeto):
    print(json.dumps(objeto, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, help="pasta raiz da coleta")
    parser.add_argument("--grafo", type=Path, help="destino do índice SQLite")
    modos = parser.add_subparsers(dest="modo", required=True)
    modos.add_parser("construir", help="reconstrói o índice a partir da coleta local")
    modos.add_parser("atualizar-curadoria", help="atualiza só as ligações curadas no grafo de origem")
    modos.add_parser("resumo", help="mostra a cobertura e os tipos de ligação")
    busca = modos.add_parser("buscar", help="procura exemplos e candidatos")
    busca.add_argument("--tema", choices=TEMAS)
    busca.add_argument("--situacao", choices=SITUACOES)
    busca.add_argument("--fonte", choices=("Zulip", "Doist"))
    busca.add_argument("--texto")
    busca.add_argument("--curados", action="store_true", help="limita à curadoria manual")
    busca.add_argument("--formato", choices=("json", "markdown"), default="json")
    busca.add_argument("--limite", type=int, default=10)
    busca.add_argument("--pular", type=int, default=0, help="pula resultados para navegar às próximas páginas")
    detalhe = modos.add_parser("mostrar", help="mostra um nó e suas ligações")
    detalhe.add_argument("id")
    args = parser.parse_args()
    dados = (args.dados or PROJETO / "dados").resolve()
    padrão = dados / "wiki" / "grafo.sqlite3"
    portátil = WIKI / "local" / "grafo.sqlite3"
    if args.dados is None and args.modo not in ("construir", "atualizar-curadoria") and portátil.is_file():
        padrão = portátil
    grafo = (args.grafo or padrão).resolve()
    if args.modo == "construir":
        try:
            construir(dados, grafo)
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(str(exc))
    if not grafo.is_file():
        parser.error("Índice ausente. Execute o modo construir.")
    if args.modo == "atualizar-curadoria":
        try:
            atualizar_curadoria(grafo)
        except (OSError, ValueError, sqlite3.Error) as exc:
            parser.error(str(exc))
    indice = grafo.with_name("consulta.sqlite3") if grafo.resolve() == portátil.resolve() else None
    with abrir_leitura(grafo, indice) as db:
        db.row_factory = sqlite3.Row
        if args.modo in ("construir", "atualizar-curadoria", "resumo"):
            resumo(db)
        elif args.modo == "buscar":
            if not (1 <= args.limite <= 200) or args.pular < 0:
                parser.error("Use limite entre 1 e 200 e um valor não negativo para pular.")
            buscar(db, args)
        else:
            try:
                imprimir_json(ler_no(db, WIKI, args.id))
            except ValueError as exc:
                parser.error(str(exc))


if __name__ == "__main__":
    main()
