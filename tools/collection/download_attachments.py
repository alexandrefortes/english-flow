import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from dataclasses import dataclass
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile
from threading import Event, Lock
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, build_opener


from tools.collection.download_zulip import DESTINATION, RECOVERABLE_HTTP, retry_delay
from tools.collection.list_attachments import NoRedirects, referencias


ZULIP_HOST = "chat.zulip.org"
REDIRECTS = {301, 302, 303, 307, 308}
DENIED = {"indisponivel", "sem_acesso_anonimo"}
HTML = {"text/html", "application/xhtml+xml"}
ROUTE_CONTROL = re.compile(r"[\x00-\x1f\x7f\\]")
SUFFIXES = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp",
    "image/avif": ".avif", "image/bmp": ".bmp", "image/tiff": ".tif",
    "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/wav": ".wav",
    "video/mp4": ".mp4", "video/webm": ".webm", "application/pdf": ".pdf",
    "application/zip": ".zip", "text/plain": ".txt", "application/json": ".json",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS arquivos (
    url TEXT PRIMARY KEY, id TEXT NOT NULL UNIQUE, estado TEXT NOT NULL,
    arquivo TEXT, mime TEXT, bytes INTEGER, sha256 TEXT, detalhe TEXT
);
CREATE TABLE IF NOT EXISTS referencias (
    url TEXT NOT NULL REFERENCES arquivos(url), mensagem_id INTEGER NOT NULL,
    PRIMARY KEY (url, mensagem_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS referencias_mensagem ON referencias(mensagem_id);
"""


@dataclass
class DownloadedFile:
    estado: str
    arquivo: str | None = None
    mime: str | None = None
    bytes: int | None = None
    sha256: str | None = None
    detalhe: str | None = None


class RetryableDownload(Exception):
    def __init__(self, detalhe, retry_after=None, global_=False):
        super().__init__(detalhe)
        self.retry_after = retry_after
        self.global_ = global_


class RateLimiter:
    def __init__(self, intervalo, interromper):
        self.intervalo = intervalo
        self.interromper = interromper
        self.lock = Lock()
        self.proxima = 0.0

    def defer(self, segundos):
        with self.lock:
            self.proxima = max(self.proxima, time.monotonic() + segundos)

    def wait_for_slot(self):
        while not self.interromper.is_set():
            with self.lock:
                agora = time.monotonic()
                espera = self.proxima - agora
                if espera <= 0:
                    self.proxima = agora + self.intervalo
                    return True
            self.interromper.wait(espera)
        return False


def attachment_id(url):
    return "zulip-anexo-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def redirect_target(anterior, location, hosts):
    if not location or re.search(r"[\x00-\x20\x7f]", location):
        return None, "redirecionamento_bloqueado"
    try:
        url = urljoin(anterior, location)
        partes = urlsplit(url)
    except ValueError:
        return None, "redirecionamento_bloqueado"
    host = partes.hostname
    if partes.scheme != "https" or host not in hosts or partes.netloc.lower() not in {host, f"{host}:443"}:
        return None, "redirecionamento_bloqueado"
    if host == ZULIP_HOST:
        path = unquote(partes.path)
        if path.rstrip("/") in {"/login", "/accounts/login"}:
            return None, "sem_acesso_anonimo"
        if (not path.startswith("/user_uploads/") or ROUTE_CONTROL.search(path)
                or any(parte in {".", ".."} for parte in path.split("/"))):
            return None, "redirecionamento_bloqueado"
    return url, None


def write_file(resposta, destino, identificador, interromper):
    mime = (resposta.headers.get("Content-Type") or "").partition(";")[0].strip().lower()
    disposicao = resposta.headers.get_content_disposition()
    nome = resposta.headers.get_filename()
    if (not mime or mime in HTML) and not nome and disposicao != "attachment":
        return DownloadedFile("resposta_ambigua", detalhe="Resposta sem metadados suficientes para confirmar um anexo.")
    mime = mime or "application/octet-stream"
    pasta = destino / "arquivos" / identificador.removeprefix("zulip-anexo-")[:2]
    pasta.mkdir(parents=True, exist_ok=True)
    if not pasta.resolve().is_relative_to(destino.resolve()):
        raise ValueError("The attachment directory is outside the destination.")
    final = pasta / (identificador + SUFFIXES.get(mime, ".bin"))
    esperado = resposta.headers.get("Content-Length")
    esperado = int(esperado) if esperado and esperado.isascii() and esperado.isdecimal() else None
    resumo = hashlib.sha256()
    total = 0
    with NamedTemporaryFile(dir=pasta, suffix=".part", delete=False) as arquivo:
        temporario = Path(arquivo.name)
        try:
            while not interromper.is_set():
                try:
                    bloco = resposta.read(256 * 1024)
                except (OSError, HTTPException) as error:
                    raise RetryableDownload(f"Leitura da resposta interrompida ({type(error).__name__}).") from error
                if not bloco:
                    break
                arquivo.write(bloco)
                resumo.update(bloco)
                total += len(bloco)
            arquivo.close()
            if interromper.is_set():
                return DownloadedFile("pendente", detalhe="Execução interrompida.")
            if esperado is not None and total != esperado:
                raise RetryableDownload(f"Resposta incompleta: {total} de {esperado} bytes.")
            temporario.replace(final)
        finally:
            arquivo.close()
            temporario.unlink(missing_ok=True)
    return DownloadedFile("baixado", final.relative_to(destino).as_posix(), mime, total, resumo.hexdigest())


def attempt_download(opener, url, destino, identificador, limitador, hosts, timeout):
    for _ in range(6):
        if not limitador.wait_for_slot():
            return DownloadedFile("pendente", detalhe="Execução interrompida.")
        pedido = Request(url, headers={"Accept": "*/*", "Accept-Encoding": "identity"}, method="GET")
        try:
            resposta = opener.open(pedido, timeout=timeout)
        except HTTPError as erro:
            with erro:
                code = erro.code
                if code in REDIRECTS:
                    url, estado = redirect_target(url, erro.headers.get("Location"), hosts)
                    if estado:
                        return DownloadedFile(estado, detalhe=f"HTTP {code}")
                    continue
                if code in RECOVERABLE_HTTP:
                    retry_after = erro.headers.get("Retry-After")
                    raise RetryableDownload(f"HTTP {code}", retry_after, bool(retry_after) or code == 429) from erro
                if code in {404, 410}:
                    return DownloadedFile("indisponivel", detalhe=f"HTTP {code}")
                if code in {401, 403}:
                    return DownloadedFile("sem_acesso_anonimo", detalhe=f"HTTP {code}")
                return DownloadedFile("resposta_ambigua", detalhe=f"HTTP {code}")
        except (URLError, OSError, HTTPException) as error:
            raise RetryableDownload(f"Conexão interrompida ({type(error).__name__}).") from error
        with resposta:
            if resposta.status != 200:
                return DownloadedFile("resposta_ambigua", detalhe=f"HTTP {resposta.status}")
            return write_file(resposta, destino, identificador, limitador.interromper)
    return DownloadedFile("redirecionamento_bloqueado", detalhe="Limite de redirecionamentos alcançado.")


def download(url, identificador, destino, limitador, hosts, timeout, tentativas):
    opener = build_opener(NoRedirects())
    for indice in range(1, tentativas + 1):
        try:
            return attempt_download(opener, url, destino, identificador, limitador, hosts, timeout)
        except RetryableDownload as exc:
            delay = retry_delay(exc.retry_after, indice)
            if exc.global_:
                limitador.defer(delay)
            if indice == tentativas or (not exc.global_ and limitador.interromper.wait(delay)):
                return DownloadedFile("pendente", detalhe=str(exc))
        except PermissionError as exc:
            return DownloadedFile("pendente", detalhe=f"Acesso local temporariamente indisponível ({exc.errno}).")
    raise AssertionError("É necessária pelo menos uma tentativa.")


def read_cache(caminho):
    if not caminho.is_file():
        return {}
    with closing(sqlite3.connect(caminho.resolve().as_uri() + "?mode=ro", uri=True)) as banco:
        return {url: json.loads(valor) for url, valor in banco.execute("SELECT url, resultado FROM verificacoes")}


def preparar(banco, anexos, cache):
    def arquivos():
        for url in anexos:
            anterior = cache.get(url, {})
            estado = anterior.get("status")
            yield url, attachment_id(url), estado if estado in DENIED else "nao_verificado", anterior.get("detalhe")

    with banco:
        banco.executemany("INSERT OR IGNORE INTO arquivos(url,id,estado,detalhe) VALUES (?,?,?,?)", arquivos())
        banco.executemany("INSERT OR IGNORE INTO referencias VALUES (?,?)",
                          ((url, mensagem["id"]) for url, mensagens in anexos.items() for mensagem in mensagens))


def file_is_present(destino, caminho, tamanho):
    if not caminho or tamanho is None:
        return False
    try:
        arquivo = (destino / caminho).resolve()
        return arquivo.is_relative_to(destino) and arquivo.is_file() and arquivo.stat().st_size == tamanho
    except OSError:
        return False


def candidatos(banco, anexos, cache, destino, rever_negados):
    registros = []
    for url, identificador, estado, caminho, tamanho in banco.execute("SELECT url,id,estado,arquivo,bytes FROM arquivos"):
        if url not in anexos or estado in DENIED and not rever_negados:
            continue
        if estado == "baixado":
            if file_is_present(destino, caminho, tamanho):
                continue
            salvar(banco, url, DownloadedFile("pendente", detalhe="Arquivo local ausente ou com tamanho diferente."))
            estado = "pendente"
        if estado == "pendente":
            prioridade = 3
        elif cache.get(url, {}).get("status") == "publico":
            prioridade = 0
        else:
            prioridade = 1 if estado == "nao_verificado" else 2
        registros.append((prioridade, url, identificador))
    return [(url, identificador) for _, url, identificador in sorted(registros)]


def salvar(banco, url, resultado):
    with banco:
        banco.execute("UPDATE arquivos SET estado=?,arquivo=?,mime=?,bytes=?,sha256=?,detalhe=? WHERE url=?",
                      (resultado.estado, resultado.arquivo, resultado.mime, resultado.bytes,
                       resultado.sha256, resultado.detalhe, url))


def resumo(banco):
    return {
        "estados": dict(banco.execute("SELECT estado, count(*) FROM arquivos GROUP BY estado ORDER BY estado")),
        "urls": banco.execute("SELECT count(*) FROM arquivos").fetchone()[0],
        "referencias": banco.execute("SELECT count(*) FROM referencias").fetchone()[0],
        "bytes_baixados": banco.execute("SELECT coalesce(sum(bytes),0) FROM arquivos WHERE estado='baixado'").fetchone()[0],
    }


def run(args, banco):
    anexos, mensagens, _ = referencias(args.input)
    cache = read_cache(args.cache)
    preparar(banco, anexos, cache)
    pendentes = candidatos(banco, anexos, cache, args.destination, args.retry_denied)[:args.limit]
    print(f'{mensagens:,} messages and {len(anexos):,} distinct URLs. This run will check {len(pendentes):,} URLs.', flush=True)
    interromper = Event()
    limitador = RateLimiter(args.interval, interromper)
    hosts = {ZULIP_HOST, *args.allow_host}
    contagem = 0
    tamanho_lote = args.workers * 4
    with ThreadPoolExecutor(max_workers=args.workers) as trabalhadores:
        try:
            for inicio in range(0, len(pendentes), tamanho_lote):
                lote = {
                    trabalhadores.submit(download, url, chave, args.destination, limitador, hosts,
                                          args.timeout, args.attempts): url
                    for url, chave in pendentes[inicio:inicio + tamanho_lote]
                }
                for tarefa in as_completed(lote):
                    salvar(banco, lote[tarefa], tarefa.result())
                    contagem += 1
                    if contagem % 100 == 0 or contagem == len(pendentes):
                        print(f'Processed {contagem:,} of {len(pendentes):,} URLs.', flush=True)
        finally:
            interromper.set()


def main():
    parser = argparse.ArgumentParser(description='Download the attachments from the local Zulip inventory.')
    parser.add_argument("--input", type=Path, default=DESTINATION / "mensagens.jsonl")
    parser.add_argument("--destination", type=Path, default=DESTINATION / "anexos")
    parser.add_argument("--cache", type=Path, help="Inventory database. The default is anexos.sqlite3 beside the input file.")
    parser.add_argument("--limit", type=int, help="Maximum number of URLs to check in this run.")
    parser.add_argument("--summary", action="store_true", help="Read the checkpoint offline.")
    parser.add_argument("--retry-denied", action="store_true", help="Try previously denied or unavailable URLs again.")
    parser.add_argument("--allow-host", action="append", default=[], metavar="HOST",
                        help="Allow an exact HTTPS redirect host documented by the provider.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--interval", type=float, default=0.2, help="Minimum time between requests in seconds.")
    parser.add_argument("--timeout", type=float, default=30, help="Socket idle timeout in seconds.")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    if ((args.limit is not None and args.limit < 1) or not 1 <= args.workers <= 32
            or not 0.05 <= args.interval <= 60 or not 0.1 <= args.timeout <= 300 or not 1 <= args.attempts <= 10):
        parser.error("Use positive values within the permitted limits.")
    args.allow_host = [host.lower() for host in args.allow_host]
    if any(not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host) for host in args.allow_host):
        parser.error("Enter a full hostname without a scheme, port, or wildcard.")
    args.input = args.input.resolve()
    args.cache = (args.cache or args.input.with_name("anexos.sqlite3")).resolve()
    args.destination = args.destination.resolve()
    estado = args.destination / "estado.sqlite3"
    try:
        if args.summary:
            with closing(sqlite3.connect(estado.as_uri() + "?mode=ro", uri=True)) as banco:
                print(json.dumps(resumo(banco), ensure_ascii=False, indent=2))
            return 0
        args.destination.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(estado, timeout=30)) as banco:
            banco.executescript("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; " + SCHEMA)
            run(args, banco)
            print(json.dumps(resumo(banco), ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
