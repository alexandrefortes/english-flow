"""Divide as imagens do acervo em lotes para revisão visual no Codex Desktop."""

import argparse
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time

from construir_grafo import PROJETO, abrir_leitura
from executar_terra_ocr import revisar_lote
from midias_revisao_ocr import zip_com_imagens
from publicar_revisao_ocr import publicar, verificar_fechamento
from recibos_ocr import ler_recibo, precisa_releitura


def inventario(dados):
    anexos = dados / "zulip/anexos"
    anteriores = json.loads((anexos / "revisoes-manuais.json").read_text(encoding="utf-8"))
    correcoes = {(r["id"], r["sha256"]): r for r in anteriores}
    itens = {}
    with abrir_leitura(anexos / "estado.sqlite3") as db:
        db.execute("ATTACH DATABASE ? AS t", ((anexos / "transcricoes.sqlite3").as_uri() + "?mode=ro",))
        for chave, origem, sha, mime, metodo, texto, estado, detalhe in db.execute("""
            SELECT a.id,a.arquivo,a.sha256,a.mime,t.metodo,t.texto,t.estado,t.detalhe
            FROM arquivos a JOIN t.transcricoes t USING (id,sha256)
            WHERE a.estado='baixado' ORDER BY a.id
        """):
            caminho = (anexos / origem).resolve()
            if not caminho.is_relative_to(anexos):
                raise ValueError(f"Original fora do acervo: {chave}")
            imagem_com_erro = metodo == "validacao-ou-extracao" and (mime or "").startswith("image/") and (
                "tesseract" in (detalhe or "").lower() or mime in {"image/gif", "image/heic"}
            )
            tem_ocr = "tesseract" in metodo or "+ocr" in metodo or imagem_com_erro
            if not tem_ocr and not (metodo == "zip-conteudo" and zip_com_imagens(caminho)):
                continue
            if (chave, sha) in correcoes:
                anterior = correcoes[chave, sha]
                texto, estado, detalhe = anterior["texto"], anterior["estado"], anterior["detalhe"]
            itens[chave] = dict(id=chave, sha256=sha, caminho=str(caminho), mime=mime or "",
                                metodo=metodo, texto=texto, estado=estado, detalhe=detalhe)
    with abrir_leitura(dados / "wiki/grafo.sqlite3") as db:
        for chave, origem, texto, estado in db.execute(
            "SELECT id,caminho,texto,estado FROM nos WHERE tipo='captura' AND caminho IS NOT NULL"
        ):
            caminho = (dados / origem).resolve()
            if not caminho.is_relative_to(dados):
                raise ValueError(f"Captura fora do acervo: {chave}")
            with caminho.open("rb") as f:
                sha = hashlib.file_digest(f, "sha256").hexdigest()
            itens[chave] = dict(id=chave, sha256=sha, caminho=str(caminho), mime="image/" + caminho.suffix[1:],
                                metodo="tesseract-doist", texto=texto, estado=estado, detalhe="")
    return itens


def resumo(db, pasta):
    etapas = dict(db.execute("SELECT estado, count(*) FROM fila GROUP BY estado"))
    registro = pasta / "publicados.json"
    publicados = len(json.loads(registro.read_bytes())) if registro.is_file() else 0
    return {"inventariados": sum(etapas.values()), "etapas": etapas, "publicados": publicados}


def revisado(pasta, item):
    caminho = pasta / "terra" / (item["id"] + ".json")
    if not caminho.is_file():
        return False
    try:
        recibo = ler_recibo(caminho)
    except ValueError:
        return False
    if precisa_releitura(recibo):
        copia = pasta / "primeira-leitura" / caminho.name
        if not copia.exists():
            copia.parent.mkdir(exist_ok=True)
            shutil.copyfile(caminho, copia)
        return False
    return recibo["sha256"] == item["sha256"]


