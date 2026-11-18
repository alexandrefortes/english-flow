"""Registra decisões por ID sobre a edição textual e confere sua cobertura."""
import argparse
from collections import Counter
from contextlib import closing
import gzip
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

WIKI = Path(__file__).resolve().parent
sys.path.insert(0, str(WIKI.parent / "plugins/ingles-para-o-trabalho"))
from indice_wiki import DECISOES, conectar, pagina_id
from consulta_grafo import SITUACOES, abrir_leitura


MARCADOR = re.compile(r"^`{3,}[^\n]*\n.*?^`{3,}[^\n]*$|^>[^\n]*|https?://\S+|"
                      r"\[[^\]\n]*\]\([^\n)]*\)|@_?\*\*[^*]*\*\*|:[\w-]+:", re.M | re.S)
PALAVRA = re.compile(r"[^\W\d_]+", re.UNICODE)
PERGUNTA = re.compile(r"\b(?:what|which|who|when|why|how|can|could|should|would|is|does|did|any)\b[^\n?]{0,180}\?", re.I)
LOG = re.compile(r"traceback \(most recent call last\)|\b(?:exception|errno|stack trace)\b|"
                 r"^\s*(?:File \".*\", line \d+|at \S+\(.*:\d+:\d+\))", re.M | re.I)
INTERFACE = re.compile(r"\b(?:unread|direct messages|settings|subscribe|channels|sign in|notifications|all messages)\b", re.I)
MUDANCA = re.compile(r"\b(?:has marked this topic as resolved|has marked this topic as unresolved|"
                     r"this topic was moved|messages? (?:was|were) moved)\b", re.I)
ALTERACAO = re.compile(r"(?:\[pushed\]|\[opened\]|\[closed\]|\[merged\]|\[updated\]).*?https://github\.com", re.I | re.S)
TECNICO = re.compile(r"\b(?:PR|issue|commit|patch|implementation|test|code|function|API|release|server|client)\b", re.I)


def avaliar_mensagem(item, antes, depois):
    texto = item["texto"]
    if MUDANCA.search(texto):
        return "apoio", "localizar a mudança de estado ou de tópico"
    if ALTERACAO.search(texto):
        return "apoio", "localizar a alteração no repositório"
    fala = MARCADOR.sub(" ", texto)
    palavras = PALAVRA.findall(fala)
    if not palavras:
        if "/user_uploads/" in texto:
            return "apoio", "localizar o arquivo citado"
        if "http" in texto:
            return "apoio", "localizar a referência compartilhada"
        if "```" in texto or texto.lstrip().startswith(">"):
            return "apoio", "consultar o bloco citado na discussão"
        return "sem-uso", "sem palavras de estudo no turno"
    if LOG.search(texto):
        return "apoio", "interpretar o diagnóstico discutido"
    if "/user_uploads/" in texto:
        return "apoio", "interpretar o anexo a partir da mensagem"
    if PERGUNTA.search(fala):
        return "apoio", "identificar a pergunta que orienta a discussão"
    if antes and PERGUNTA.search(MARCADOR.sub(" ", antes)):
        return "apoio", "ler a continuação de uma pergunta"
    if re.search(r"\b(?:thanks|thank you|sorry|welcome)\b", fala, re.I):
        return "apoio", "interpretar a cortesia na conversa"
    if re.search(r"\b(?:because|reason|since|so that)\b", fala, re.I):
        return "apoio", "acompanhar a justificativa no tópico"
    if TECNICO.search(fala):
        return "apoio", "contextualizar o trabalho técnico discutido"
    if len(palavras) < 3:
        if antes and len(PALAVRA.findall(antes)) >= 3:
            return "apoio", "interpretar a resposta breve junto ao turno anterior"
        return "sem-uso", "fragmento curto sem antecedente esclarecedor"
    if depois and PERGUNTA.search(MARCADOR.sub(" ", depois)):
        return "apoio", "situar a pergunta do turno seguinte"
    if antes or depois:
        return "apoio", "acompanhar o assunto entre os turnos do tópico"
    return "apoio", "identificar o assunto apresentado na abertura"


def avaliar(db, item, exemplos):
    chave, tipo, texto = item["id"], item["tipo"], item["texto"]
    if chave in exemplos:
        for e in exemplos[chave]:
            if e.get("assinatura") != item["assinatura"]:
                raise ValueError(f"Confira o contexto de {chave} e registre a assinatura {item['assinatura']}.")
            if not e["trecho"].strip() or e["trecho"] not in texto or not e["usos"] or not e["funcao"]:
                raise ValueError(f"Reveja o trecho e seus usos em {chave}.")
        return "conferido", "trecho localizado na página"
    if tipo == "mensagem":
        vizinhos = []
        for op, ordem in (("<", "DESC"), (">", "ASC")):
            r = db.execute(f"SELECT texto FROM itens WHERE pai=? AND ordem {op} ? ORDER BY ordem {ordem} LIMIT 1",
                           (item["pai"], item["ordem"])).fetchone()
            vizinhos.append(r[0] if r else "")
        return avaliar_mensagem(item, *vizinhos)
    if tipo == "topico":
        turnos = [r for r in db.execute("SELECT id,texto FROM itens WHERE pai=? ORDER BY ordem", (chave,))]
        if not turnos:
            return "sem-uso", "tópico sem turnos disponíveis"
        if len(turnos) == 1:
            return "apoio", "localizar a mensagem de abertura"
        if any(turno["id"] in exemplos for turno in turnos):
            return "apoio", "abrir a sequência de um exemplo conferido"
        if any(PERGUNTA.search(turno["texto"]) for turno in turnos[:-1]):
            return "apoio", "ler uma pergunta e os turnos seguintes"
        if any("/user_uploads/" in turno["texto"] for turno in turnos):
            return "apoio", "situar os arquivos na sequência da conversa"
        return "apoio", "reconstituir a sequência de turnos"
    if tipo == "anexo":
        origem = db.execute("SELECT m.texto FROM backlinks b JOIN itens m ON m.id=b.mensagem "
                            "WHERE b.anexo=? ORDER BY length(m.texto) DESC LIMIT 1", (chave,)).fetchone()
        if LOG.search(texto):
            return "apoio", "conferir o diagnóstico anexado"
        if INTERFACE.search(texto):
            return "apoio", "localizar termos da interface na transcrição"
        if origem and "/user_uploads/" in origem[0]:
            return "apoio", "localizar o arquivo mencionado na conversa"
        if origem:
            return "apoio", "relacionar o arquivo à mensagem que o cita"
        if not texto.strip():
            return "sem-uso", "sem transcrição ou mensagem de origem"
        return "apoio", "consultar o conteúdo extraído do arquivo"
    if tipo == "catalogo":
        return "apoio", item["titulo"]
    if tipo in ("indice", "guia"):
        if item["pagina"] == "AGENTS.md":
            return "apoio", "consultar o procedimento de manutenção"
        if item["pagina"] == "grafo.md":
            return "apoio", "consultar o procedimento de busca"
        return "apoio", "localizar uma fonte ou página de estudo"
    raise ValueError(f"Avalie a página {chave} e registre a evidência ou a função de apoio.")


