"""Read the public study sources already present in the project directory."""

from contextlib import closing
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sqlite3

from acervo_original import DOIST, ZULIP, capture_extension


PLUGIN = Path(__file__).resolve().parent
DOIST_SAMPLES = {item[0]: item[1:] for item in DOIST}
DOIST_TRANSCRIPTS = {
    "doist-pedir-atualizacao": "Let me know if there’s anything I can help with",
    "doist-dar-feedback": "Could you check out this Twist intro? Is it too long?",
    "doist-combinar-prazo": "Can we do Thursday instead of Monday?",
}
ZULIP_SAMPLES = {item[0]: item[1:] for item in ZULIP}
SAMPLE_BY_URL = {url: key for key, (_, url) in DOIST_SAMPLES.items()}
ZULIP_DATABASES = {"full": "zulip", "pilot": "zulip-piloto"}
ZULIP_MESSAGE_ID = re.compile(r"zulip-msg-([0-9]{1,16})")
SEARCH_LIMIT = 12


@lru_cache(maxsize=4)
def doist_catalog(data):
    catalog = read_json(data.parent / "fontes" / "doist.json")
    if not isinstance(catalog.get("itens"), list):
        catalog = read_json(PLUGIN / "catalogo-doist.json")
    items = {
        item["id"]: item for item in catalog["itens"]
        if isinstance(item, dict) and item.get("estado") == "elegível"
        and isinstance(item.get("id"), str) and re.fullmatch(r"[a-z0-9-]+", item["id"])
        and isinstance(item.get("url_secao"), str) and isinstance(item.get("url_original"), str)
    }
    aliases = {key: SAMPLE_BY_URL[item["url_original"]]
               for key, item in items.items() if item["url_original"] in SAMPLE_BY_URL}
    return items, aliases


def has_doist(data, key):
    return key in DOIST_SAMPLES or key in doist_catalog(data)[0]


def capture_path(stem):
    for suffix in (".png", ".jpg", ".webp"):
        path = stem.with_suffix(suffix)
        try:
            with path.open("rb") as stream:
                if capture_extension(stream, os.fstat(stream.fileno()).st_size) == suffix:
                    return path
        except (OSError, ValueError):
            continue
    return None


def get_doist(data, key):
    items, aliases = doist_catalog(data)
    canonical = aliases.get(key, key)
    sample = canonical in DOIST_SAMPLES
    catalog_keys = [alias for alias, target in aliases.items() if target == canonical] if sample else [canonical]
    item = items.get(key) or (items[catalog_keys[0]] if catalog_keys else {})
    path = capture_path(data / canonical) if sample else None
    if path is None:
        path = next((path for catalog_key in catalog_keys
                     if (path := capture_path(data / "doist" / "capturas" / catalog_key))), None)
    source = {
        "id": key, "company": "Doist", "available": path is not None,
        "title": item.get("titulo", key), "description": item.get("evidencia", ""),
        "url": DOIST_SAMPLES[canonical][0] if sample else item["url_secao"],
        "scope": "sample" if sample else "full",
        "aliases": list(dict.fromkeys(alias for alias in (canonical, *catalog_keys) if alias != key)),
    }
    if sample:
        source["transcript"] = DOIST_TRANSCRIPTS[canonical]
    return source, path


def read_json(path):
    try:
        if path.stat().st_size > 16 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def sample_messages(data, key):
    url, _, topic, _, expected = ZULIP_SAMPLES[key]
    channel = url.split("/channel/", 1)[1].split("/", 1)[0].split("-", 1)[-1]
    rows = read_json(data / f"{key}.json").get("mensagens", [])
    if not isinstance(rows, list):
        return []
    messages = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        message_id, body = row.get("id"), row.get("texto")
        if type(message_id) is not int or message_id not in expected or not isinstance(body, str) or not body.strip():
            continue
        messages[message_id] = {
            "id": f"zulip-msg-{message_id}", "company": "Zulip", "scope": "sample",
            "channel": channel, "topic": topic, "excerpt": body[:2500], "text": body,
            "url": f"{url.rsplit('/', 1)[0]}/{message_id}",
            "author": row.get("autor") if isinstance(row.get("autor"), str) else "",
            "datetime_utc": row.get("data_utc") if isinstance(row.get("data_utc"), str) else "",
        }
    return [messages[message_id] for message_id in expected if message_id in messages]


def sample_text(data, key):
    path = data / f"{key}.txt"
    try:
        if path.stat().st_size <= 262144:
            return path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        pass
    return ""


def get_zulip_sample(data, key):
    url, _, topic, _, expected = ZULIP_SAMPLES[key]
    messages = sample_messages(data, key)
    text = sample_text(data, key)
    source = {"id": key, "company": "Zulip", "url": url, "title": topic, "topic": topic,
              "scope": "sample", "available": bool(messages or text),
              "complete": len(messages) == len(expected)}
    if messages:
        source["excerpt"] = "\n\n".join(
            f"{row['author']}: {row['excerpt']}" if row["author"] else row["excerpt"] for row in messages
        )
    elif text:
        source["excerpt"] = text
    return source, messages