def preparar(db, itens, pasta):
    db.execute("""CREATE TABLE IF NOT EXISTS fila (
        id TEXT PRIMARY KEY, sha TEXT NOT NULL, metodo TEXT NOT NULL, estado TEXT NOT NULL,
        erro TEXT, tentativas INTEGER NOT NULL DEFAULT 0)""")
    with db:
        for chave, item in itens.items():
            existente = db.execute("SELECT sha,estado FROM fila WHERE id=?", (chave,)).fetchone()
            estado = "pendente"
            erro = None
            if revisado(pasta, item):
                estado = "revisado"
            if existente and existente[0] == item["sha256"] and existente[1] == "falha" and estado == "pendente":
                continue
            if not Path(item["caminho"]).stat().st_size:
                estado = "sem_imagem"
                erro = "O arquivo de origem tem zero bytes."
            db.execute("""INSERT INTO fila(id,sha,metodo,estado,erro) VALUES (?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET sha=excluded.sha,metodo=excluded.metodo,estado=excluded.estado,
                erro=excluded.erro,tentativas=CASE WHEN fila.sha=excluded.sha THEN fila.tentativas ELSE 0 END""",
                (chave, item["sha256"], item["metodo"], estado, erro))
        db.execute("CREATE TEMP TABLE inventario_atual(id TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO inventario_atual VALUES (?)", ((chave,) for chave in itens))
        db.execute("DELETE FROM fila WHERE id NOT IN (SELECT id FROM inventario_atual)")


def lotes(db, itens, tamanho, limite):
    selecionados = [itens[i] for i, in db.execute(
        """SELECT id FROM fila WHERE estado='pendente'
        ORDER BY CASE WHEN id LIKE 'doist-%' THEN 0 WHEN metodo='tesseract-imagem' THEN 1 ELSE 2 END,id"""
    )]
    if limite is not None:
        selecionados = selecionados[:limite]
    fila = deque()
    leves = []
    for item in selecionados:
        if item["metodo"] in {"tesseract-imagem", "tesseract-doist"}:
            leves.append(item)
            if len(leves) == tamanho:
                fila.append(leves)
                leves = []
        else:
            fila.append([item])
    if leves:
        fila.appendleft(leves)
    return fila


