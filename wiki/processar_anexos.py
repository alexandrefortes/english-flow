"""Baixa, transcreve e incorpora os anexos do Zulip à wiki local."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


WIKI = Path(__file__).resolve().parent
ROOT = WIKI.parent
ANEXOS = ROOT / "dados" / "zulip" / "anexos"


def comando(nome, *opcoes):
    return [sys.executable, "-B", "-X", "utf8", str(WIKI / nome), *opcoes]


def estado():
    origem = ANEXOS / "estado.sqlite3"
    transcricao = ANEXOS / "transcricoes.sqlite3"
    if not origem.is_file():
        return {"downloads": {}, "transcricoes": {}, "aguardam_transcricao": 0}
    with closing(sqlite3.connect(origem.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        downloads = dict(db.execute("SELECT estado, count(*) FROM arquivos GROUP BY estado"))
        transcricoes = {}
        faltam = downloads.get("baixado", 0)
        if transcricao.is_file():
            db.execute("ATTACH DATABASE ? AS textos", (transcricao.as_uri() + "?mode=ro",))
            if db.execute("SELECT 1 FROM textos.sqlite_master WHERE name='transcricoes'").fetchone():
                transcricoes = dict(db.execute("""
                    SELECT t.estado, count(*) FROM textos.transcricoes t
                    JOIN arquivos a ON a.id=t.id AND a.sha256=t.sha256
                    WHERE a.estado='baixado' GROUP BY t.estado
                """))
                faltam -= sum(transcricoes.values())
    return {"downloads": downloads, "transcricoes": transcricoes, "aguardam_transcricao": faltam}


def executar_transcricao(comando_transcricao):
    for tentativa in range(3):
        try:
            subprocess.run(comando_transcricao, cwd=ROOT, check=True)
            return
        except subprocess.CalledProcessError as erro:
            if sys.platform != "win32" or erro.returncode != 0x40010004 or tentativa == 2:
                raise
            print("A transcrição foi interrompida pelo Windows. Retomando do último registro.", flush=True)
            time.sleep(5)


def acompanhar_download(download, transcrever):
    with subprocess.Popen(download, cwd=ROOT) as processo:
        try:
            while processo.poll() is None:
                executar_transcricao(transcrever)
                if processo.poll() is None:
                    time.sleep(8)
        except (KeyboardInterrupt, subprocess.CalledProcessError):
            if processo.poll() is None:
                processo.terminate()
            raise
        if processo.returncode != 0:
            raise subprocess.CalledProcessError(processo.returncode, download)


def executar(args):
    download = comando("baixar_anexos.py", "--intervalo", str(args.intervalo))
    transcrever = comando("transcrever_anexos.py", "--trabalhadores", str(args.trabalhadores),
                         "--dispositivo", args.dispositivo)
    if args.modelo:
        transcrever.extend(("--modelo", str(args.modelo.expanduser().resolve())))
    lote = [*transcrever, "--limite", str(args.trabalhadores * 24)]
    revisar = ["--rever-negados"] if args.rever_negados else []
    acompanhar_download([*download, *revisar], lote)
    for intervalo in (1.0, 2.0):
        if not estado()["downloads"].get("pendente", 0):
            break
        nova_passagem = comando("baixar_anexos.py", "--intervalo", str(max(args.intervalo, intervalo)),
                                 "--trabalhadores", "2", "--tentativas", "2")
        acompanhar_download(nova_passagem, lote)

    executar_transcricao([*transcrever, "--refazer-falhas"])
    resultado = estado()
    if resultado["aguardam_transcricao"]:
        raise RuntimeError("Ainda há arquivos baixados sem registro de transcrição.")
    if not args.so_transcrever:
        subprocess.run(comando("ingerir_anexos.py"), cwd=ROOT, check=True)
        subprocess.run(comando("ingerir_acervo.py", "--verificar"), cwd=ROOT, check=True)
    print(json.dumps(resultado, ensure_ascii=False, indent=2), flush=True)
    estados = resultado["downloads"]
    return int(any(estados.get(chave, 0) for chave in
                   ("pendente", "nao_verificado", "resposta_ambigua", "redirecionamento_bloqueado")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervalo", type=float, default=0.35,
                        help="Intervalo global entre requisições ao Zulip")
    parser.add_argument("--trabalhadores", type=int, default=6, help="Trabalhadores da transcrição")
    parser.add_argument("--dispositivo", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--modelo", type=Path, help="Modelo Whisper local")
    parser.add_argument("--rever-negados", action="store_true")
    parser.add_argument("--so-transcrever", action="store_true",
                        help="Termina após registrar a extração e a transcrição")
    parser.add_argument("--resumo", action="store_true", help="Consulta os checkpoints sem rede")
    args = parser.parse_args()
    if not 0.05 <= args.intervalo <= 60 or args.trabalhadores < 1:
        parser.error("Use um intervalo entre 0,05 e 60 segundos e pelo menos um trabalhador.")
    if args.resumo:
        print(json.dumps(estado(), ensure_ascii=False, indent=2))
        return 0
    try:
        ANEXOS.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(ANEXOS / "processamento.sqlite3", timeout=0)) as lock:
            try:
                lock.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as erro:
                if erro.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                    raise RuntimeError("Já há uma execução em andamento. Use --resumo.") from erro
                raise
            return executar(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as erro:
        print(f"Processamento interrompido. {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
