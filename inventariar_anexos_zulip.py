"""Inventaria anexos citados no JSONL público do Zulip e verifica o acesso anônimo."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from http.client import HTTPException
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote_from_bytes, unquote_to_bytes, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from baixar_zulip import DESTINATION, RECOVERABLE_HTTP, ROOT, retry_delay, save_json, utc


UPLOAD = re.compile(
    r"(?<![\w/@:.-])(?:(?:(?:https?:)?//)?chat\.zulip\.org/|/?)user_uploads/(?:download/)?"
    r"(\d+/(?:[A-Za-z0-9_-]+/){1,2}[^\s/#?<>()\[\]'\"`\\]+)",
    re.IGNORECASE,
)
ESTADOS_VERIFICADOS = {"publico", "indisponivel", "sem_acesso_anonimo"}


class SemRedirecionar(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def referencias(caminho):
    anexos = defaultdict(list)
    sha256 = hashlib.sha256()
    count = 0
    with caminho.open("rb") as source:
        for line in source:
            sha256.update(line)
            message = json.loads(line)
            count += 1
            urls = set()
            content = message["content"]
            for match in UPLOAD.finditer(content):
                candidate = match[1]
                before = content[match.start() - 1:match.start()]
                if before not in {"(", "<", "`", "\"", "'"}:
                    candidate = candidate.rstrip(".,;!:")
                path = unquote_to_bytes(candidate)
                parts = path.split(b"/")
                if len(parts) != len(candidate.split("/")) or any(part in {b"", b".", b".."} for part in parts):
                    continue
                urls.add(f"{ROOT}/user_uploads/{quote_from_bytes(path)}")
            for url in sorted(urls):
                anexos[url].append({
                    "id": message["id"],
                    "stream_id": message["stream_id"],
                    "channel": message["channel"],
                    "topic": message["topic"],
                    "url": message["url"],
                })
    return anexos, count, sha256.hexdigest()


def verificar(url, esperar, adiar):
    opener = build_opener(SemRedirecionar())
    method = "HEAD"
    for attempt in range(1, 5):
        if not esperar():
            return None
        request = Request(url, headers={"Accept": "*/*"}, method=method)
        if method == "GET":
            request.add_header("Range", "bytes=0-0")
        try:
            with opener.open(request, timeout=20) as response:
                code = response.status
                headers = response.headers
            detail = None
        except HTTPError as error:
            with error:
                code = error.code
                headers = error.headers
            detail = f"HTTP {code}"
        except (URLError, HTTPException, TimeoutError) as error:
            code = None
            headers = {}
            detail = str(error)

        if code in {405, 501} and method == "HEAD":
            method = "GET"
            continue
        if code is None or code in RECOVERABLE_HTTP:
            adiar(retry_delay(headers.get("Retry-After"), attempt))
            continue
        break

    content_type = headers.get("Content-Type")
    disposition = headers.get("Content-Disposition")
    location = urlparse(headers.get("Location", "")).path.rstrip("/")
    if code in {200, 206} and (disposition or (content_type and not content_type.lower().startswith("text/html"))):
        status = "publico"
    elif code in {404, 410}:
        status = "indisponivel"
    elif code in {401, 403} or (code in {301, 302, 303, 307, 308} and location == "/login"):
        status = "sem_acesso_anonimo"
    else:
        status = "pendente"
        detail = detail or "Resposta sem evidência suficiente para confirmar o arquivo."
    return {
        "status": status,
        "http": code,
        "metodo": method,
        "content_type": content_type,
        "content_length": headers.get("Content-Length"),
        "content_range": headers.get("Content-Range"),
        "content_disposition": disposition,
        "tentativas": attempt,
        "verificado_em_utc": utc(),
        "detalhe": detail,
    }


def inventariar(diretorio, limite=None):
    """Reutiliza resultados persistidos e exporta o inventário do JSONL atual."""
    anexos, total_mensagens, sha256 = referencias(diretorio / "mensagens.jsonl")
    lock = threading.Lock()
    interromper = threading.Event()
    proxima_consulta = 0.0

    def adiar(segundos):
        nonlocal proxima_consulta
        with lock:
            proxima_consulta = max(proxima_consulta, time.monotonic() + segundos)

    def esperar():
        nonlocal proxima_consulta
        while not interromper.is_set():
            with lock:
                now = time.monotonic()
                delay = proxima_consulta - now
                if delay <= 0:
                    proxima_consulta = now + 0.2
                    return True
            interromper.wait(delay)
        return False

    with closing(sqlite3.connect(diretorio / "anexos.sqlite3", timeout=30)) as database:
        database.execute("CREATE TABLE IF NOT EXISTS verificacoes (url TEXT PRIMARY KEY, resultado TEXT NOT NULL)")
        resultados = {
            url: json.loads(data)
            for url, data in database.execute("SELECT url, resultado FROM verificacoes")
        }
        pendentes = [url for url in anexos if resultados.get(url, {}).get("status") not in ESTADOS_VERIFICADOS]
        lote = pendentes[:limite]
        print(f"Anexos do Zulip: {len(anexos)} URLs, {len(lote)} a verificar nesta execução.", flush=True)
        with ThreadPoolExecutor(max_workers=4) as executor:
            try:
                for start in range(0, len(lote), 100):
                    consultas = {executor.submit(verificar, url, esperar, adiar): url for url in lote[start:start + 100]}
                    for consulta in as_completed(consultas):
                        url, result = consultas[consulta], consulta.result()
                        with database:
                            database.execute("INSERT OR REPLACE INTO verificacoes VALUES (?, ?)", (url, json.dumps(result)))
                        resultados[url] = result
                    processed = min(start + 100, len(lote))
                    print(f"Anexos consultados nesta execução: {processed}/{len(lote)}", flush=True)
            finally:
                interromper.set()

    arquivo = diretorio / "anexos.jsonl"
    temporario = arquivo.with_suffix(".jsonl.tmp")
    estados = Counter()
    with temporario.open("w", encoding="utf-8", newline="\n") as output:
        for url, mensagens in sorted(anexos.items()):
            acesso = resultados.get(url, {"status": "nao_verificado"})
            estados[acesso["status"]] += 1
            output.write(json.dumps({"url": url, "mensagens": mensagens, **acesso}, ensure_ascii=False) + "\n")
    temporario.replace(arquivo)

    resumo = {
        "origem": "mensagens.jsonl",
        "origem_sha256": sha256,
        "mensagens_lidas": total_mensagens,
        "urls_unicas": len(anexos),
        "referencias": sum(map(len, anexos.values())),
        "estados": dict(sorted(estados.items())),
        "pendencias": estados["pendente"] + estados["nao_verificado"],
        "resumo_em_utc": utc(),
    }
    save_json(diretorio / "anexos-resumo.json", resumo)
    return resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diretorio", type=Path, default=DESTINATION, help="pasta do mensagens.jsonl")
    parser.add_argument("--limite", type=int, help="máximo de URLs para verificar nesta execução")
    args = parser.parse_args()
    if args.limite is not None and args.limite < 1:
        parser.error("--limite deve ser positivo")
    resumo = inventariar(args.diretorio, args.limite)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return int(bool(resumo["pendencias"]) and args.limite is None)


if __name__ == "__main__":
    raise SystemExit(main())