def processar(args, db, pasta):
    dados = pasta.parent
    itens = inventario(dados)
    preparar(db, itens, pasta)
    if args.repetir_falhas:
        with db:
            db.execute("UPDATE fila SET estado='pendente',tentativas=0,erro=NULL WHERE estado='falha'")
    fila = lotes(db, itens, args.lote, args.limite)
    print(json.dumps(resumo(db, pasta), ensure_ascii=False), flush=True)
    novos_recibos = 0
    ultima_publicacao = time.monotonic()
    pausa_ate = 0.0
    pausas = 0
    trabalhos = {}
    with ThreadPoolExecutor(max_workers=args.trabalhadores) as pool:
        while trabalhos or fila:
            while fila and len(trabalhos) < args.trabalhadores and time.monotonic() >= pausa_ate:
                lote = []
                for item in fila.popleft():
                    if revisado(pasta, item):
                        with db:
                            db.execute("UPDATE fila SET estado='revisado',erro=NULL WHERE id=?", (item["id"],))
                        novos_recibos += 1
                    else:
                        lote.append(item)
                if not lote:
                    continue
                futuro = pool.submit(revisar_lote, args.executavel, lote, dados, pasta / "temporarios")
                trabalhos[futuro] = lote
            if not trabalhos:
                if not fila:
                    break
                time.sleep(min(30, max(1, pausa_ate - time.monotonic())))
                continue
            feitos, _ = wait(trabalhos, timeout=30, return_when=FIRST_COMPLETED)
            for futuro in feitos:
                lote = trabalhos.pop(futuro)
                erro = futuro.exception()
                restantes = []
                for item in lote:
                    if revisado(pasta, item):
                        with db:
                            db.execute("UPDATE fila SET estado='revisado',erro=NULL WHERE id=?", (item["id"],))
                        novos_recibos += 1
                    else:
                        restantes.append(item)
                if not restantes:
                    if not erro:
                        pausas = 0
                    continue
                motivo = str(erro or "O executor não entregou recibo.")
                alerta = motivo.lower()
                if any(s in alerta for s in ("rate_limit", "usage limit", "usage_limit", "quota", "429",
                                             "connection", "temporarily unavailable", "server_error", "503")):
                    minutos = min(60, 2 ** min(6, pausas))
                    pausas += 1
                    pausa_ate = max(pausa_ate, time.monotonic() + 60 * minutos)
                    print(f"Serviço indisponível. Nova tentativa em {minutos} min. {motivo[-300:]}", flush=True)
                    fila.appendleft(restantes)
                elif any(s in alerta for s in ("model_not_found", "not supported when", "unauthorized",
                                               "not logged", "authentication", "permission denied", "401")):
                    raise RuntimeError(f"Acesso ao modelo interrompido: {motivo[-550:]}") from erro
                elif len(restantes) > 1:
                    meio = len(restantes) // 2
                    fila.appendleft(restantes[meio:])
                    fila.appendleft(restantes[:meio])
                else:
                    chave = restantes[0]["id"]
                    with db:
                        db.execute("UPDATE fila SET tentativas=tentativas+1,erro=? WHERE id=?", (motivo[-1200:], chave))
                        if db.execute("SELECT tentativas FROM fila WHERE id=?", (chave,)).fetchone()[0] < 2:
                            fila.append(restantes)
                        else:
                            db.execute("UPDATE fila SET estado='falha' WHERE id=?", (chave,))
                            print(f"Falha isolada {chave}: {motivo[-180:]}", flush=True)
            if novos_recibos and (novos_recibos >= 192 or time.monotonic() - ultima_publicacao >= 300):
                resultado = publicar(dados, PROJETO / "wiki/local")
                print(json.dumps({**resumo(db, pasta), "publicacao": resultado}, ensure_ascii=False), flush=True)
                novos_recibos = 0
                ultima_publicacao = time.monotonic()
    resultado = publicar(dados, PROJETO / "wiki/local")
    print(json.dumps({**resumo(db, pasta), "publicacao": resultado}, ensure_ascii=False), flush=True)
    if args.limite is None:
        conferidos = verificar_fechamento(dados, PROJETO / "wiki/local")
        print(json.dumps({"fechamento": conferidos}, ensure_ascii=False), flush=True)
    return int(bool(resultado.get("invalidos") or db.execute("SELECT 1 FROM fila WHERE estado='falha'").fetchone()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modo", choices=("revisar", "resumo", "inventario"))
    parser.add_argument("--executavel", type=Path, help="Executável do Codex Desktop com acesso ao Terra")
    parser.add_argument("--trabalhadores", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--lote", type=int, choices=range(1, 9), default=6)
    parser.add_argument("--limite", type=int)
    parser.add_argument("--repetir-falhas", action="store_true")
    args = parser.parse_args()
    pasta = PROJETO / "dados/revisao-ocr"
    pasta.mkdir(exist_ok=True, parents=True)
    if args.modo == "inventario":
        print(json.dumps(Counter(i["metodo"] for i in inventario(pasta.parent).values()), indent=2))
        return 0
    if args.modo == "resumo":
        with abrir_leitura(pasta / "fila.sqlite3") as db:
            print(json.dumps(resumo(db, pasta), indent=2))
        return 0
    if not args.executavel or not args.executavel.is_file() or (args.limite is not None and args.limite < 1):
        parser.error("Informe um executável e um limite positivo, se usar --limite.")
    with closing(sqlite3.connect(pasta / "execucao.sqlite3", timeout=1)) as guarda:
        guarda.execute("BEGIN IMMEDIATE")
        with closing(sqlite3.connect(pasta / "fila.sqlite3")) as db:
            return processar(args, db, pasta)


if __name__ == "__main__":
    raise SystemExit(main())
