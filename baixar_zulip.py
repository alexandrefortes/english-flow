"""Baixa o histórico público na web de chat.zulip.org."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
from http.client import HTTPException
from http.cookiejar import CookieJar
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import NamedTemporaryFile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


ROOT = "https://chat.zulip.org"
PUBLIC_NARROW = [{"operator": "channels", "operand": "web-public"}]
DESTINATION = Path(__file__).resolve().parent / "dados" / "zulip"
RECOVERABLE_HTTP = {408, 429, 500, 502, 503, 504}
CHANNEL_FIELDS = (
    "stream_id", "name", "is_web_public", "is_archived", "first_message_id",
    "message_retention_days",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY,
    stream_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_full_name TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    datetime_utc TEXT NOT NULL,
    url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paginas (
    numero INTEGER PRIMARY KEY,
    ancora TEXT NOT NULL UNIQUE,
    solicitadas INTEGER NOT NULL,
    coletada_em_utc TEXT NOT NULL,
    menor_id INTEGER,
    maior_id INTEGER,
    recebidas INTEGER NOT NULL,
    gravadas INTEGER NOT NULL,
    found_oldest INTEGER NOT NULL,
    found_newest INTEGER NOT NULL,
    found_anchor INTEGER NOT NULL,
    history_limited INTEGER
);
CREATE INDEX IF NOT EXISTS mensagens_canal_topico_id ON mensagens(stream_id, topic, id);
"""


def utc(timestamp=None):
    value = datetime.now(timezone.utc) if timestamp is None else datetime.fromtimestamp(timestamp, timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def retry_delay(retry_after, attempt):
    if retry_after:
        try:
            return max(0, float(retry_after))
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return min(60, 2 ** attempt)


def read_http(request, opener=urlopen):
    for attempt in range(1, 8):
        try:
            with opener(request, timeout=45) as response:
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except HTTPError as error:
            if error.code not in RECOVERABLE_HTTP or attempt == 7:
                raise
            delay = retry_delay(error.headers.get("Retry-After"), attempt)
            failure = str(error)
            error.close()
        except (URLError, HTTPException, TimeoutError, EOFError) as error:
            if attempt == 7:
                raise
            delay = retry_delay(None, attempt)
            failure = str(error)
        print(f"{utc()} tentativa {attempt}: {failure}; retomando em {delay:.1f} s", file=sys.stderr, flush=True)
        time.sleep(delay)


def fetch_page(anchor, num_before, narrow=PUBLIC_NARROW, *, num_after=0):
    query = urlencode({
        "narrow": json.dumps(narrow, separators=(",", ":")),
        "anchor": anchor,
        "num_before": num_before,
        "num_after": num_after,
        "include_anchor": "true" if anchor == "newest" else "false",
        "apply_markdown": "false",
        "allow_empty_topic_name": "true",
    })
    request = Request(
        f"{ROOT}/json/messages?{query}",
        headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
    )
    response = json.loads(read_http(request))
    if response["result"] != "success":
        raise ValueError(response.get("msg") or response["result"])
    return response


def fetch_channels():
    # O cliente web usa uma sessão anônima com o token CSRF da página inicial.
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies)).open
    read_http(f"{ROOT}/", opener)
    token = next((cookie.value for cookie in cookies if cookie.name in {"__Host-csrftoken", "csrftoken"}), None)
    if token is None:
        raise ValueError("A página anônima do Zulip não forneceu cookie CSRF.")
    form = urlencode({
        "fetch_event_types": '["subscription"]',
        "event_types": "[]",
        "client_capabilities": '{"notification_settings_null":true,"archived_channels":true}',
    }).encode("ascii")
    request = Request(f"{ROOT}/json/register", data=form, headers={
        "Accept-Encoding": "gzip",
        "Referer": f"{ROOT}/",
        "X-CSRFToken": token,
        "X-Requested-With": "XMLHttpRequest",
    })
    data = json.loads(read_http(request, opener))
    if data["result"] != "success":
        raise ValueError(data.get("msg") or data["result"])
    channels = {
        channel["stream_id"]: {field: channel.get(field) for field in CHANNEL_FIELDS}
        for key in ("subscriptions", "unsubscribed", "never_subscribed")
        for channel in data[key]
        if channel["is_web_public"]
    }
    return {
        "endpoint": request.full_url,
        "captured_utc": utc(),
        "server_version": data["zulip_version"],
        "archived_channels_requested": True,
        "channels": [channels[stream_id] for stream_id in sorted(channels)],
    }


