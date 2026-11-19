"""Registra decisões por ID sobre a edição textual e confere sua cobertura."""
import argparse
from collections import Counter
from contextlib import closing
from filecmp import cmp
import gzip
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

WIKI = Path(__file__).resolve().parent
sys.path.insert(0, str(WIKI.parent / "plugins/ingles-para-o-trabalho"))
from indice_wiki import DECISOES, TIPOS, conectar, pagina_id, sincronizar
from consulta_grafo import SITUACOES, TEMAS


def validar_revisao(db, revisao):
    chave = revisao["id"]
    item = db.execute("SELECT * FROM itens WHERE id=?", (chave,)).fetchone()
    if not item or (item["tipo"], item["assinatura"]) != (revisao["tipo"], revisao["assinatura"]):
        raise ValueError(f"ID, tipo ou assinatura divergente: {chave}")
    estado, motivo = revisao["estado"], revisao["motivo"]
    if estado not in {"conferido", "apoio", "sem-uso"} or not motivo.strip() or any(c in motivo for c in "\r\n\t"):
        raise ValueError(f"Decisão ou motivo inválido: {chave}")
    evidencias = revisao.get("evidencias", [])
    if (estado == "conferido") != bool(evidencias):
        raise ValueError(f"Confira as evidências de {chave}.")
    trechos = set()
    for e in evidencias:
        if (not e["trecho"].strip() or e["trecho"] not in item["texto"] or e["trecho"] in trechos
                or not e["funcao"].strip() or not e["usos"] or set(e["usos"]) - TEMAS.keys() - SITUACOES.keys()
                or e.get("assinatura", item["assinatura"]) != item["assinatura"]):
            raise ValueError(f"Evidência divergente: {chave}")
        trechos.add(e["trecho"])
    return [{**e, "assinatura": item["assinatura"]} for e in evidencias]


