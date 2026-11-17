"""Indexa as fontes locais e liga trechos candidatos às páginas Markdown."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from regras import classificar


WIKI = Path(__file__).resolve().parent
PROJETO = WIKI.parent
TEMAS = {
    "gramatica": "Gramática",
    "conversacao": "Conversação",
    "vocabulario": "Vocabulário",
    "phrasal-verbs": "Phrasal verbs",
    "linguagem-informal": "Linguagem informal e gírias",
    "dia-a-dia": "Dia a dia no trabalho",
    "pronuncia": "Pronúncia",
}
SITUACOES = {
    "pedir-atualizacao": "Pedir uma atualização",
    "negociar-prazo": "Negociar um prazo",
    "dar-feedback": "Dar feedback",
    "confirmar-proximos-passos": "Confirmar próximos passos",
    "se-apresentar": "Apresentar-se a novos colegas",
    "pedir-ajuda": "Pedir ajuda",
    "esclarecer": "Pedir esclarecimento",
    "comunicar-risco": "Comunicar risco",
}
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


def abrir_leitura(path):
    return closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True))


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
    db.execute("INSERT INTO entradas VALUES (?, ?)", ("fontes/doist.json (elegíveis)", len(elegiveis)))
    db.execute("INSERT INTO entradas VALUES (?, ?)", ("doist/wiki-ocr.jsonl", len(ocr)))
    print(f"Doist: {len(elegiveis)} capturas no catálogo, {len(ocr)} resultados de OCR", flush=True)


def registrar_curadoria(db):
    curadoria = carregar_json(WIKI / "curadoria.json")
    for origem, destinos in curadoria.items():
        if not db.execute("SELECT 1 FROM nos WHERE id=?", (origem,)).fetchone():
            continue  # O índice também pode ser criado com uma coleta parcial.
        db.executemany(INSERIR_LIGACAO, [(origem, destino, "curado", None) for destino in destinos])


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


def pagina_local(db, identificador, url):
    if identificador.startswith("doist-"):
        pagina = f"local/doist/{identificador}.md"
        return pagina if (WIKI / pagina).is_file() else None
    if not identificador.startswith("zulip-msg-"):
        return None
    channel = re.search(r"/(?:channel|stream)/(\d+)", url or "")
    thread = db.execute(
        "SELECT destino FROM ligacoes WHERE origem=? AND relacao='pertence'", (identificador,)
    ).fetchone()
    if channel and thread:
        pagina = f"local/zulip/canal-{channel[1]}/{thread[0]}.md"
        if (WIKI / pagina).is_file():
            return f"{pagina}#{identificador}"
    return None


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
    filtros = ["n.tipo IN ('mensagem', 'captura')"]
    valores = []
    destinos = [destino for destino in (args.tema, args.situacao) if destino]
    for destino in destinos:
        origem = " AND l.relacao='curado'" if args.curados else ""
        filtros.append(f"EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.destino=?{origem})")
        valores.append(destino)
    if args.curados and not (args.tema or args.situacao):
        filtros.append("EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.relacao='curado')")
    if args.fonte:
        filtros.append("n.fonte = ?")
        valores.append(args.fonte)
    if args.texto:
        filtros.append("(instr(lower(n.texto), lower(?)) > 0 OR instr(lower(n.titulo), lower(?)) > 0)")
        valores.extend((args.texto, args.texto))
    where = " AND ".join(filtros)
    cursor = db.execute(f"""
        SELECT n.id, n.fonte, n.titulo, n.url, n.estado, substr(n.texto,1,320) AS previa
        FROM nos n WHERE {where}
        ORDER BY EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.relacao='curado') DESC,
                 n.ordem DESC, n.id
        LIMIT ? OFFSET ?
    """, (*valores, args.limite, args.pular))
    resultados = []
    for linha in cursor:
        vinculos = db.execute("""
            SELECT destino, relacao, trecho FROM ligacoes
            WHERE origem=? AND relacao IN ('curado','candidato')
            ORDER BY destino, relacao DESC
        """, (linha["id"],))
        classificacao = [dict(vinculo) for vinculo in vinculos
                         if not destinos or vinculo["destino"] in destinos]
        resultados.append({**dict(linha), "classificacao": classificacao,
                           "pagina_local": pagina_local(db, linha["id"], linha["url"])})
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


def mostrar(db, identificador):
    no = db.execute("SELECT * FROM nos WHERE id=?", (identificador,)).fetchone()
    if no is None:
        raise ValueError(f"Nó não encontrado: {identificador}")
    saidas = db.execute("""
        SELECT l.destino AS id, l.relacao, l.trecho, n.titulo, n.caminho
        FROM ligacoes l JOIN nos n ON n.id=l.destino
        WHERE l.origem=? ORDER BY l.relacao, l.destino
    """, (identificador,))
    entradas = db.execute("""
        SELECT relacao, count(*) AS quantidade FROM ligacoes WHERE destino=? GROUP BY relacao
    """, (identificador,))
    imprimir_json({"no": dict(no), "pagina_local": pagina_local(db, identificador, no["url"]),
                   "ligacoes": [dict(linha) for linha in saidas],
                   "ligacoes_recebidas": {linha["relacao"]: linha["quantidade"] for linha in entradas}})


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
    with abrir_leitura(grafo) as db:
        db.row_factory = sqlite3.Row
        if args.modo in ("construir", "atualizar-curadoria", "resumo"):
            resumo(db)
        elif args.modo == "buscar":
            if not (1 <= args.limite <= 200) or args.pular < 0:
                parser.error("Use limite entre 1 e 200 e um valor não negativo para pular.")
            buscar(db, args)
        else:
            try:
                mostrar(db, args.id)
            except ValueError as exc:
                parser.error(str(exc))


if __name__ == "__main__":
    main()