def channel_inventory():
    try:
        return fetch_channels()
    except (URLError, HTTPException, TimeoutError, OSError, ValueError, KeyError) as error:
        print(f"{utc()} inventário indisponível: {error}", file=sys.stderr, flush=True)
        return {"endpoint": f"{ROOT}/json/register", "captured_utc": utc(), "error": str(error), "channels": []}


def oldest_probe():
    try:
        response = fetch_page("oldest", 0, num_after=1)
        if not response["found_oldest"] or len(response["messages"]) > 1:
            raise ValueError("O servidor não confirmou o primeiro intervalo do histórico.")
        observed = next(iter(response["messages"]), None)
        return {
            "captured_utc": utc(),
            "id": observed["id"] if observed else None,
            "datetime_utc": utc(observed["timestamp"]) if observed else None,
            "history_limited": response.get("history_limited"),
        }
    except (URLError, HTTPException, OSError, ValueError, KeyError) as error:
        return {"captured_utc": utc(), "error": str(error)}


def validate_page(response, anchor, count):
    messages = response["messages"]
    ids = [message["id"] for message in messages]
    if ids != sorted(set(ids)) or len(ids) > count:
        raise ValueError("A página contém IDs fora de ordem, repetidos ou excede o tamanho solicitado.")
    if anchor == "newest":
        if not response["found_newest"]:
            raise ValueError("A primeira página veio sem found_newest.")
    elif response["anchor"] != anchor or response["found_anchor"] or (ids and ids[-1] >= anchor):
        raise ValueError(f"A página não respeitou a âncora exclusiva {anchor}.")
    if not ids and not response["found_oldest"]:
        raise ValueError("A página não avançou e o servidor não confirmou o início do histórico.")
    for message in messages:
        if message["type"] != "stream" or message["content_type"] != "text/x-markdown":
            raise ValueError(f"Tipo inesperado na mensagem {message['id']}.")
    return messages


def message_row(message):
    message_id = message["id"]
    stream_id = message["stream_id"]
    topic = message["subject"]
    encoded = quote(topic, safe="").replace(".", "%2E").replace("%", ".")
    url = f"{ROOT}/#narrow/channel/{stream_id}/topic/{encoded}/near/{message_id}"
    return (
        message_id, stream_id, message["display_recipient"], topic, message["content"],
        message["sender_id"], message["sender_full_name"], message["timestamp"],
        utc(message["timestamp"]), url,
    )


