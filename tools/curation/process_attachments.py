import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


from tools import ROOT
ATTACHMENTS = ROOT / "dados" / "zulip" / "anexos"


def comando(nome, *opcoes):
    return [sys.executable, "-B", "-X", "utf8", "-m", nome, *opcoes]


def estado():
    origem = ATTACHMENTS / "estado.sqlite3"
    transcricao = ATTACHMENTS / "transcricoes.sqlite3"
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


def run_transcription(comando_transcricao):
    for tentativa in range(3):
        try:
            subprocess.run(comando_transcricao, cwd=ROOT, check=True)
            return
        except subprocess.CalledProcessError as erro:
            if sys.platform != "win32" or erro.returncode != 0x40010004 or tentativa == 2:
                raise
            print("Windows stopped the transcription. Resuming from the last record.", flush=True)
            time.sleep(5)


def watch_download(download, transcrever):
    with subprocess.Popen(download, cwd=ROOT) as processo:
        try:
            while processo.poll() is None:
                run_transcription(transcrever)
                if processo.poll() is None:
                    time.sleep(8)
        except (KeyboardInterrupt, subprocess.CalledProcessError):
            if processo.poll() is None:
                processo.terminate()
            raise
        if processo.returncode != 0:
            raise subprocess.CalledProcessError(processo.returncode, download)


def run(args):
    download = comando("tools.collection.download_attachments", "--interval", str(args.interval))
    transcrever = comando("tools.curation.transcribe_attachments", "--workers", str(args.workers),
                         "--device", args.device)
    if args.model:
        transcrever.extend(("--model", str(args.model.expanduser().resolve())))
    lote = [*transcrever, "--limit", str(args.workers * 24)]
    revisar = ["--retry-denied"] if args.retry_denied else []
    watch_download([*download, *revisar], lote)
    for intervalo in (1.0, 2.0):
        if not estado()["downloads"].get("pendente", 0):
            break
        nova_passagem = comando("tools.collection.download_attachments", "--interval", str(max(args.interval, intervalo)),
                                 "--workers", "2", "--attempts", "2")
        watch_download(nova_passagem, lote)

    run_transcription([*transcrever, "--retry-errors"])
    resultado = estado()
    if resultado["aguardam_transcricao"]:
        raise RuntimeError("Some downloaded files have no transcription record.")
    if not args.transcribe_only:
        subprocess.run(comando("tools.curation.build_attachments"), cwd=ROOT, check=True)
        subprocess.run(comando("tools.curation.build_wiki", "--verify"), cwd=ROOT, check=True)
    print(json.dumps(resultado, ensure_ascii=False, indent=2), flush=True)
    estados = resultado["downloads"]
    return int(any(estados.get(chave, 0) for chave in
                   ("pendente", "nao_verificado", "resposta_ambigua", "redirecionamento_bloqueado")))


def main():
    parser = argparse.ArgumentParser(description='Download, transcribe, and add Zulip attachments to the wiki.')
    parser.add_argument("--interval", type=float, default=0.35,
                        help="Minimum time between Zulip requests.")
    parser.add_argument("--workers", type=int, default=6, help="Number of transcription workers.")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--model", type=Path, help="Local Whisper model.")
    parser.add_argument("--retry-denied", action="store_true")
    parser.add_argument("--transcribe-only", action="store_true",
                        help="Stop after text extraction and transcription.")
    parser.add_argument("--summary", action="store_true", help="Read the checkpoints offline.")
    args = parser.parse_args()
    if not 0.05 <= args.interval <= 60 or args.workers < 1:
        parser.error("Use an interval from 0.05 to 60 seconds and at least one worker.")
    if args.summary:
        print(json.dumps(estado(), ensure_ascii=False, indent=2))
        return 0
    try:
        ATTACHMENTS.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(ATTACHMENTS / "processamento.sqlite3", timeout=0)) as lock:
            try:
                lock.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as erro:
                if erro.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                    raise RuntimeError("A run is in progress. Use --summary.") from erro
                raise
            return run(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as erro:
        print(f'Processing stopped. {erro}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