def salvar_registros(db, wiki, exemplos):
    with NamedTemporaryFile(dir=wiki, delete=False) as arq, NamedTemporaryFile(dir=wiki, delete=False) as ev:
        decisoes, trechos = Path(arq.name), Path(ev.name)
    try:
        with decisoes.open("wb") as arquivo, gzip.GzipFile(filename="", fileobj=arquivo, mode="wb", mtime=0) as out:
            for linha in db.execute("SELECT id,tipo,assinatura,estado,motivo FROM inventario "
                                    "WHERE estado!='pendente' ORDER BY id"):
                out.write(("\t".join(linha) + "\n").encode())
        with trechos.open("w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write("{")
            for n, chave in enumerate(sorted(exemplos)):
                arquivo.write(",\n" if n else "\n")
                arquivo.write("  " + json.dumps(chave, ensure_ascii=False) + ": ")
                json.dump(exemplos[chave], arquivo, ensure_ascii=False)
            arquivo.write("\n}\n")
        for temporario, destino in [(trechos, wiki / "curadoria.json"), (decisoes, wiki / DECISOES)]:
            if not destino.exists() or not cmp(temporario, destino, shallow=False):
                temporario.chmod(0o644)
                temporario.replace(destino)
    finally:
        trechos.unlink(missing_ok=True)
        decisoes.unlink(missing_ok=True)


def registrar(db, wiki, arquivos):
    with db:
        sincronizar(db, wiki)
        exemplos = json.loads((wiki / "curadoria.json").read_bytes())
        for arquivo in arquivos:
            with arquivo.open(encoding="utf-8") as entrada:
                for numero, linha in enumerate(entrada, 1):
                    try:
                        r = json.loads(linha)
                        novas = validar_revisao(db, r)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError(f"{arquivo}:{numero}: {exc}") from exc
                    if novas:
                        exemplos[r["id"]] = novas
                    else:
                        exemplos.pop(r["id"], None)
                    db.execute("INSERT OR REPLACE INTO decisoes VALUES (?,?,?,?,?)",
                               (r["id"], r["tipo"], r["assinatura"], r["estado"], r["motivo"]))
        for chave, evidencias in exemplos.items():
            item = db.execute("SELECT tipo,assinatura FROM itens WHERE id=?", (chave,)).fetchone()
            if item and evidencias and all(e["assinatura"] == item["assinatura"] for e in evidencias):
                r = dict(id=chave, tipo=item["tipo"], assinatura=item["assinatura"], estado="conferido",
                         motivo="trecho localizado na página", evidencias=evidencias)
                validar_revisao(db, r)
                db.execute("INSERT INTO decisoes VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                           "assinatura=excluded.assinatura,estado=excluded.estado,motivo=excluded.motivo "
                           "WHERE decisoes.estado!='conferido' OR decisoes.assinatura!=excluded.assinatura",
                           (chave, item["tipo"], item["assinatura"], "conferido", r["motivo"]))
        salvar_registros(db, wiki, exemplos)


def inventariar_paginas(wiki):
    esperado = {}
    marcadores = re.compile(r"^(?:## (zulip-msg-\d+)$|(`{3,})([^\n]*))", re.M)
    for pagina in wiki.rglob("*.md"):
        rel = pagina.relative_to(wiki).as_posix()
        chave = pagina_id(rel)
        if rel.startswith("local/zulip/") and pagina.stem.startswith("zulip-topico-"):
            chave, tipo = pagina.stem, "topico"
            cerca = ""
            for m in marcadores.finditer(pagina.read_text(encoding="utf-8-sig")):
                if cerca:
                    if m[2] and len(m[2]) >= len(cerca) and not m[3].strip():
                        cerca = ""
                elif m[2]:
                    cerca = m[2]
                elif m[1] in esperado:
                    raise ValueError(f"Mensagem repetida na wiki: {m[1]} em {rel}")
                else:
                    esperado[m[1]] = "mensagem"
        elif rel.startswith("local/anexos/zulip-anexo-"):
            chave, tipo = pagina.stem, "anexo"
        elif rel.startswith("local/doist/doist-"):
            chave, tipo = pagina.stem, "captura"
        elif rel == "fontes.md":
            tipo = "catalogo"
        elif rel in {"grafo.md", "AGENTS.md"}:
            tipo = "guia"
        elif rel.startswith("local/") or pagina.name == "index.md":
            tipo = "indice"
        else:
            tipo = "didatica"
        esperado[chave] = tipo
    esperado.update({pagina_id(p.relative_to(wiki).as_posix()): "catalogo" for p in wiki.rglob("*.json")})
    return esperado


def conferir(db, wiki):
    esperado = inventariar_paginas(wiki)
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
        if item and item["estado"] != "pendente" and (item["estado"] != "conferido" or any(
                e["trecho"] not in item["texto"] for e in registros)):
            raise ValueError(f"Evidência divergente: {i}")
    return {"por_tipo_e_decisao": totais, "por_situacao": situacoes, "inventario": len(esperado),
            "pendentes": sum(t["total"] for t in totais if t["estado"] == "pendente")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    operacao = parser.add_mutually_exclusive_group()
    operacao.add_argument("--registrar", action="store_true")
    operacao.add_argument("--pendentes", choices=TIPOS, metavar="TIPO", help="listar IDs pendentes de um tipo em JSONL")
    parser.add_argument("--apos", metavar="ID", help="continuar depois deste ID na ordem da listagem")
    parser.add_argument("--limite", type=int, help="número máximo de pendentes a listar (padrão 50)")
    parser.add_argument("--revisoes", type=Path, nargs="+", default=[], help="decisões individuais em JSONL")
    args = parser.parse_args()
    if args.revisoes and not args.registrar:
        parser.error("Para gravar as revisões, use --registrar.")
    if (args.apos is not None or args.limite is not None) and not args.pendentes:
        parser.error("--apos e --limite são opções da listagem --pendentes.")
    if args.limite is not None and args.limite < 1:
        parser.error("O limite deve ser positivo.")
    with closing(conectar(WIKI)) as db:
        if args.pendentes:
            for item in db.execute("SELECT id,tipo,assinatura,pagina FROM inventario "
                                   "WHERE estado='pendente' AND tipo=? AND id>? ORDER BY id LIMIT ?",
                                   (args.pendentes, args.apos or "", args.limite or 50)):
                print(json.dumps(dict(item), ensure_ascii=False))
        elif args.registrar:
            registrar(db, WIKI, args.revisoes)
            with db:
                sincronizar(db, WIKI)
        if not args.pendentes:
            print(json.dumps(conferir(db, WIKI), ensure_ascii=False, indent=2))