def open_zulip(path):
    return closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1))


def database_coverage(data, scope):
    directory = data / ZULIP_DATABASES[scope]
    path = directory / "coleta.sqlite3"
    if not path.is_file():
        return {"available": False, "complete": None}
    try:
        with open_zulip(path) as connection:
            available = bool(connection.execute("SELECT id, channel, topic, content, url FROM mensagens LIMIT 1").fetchone())
    except (OSError, sqlite3.Error):
        return {"available": False, "complete": None, "error": "base_unreadable"}
    report = read_json(directory / "coleta.json")
    complete = report.get("coverage_verified")
    return {"available": available, "complete": complete if isinstance(complete, bool) else None,
            **{key: report[key] for key in ("count", "cutoff_utc", "first_datetime_utc", "last_datetime_utc")
               if isinstance(report.get(key), (str, int))}}


def zulip_coverage(data, samples):
    pilot = database_coverage(data, "pilot")
    full = database_coverage(data, "full")
    searchable_samples = sum(bool(messages) for _, messages in samples)
    return {
        "sample": {"available": sum(source["available"] for source, _ in samples),
                   "total": len(samples), "searchable": searchable_samples},
        "pilot": pilot, "full": full,
        "searchable": bool(searchable_samples or pilot["available"] or full["available"]),
    }


def list_sources(data):
    samples = [get_zulip_sample(data, key) for key in ZULIP_SAMPLES]
    items, aliases = doist_catalog(data)
    doist_keys = (*DOIST_SAMPLES, *(key for key in items if key not in DOIST_SAMPLES and key not in aliases))
    doist = [get_doist(data, key)[0] for key in doist_keys]
    sources = [source for source in doist if source["scope"] == "sample"]
    sources.extend({key: value for key, value in source.items() if key != "excerpt"} for source, _ in samples)
    sources.extend(source for source in doist if source["scope"] == "full" and source["available"])
    coverage = {"doist": {"available": sum(source["available"] for source in doist), "total": len(doist)},
                "zulip": zulip_coverage(data, samples)}
    return {"sources": sources, "coverage": coverage}


def query_database(data, scope, *, message_id=None, query=None):
    path = data / ZULIP_DATABASES[scope] / "coleta.sqlite3"
    if not path.is_file():
        return []
    if message_id is not None:
        condition, values = "id = ?", (message_id,)
    else:
        condition, values = "instr(lower(content), lower(?)) > 0 OR instr(lower(topic), lower(?)) > 0", (query, query)
    try:
        with open_zulip(path) as connection:
            rows = connection.execute(
                f"SELECT id, channel, topic, substr(content, 1, 2500), url FROM mensagens "
                f"WHERE {condition} ORDER BY id DESC LIMIT ?", (*values, SEARCH_LIMIT)
            )
            return [(key, {"id": f"zulip-msg-{key}", "company": "Zulip", "scope": scope,
                           "channel": channel, "topic": topic, "excerpt": excerpt, "url": url})
                    for key, channel, topic, excerpt, url in rows]
    except (OSError, sqlite3.Error):
        return []


def sample_result(message):
    return {key: value for key, value in message.items() if key != "text"}


def read_zulip_message(data, message_id):
    for scope in ZULIP_DATABASES:
        matches = query_database(data, scope, message_id=message_id)
        if matches:
            return matches[0][1]
    for key, (_, _, _, _, expected) in ZULIP_SAMPLES.items():
        if message_id in expected:
            for message in sample_messages(data, key):
                if message["id"] == f"zulip-msg-{message_id}":
                    return sample_result(message)
    return None


def search_zulip(data, query):
    samples = [get_zulip_sample(data, key) for key in ZULIP_SAMPLES]
    matches = {}
    for scope in ZULIP_DATABASES:
        for key, message in query_database(data, scope, query=query):
            matches.setdefault(key, message)
    word = query.casefold()
    for _, messages in samples:
        for message in messages:
            if word in message["text"].casefold() or word in message["topic"].casefold():
                key = int(message["id"].removeprefix("zulip-msg-"))
                matches.setdefault(key, sample_result(message))
    ids = sorted(matches, reverse=True)[:SEARCH_LIMIT]
    return {"matches": [matches[key] for key in ids], "coverage": {"zulip": zulip_coverage(data, samples)}}


def source_ref(data, key):
    if has_doist(data, key):
        source, _ = get_doist(data, key)
    elif key in ZULIP_SAMPLES:
        url, _, title, _, _ = ZULIP_SAMPLES[key]
        source = {"url": url, "title": title}
    elif match := ZULIP_MESSAGE_ID.fullmatch(key):
        source = read_zulip_message(data, int(match[1]))
        if source:
            source = {**source, "title": source["topic"]}
    else:
        source = None
    if source and isinstance(source["url"], str) and source["url"].startswith("https://"):
        return {"id": key, "title": source["title"], "url": source["url"]}
    return None