def registrar(db, wiki, lote):
    exemplos = json.loads((wiki / "curadoria.json").read_bytes())
    anterior = ""
    while True:
        itens = db.execute("SELECT * FROM inventario WHERE id>? AND estado='pendente' ORDER BY id LIMIT ?",
                           (anterior, lote)).fetchall()
        if not itens:
            break
        with db:
            for item in itens:
                estado, motivo = avaliar(db, item, exemplos)
                db.execute("INSERT OR REPLACE INTO decisoes VALUES (?,?,?,?,?)",
                           (item["id"], item["tipo"], item["assinatura"], estado, motivo))
        anterior = itens[-1]["id"]
    with db:
        db.execute("DELETE FROM decisoes WHERE id NOT IN (SELECT id FROM itens)")
    with NamedTemporaryFile(dir=wiki, delete=False) as arquivo:
        tmp = Path(arquivo.name)
        try:
            with gzip.GzipFile(filename="", fileobj=arquivo, mode="wb", mtime=0) as out:
                for linha in db.execute("SELECT id,tipo,assinatura,estado,motivo FROM inventario ORDER BY id"):
                    out.write(("\t".join(linha) + "\n").encode())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    tmp.replace(wiki / DECISOES)


def conferir(db, wiki):
    with abrir_leitura(wiki / "local/grafo.sqlite3") as grafo:
        esperado = {i: "topico" if t == "conversa" else t for i, t in grafo.execute(
            "SELECT id,tipo FROM nos WHERE tipo IN ('conversa','mensagem','captura')")}
    esperado.update(dict.fromkeys(json.loads((wiki / "local/anexos/extracao.json").read_bytes()), "anexo"))
    fontes = set(esperado)
    for pagina in wiki.rglob("*.md"):
        if pagina.stem in fontes:
            continue
        rel = pagina.relative_to(wiki).as_posix()
        if rel == "fontes.md":
            tipo = "catalogo"
        elif rel in {"grafo.md", "AGENTS.md"}:
            tipo = "guia"
        elif rel.startswith("local/") or pagina.name == "index.md":
            tipo = "indice"
        else:
            tipo = "didatica"
        esperado[pagina_id(rel)] = tipo
    esperado.update({pagina_id(p.relative_to(wiki).as_posix()): "catalogo" for p in wiki.rglob("*.json")})
    atual = {r[0]: r[1] for r in db.execute("SELECT id,tipo FROM itens")}
    divergentes = esperado.items() ^ atual.items()
    if divergentes:
        raise ValueError(f"{len(divergentes)} diferenças no inventário: {sorted(divergentes)[:10]}")
    extras = db.execute("SELECT id FROM decisoes EXCEPT SELECT id FROM itens LIMIT 1").fetchone()
    if extras:
        raise ValueError(f"Decisão fora do inventário: {extras[0]}")
    totais = [dict(r) for r in db.execute("SELECT tipo,estado,count(*) AS total FROM inventario GROUP BY tipo,estado")]
    situacoes = Counter()
    for s in SITUACOES:
        situacoes[s] = db.execute("SELECT count(DISTINCT i.id) FROM inventario i JOIN evidencias e ON e.id=i.id "
                                  "WHERE i.estado='conferido' AND instr(' '||e.usos||' ',' '||?||' ')", (s,)).fetchone()[0]
    exemplos = json.loads((wiki / "curadoria.json").read_bytes())
    for i, registros in exemplos.items():
        item = db.execute("SELECT estado,texto FROM inventario WHERE id=?", (i,)).fetchone()
        if not item or item["estado"] != "conferido" or any(e["trecho"] not in item["texto"] for e in registros):
            raise ValueError(f"Evidência divergente: {i}")
    return {"por_tipo_e_decisao": totais, "por_situacao": situacoes, "inventario": len(esperado),
            "pendentes": sum(t["total"] for t in totais if t["estado"] == "pendente")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registrar", action="store_true")
    parser.add_argument("--lote", type=int, default=2000)
    args = parser.parse_args()
    if args.lote < 1:
        parser.error("Use um lote positivo.")
    with closing(conectar(WIKI)) as db:
        if args.registrar:
            registrar(db, WIKI, args.lote)
        print(json.dumps(conferir(db, WIKI), ensure_ascii=False, indent=2))