def paginate(database, max_pages):
    executed = 0
    while max_pages is None or executed < max_pages:
        previous = database.execute("SELECT * FROM paginas ORDER BY numero DESC LIMIT 1").fetchone()
        if previous and previous["found_oldest"]:
            break
        anchor = previous["menor_id"] if previous else "newest"
        requested = 1000 if previous else 500
        response = fetch_page(anchor, requested)
        fetched_at = utc()
        messages = validate_page(response, anchor, requested)
        rows = [message_row(message) for message in messages]
        database.execute("BEGIN IMMEDIATE")
        with database:
            latest = database.execute("SELECT MAX(numero) FROM paginas").fetchone()[0]
            previous_number = previous["numero"] if previous else None
            if latest != previous_number:
                raise RuntimeError("Outra coleta avançou o checkpoint. Execute novamente para retomar.")
            result = database.executemany(
                "INSERT INTO mensagens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                rows,
            )
            database.execute(
                """INSERT INTO paginas VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(anchor), requested, fetched_at, rows[0][0] if rows else None,
                    rows[-1][0] if rows else None, len(rows), result.rowcount,
                    response["found_oldest"], response["found_newest"], response["found_anchor"],
                    response.get("history_limited"),
                ),
            )
        executed += 1
        page_number = (previous["numero"] if previous else 0) + 1
        if executed == 1 or page_number % 10 == 0 or response["found_oldest"]:
            print(f"{fetched_at} página {page_number}: {len(rows)} mensagens, âncora {anchor}, "
                  f"menor ID {rows[0][0] if rows else '-'}, found_oldest={response['found_oldest']}", flush=True)
        time.sleep(0.2)


def save_json(path, value):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    Path(temporary.name).replace(path)


def compare_channels(database, initial, current, cutoff, complete):
    initial_channels = {channel["stream_id"]: channel for channel in initial["channels"]}
    current_channels = {channel["stream_id"]: channel for channel in current["channels"]}
    channel_stats = {
        row["stream_id"]: dict(row)
        for row in database.execute(
            """SELECT stream_id, COUNT(*) AS count, MIN(id) AS min_id, MAX(id) AS max_id,
                      COUNT(DISTINCT topic) AS topics, MIN(datetime_utc) AS first_datetime_utc,
                      MAX(datetime_utc) AS last_datetime_utc
               FROM mensagens GROUP BY stream_id"""
        )
    }
    stream_ids = initial_channels.keys() | current_channels.keys() | channel_stats.keys()
    channels = []
    for stream_id in sorted(stream_ids):
        stats = channel_stats.get(stream_id, {
            "stream_id": stream_id, "count": 0, "topics": 0, "min_id": None, "max_id": None,
            "first_datetime_utc": None, "last_datetime_utc": None,
        })
        inventory = current_channels.get(stream_id) or initial_channels.get(stream_id)
        channel = {**stats, **(inventory or {})}
        if inventory is None:
            channel["name"] = database.execute(
                "SELECT channel FROM mensagens WHERE id = ?", (stats["max_id"],)
            ).fetchone()[0]
        first_id = channel.get("first_message_id")
        if not complete or not inventory:
            matches = None
        elif first_id is None or (cutoff is not None and first_id > cutoff):
            matches = channel["count"] == 0
        else:
            matches = channel["min_id"] == first_id
        channels.append({
            **channel,
            "in_initial_inventory": stream_id in initial_channels,
            "in_current_inventory": stream_id in current_channels,
            "matches_first_message_id": matches,
        })
    return channels


def export(database, directory, initial, current, probe, export_jsonl):
    pages = [dict(row) for row in database.execute("SELECT * FROM paginas ORDER BY numero")]
    complete = bool(pages[-1]["found_oldest"])
    cutoff = pages[0]["maior_id"]
    summary = dict(database.execute(
        """SELECT COUNT(*) AS count, MIN(id) AS min_id, MAX(id) AS max_id,
                  MIN(datetime_utc) AS first_datetime_utc, MAX(datetime_utc) AS last_datetime_utc,
                  COUNT(DISTINCT stream_id) AS channels_with_messages
           FROM mensagens"""
    ).fetchone())
    channels = compare_channels(database, initial, current, cutoff, complete)
    save_json(directory / "canais.json", channels)
    sha256 = write_jsonl(database, directory) if export_jsonl else None
    recorded = sum(page["gravadas"] for page in pages)
    issues = []
    if not complete:
        issues.append("O piloto ainda não chegou a found_oldest.")
    if any(page["history_limited"] for page in pages):
        issues.append("O servidor indicou history_limited.")
    if any(page["history_limited"] is None for page in pages):
        issues.append("Páginas sem indicação de history_limited.")
    chain_matches = page_chain_matches(database, pages)
    if not chain_matches:
        issues.append("O registro de páginas diverge dos intervalos gravados.")
    if summary["count"] != recorded or summary["max_id"] != cutoff:
        issues.append("A contagem ou o limite diverge do registro de páginas.")
    for name, snapshot in (("inicial", initial), ("final", current)):
        if snapshot.get("error"):
            issues.append(f"Inventário {name}: {snapshot['error']}")
    if complete and initial["channels"] != current["channels"]:
        issues.append("O inventário público mudou durante a coleta.")
    if complete and any(channel["matches_first_message_id"] is False for channel in channels):
        issues.append("O menor ID observado diverge de first_message_id em pelo menos um canal.")
    if complete and any(channel["count"] and not channel["in_current_inventory"] for channel in channels):
        issues.append("Há mensagens de canais ausentes do inventário final.")
    if complete and (probe is None or probe.get("error") or probe["history_limited"] is not False
                     or probe["id"] != summary["min_id"]):
        issues.append(f"Sondagem de anchor=oldest divergiu ou falhou: {probe}.")
    report = {
        "endpoint": f"{ROOT}/json/messages",
        "narrow": PUBLIC_NARROW,
        "apply_markdown": False,
        "allow_empty_topic_name": True,
        "cutoff_utc": pages[0]["coletada_em_utc"],
        "cutoff_id": cutoff,
        "last_page_utc": pages[-1]["coletada_em_utc"],
        "found_oldest": complete,
        "coverage_verified": not issues,
        "page_chain_verified": chain_matches,
        "oldest_probe": probe,
        "history_limited_pages": sum(page["history_limited"] == 1 for page in pages),
        "history_limited_missing_pages": sum(page["history_limited"] is None for page in pages),
        "duplicates": sum(page["recebidas"] - page["gravadas"] for page in pages),
        **summary,
        "jsonl_sha256": sha256,
        "inventory_initial": {key: value for key, value in initial.items() if key != "channels"},
        "inventory_current": {
            **{key: value for key, value in current.items() if key != "channels"},
            "channels": len(current["channels"]),
            "archived": sum(channel["is_archived"] is True for channel in current["channels"]),
            "without_first_message": sum(channel["first_message_id"] is None for channel in current["channels"]),
        },
        "issues": issues,
        "pages": pages,
    }
    save_json(directory / "coleta.json", report)
    return report


def page_chain_matches(database, pages):
    if not pages[0]["found_newest"] or pages[0]["ancora"] != "newest":
        return False
    for previous, page in zip(pages, pages[1:]):
        if (previous["found_oldest"] or page["ancora"] != str(previous["menor_id"])
                or page["found_anchor"] or page["found_newest"]):
            return False
        if page["maior_id"] is not None and page["maior_id"] >= previous["menor_id"]:
            return False
    for page in pages:
        count = database.execute(
            "SELECT COUNT(*) FROM mensagens WHERE id BETWEEN ? AND ?",
            (page["menor_id"], page["maior_id"]),
        ).fetchone()[0]
        if count != page["gravadas"] or not 0 <= count <= page["recebidas"] <= page["solicitadas"]:
            return False
    return True


def write_jsonl(database, directory):
    temporary = directory / "mensagens.jsonl.tmp"
    sha256 = hashlib.sha256()
    with temporary.open("wb") as output:
        for row in database.execute("SELECT * FROM mensagens ORDER BY id DESC"):
            line = (json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            output.write(line)
            sha256.update(line)
    temporary.replace(directory / "mensagens.jsonl")
    return sha256.hexdigest()


def coletar(diretorio=DESTINATION, max_paginas=None, exportar_piloto=False):
    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)
    inventory_path = diretorio / "inventario-inicial.json"
    error_path = diretorio / "erro.json"
    with closing(sqlite3.connect(diretorio / "coleta.sqlite3", timeout=30)) as database:
        database.row_factory = sqlite3.Row
        database.executescript(SCHEMA)
        try:
            initial = (json.loads(inventory_path.read_text(encoding="utf-8"))
                       if inventory_path.exists() else None)
            has_pages = database.execute("SELECT 1 FROM paginas LIMIT 1").fetchone() is not None
            if initial is None or (initial.get("error") and not has_pages):
                initial = channel_inventory()
                save_json(inventory_path, initial)
            paginate(database, max_paginas)
            complete = bool(database.execute(
                "SELECT found_oldest FROM paginas ORDER BY numero DESC LIMIT 1"
            ).fetchone()[0])
            current = channel_inventory() if complete or exportar_piloto else initial
            probe = oldest_probe() if complete or exportar_piloto else None
            database.execute("BEGIN IMMEDIATE")
            with database:
                report = export(database, diretorio, initial, current, probe, complete or exportar_piloto)
        except (KeyboardInterrupt, OSError, ValueError, RuntimeError, sqlite3.Error, HTTPException, KeyError) as error:
            save_json(error_path, {"utc": utc(), "error": str(error) or type(error).__name__})
            raise
    error_path.unlink(missing_ok=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diretorio", type=Path, default=DESTINATION)
    parser.add_argument("--max-paginas", type=int, help="para após este número de páginas nesta execução")
    parser.add_argument("--exportar-piloto", action="store_true", help="exporta JSONL mesmo sem chegar ao início")
    args = parser.parse_args(argv)
    if args.max_paginas is not None and args.max_paginas < 1:
        parser.error("--max-paginas deve ser positivo")
    report = coletar(args.diretorio, args.max_paginas, args.exportar_piloto)
    print(f"{report['count']} mensagens em {report['channels_with_messages']} canais. "
          f"Relatório: {args.diretorio / 'coleta.json'}", flush=True)
    return 3 if report["found_oldest"] and not report["coverage_verified"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
