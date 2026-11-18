from contextlib import closing
import re
import sqlite3


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


def abrir_leitura(path):
    return closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True))


def pagina_local(db, wiki, identificador, url):
    ancora = ""
    if re.fullmatch(r"doist-[a-z0-9-]+", identificador):
        pagina = f"local/doist/{identificador}.md"
    elif identificador in TEMAS:
        pagina = f"{identificador}.md"
    elif identificador in SITUACOES:
        pagina, ancora = "situacoes.md", "#" + identificador
    else:
        canal = re.search(r"/(?:channel|stream)/(\d+)", url or "")
        if not canal:
            return None
        topico = identificador
        if re.fullmatch(r"zulip-msg-\d+", identificador):
            linha = db.execute("SELECT destino FROM ligacoes WHERE origem=? AND relacao='pertence'",
                               (identificador,)).fetchone()
            if not linha:
                return None
            topico, ancora = linha[0], "#" + identificador
        if not re.fullmatch(r"zulip-topico-[0-9a-f]{24}", topico):
            return None
        pagina = f"local/zulip/canal-{canal[1]}/{topico}.md"
    return pagina + ancora if (wiki / pagina).is_file() else None


def buscar_exemplos(db, wiki, *, tema=None, situacao=None, fonte=None, texto=None, curados=False, limite=10, pular=0):
    filtros = ["n.tipo IN ('mensagem', 'captura')"]
    valores = []
    destinos = [destino for destino in (tema, situacao) if destino]
    for destino in destinos:
        origem = " AND l.relacao='curado'" if curados else ""
        filtros.append(f"EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.destino=?{origem})")
        valores.append(destino)
    if curados and not (tema or situacao):
        filtros.append("EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.relacao='curado')")
    if fonte:
        filtros.append("n.fonte = ?")
        valores.append(fonte)
    if texto:
        filtros.append("(instr(lower(n.texto), lower(?)) > 0 OR instr(lower(n.titulo), lower(?)) > 0)")
        valores.extend((texto, texto))
    where = " AND ".join(filtros)
    cursor = db.execute(f"""
        SELECT n.id, n.fonte, n.titulo, n.url, n.estado, substr(n.texto,1,320) AS previa
        FROM nos n WHERE {where}
        ORDER BY EXISTS (SELECT 1 FROM ligacoes l WHERE l.origem=n.id AND l.relacao='curado') DESC,
                 n.ordem DESC, n.id
        LIMIT ? OFFSET ?
    """, (*valores, limite, pular))
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
                           "pagina_local": pagina_local(db, wiki, linha["id"], linha["url"])})
    return resultados


def ler_no(db, wiki, identificador):
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
    return {"no": dict(no), "pagina_local": pagina_local(db, wiki, identificador, no["url"]),
                   "ligacoes": [dict(linha) for linha in saidas],
                   "ligacoes_recebidas": {linha["relacao"]: linha["quantidade"] for linha in entradas}}
