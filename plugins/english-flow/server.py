import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from tempfile import NamedTemporaryFile
from threading import Lock

PLUGIN = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN / "lib/pyyaml.zip"))
import yaml

import local_sources as acervo
import graph_reader as grafo
import wiki_search
from edition import BUNDLE, bundled_cache_path, prepare_bundled_wiki
from notebook_format import KINDS, entry_data, markdown_bytes
from tool_inputs import READ_WIKI_ITEM_FIELDS, SAVE_ENTRY_FIELDS, SEARCH_WIKI_FIELDS, STRING, validate
from wiki_index import connect
from source_download import MAX_DOWNLOAD, download, download_messages, verified_image_extension


PROJECT = os.environ.get("ENGLISH_FLOW_PROJECT_DIR")
PERSONAL_DIR = Path.home() / "English Flow"
ROOT = Path(PROJECT or PERSONAL_DIR).expanduser().resolve()
NOTEBOOK = Path(os.environ.get("ENGLISH_FLOW_NOTEBOOK_DIR") or PERSONAL_DIR / "notebook").expanduser().resolve()
DATA = ROOT / "dados" if PROJECT else PERSONAL_DIR / "sources"
BUNDLED_WIKI = bundled_cache_path(BUNDLE) if not PROJECT and (BUNDLE / "manifest.json").is_file() else None
WIKI = BUNDLED_WIKI or ROOT / "wiki"
UI_URI = "ui://english-flow/notebook.html"
UI_TYPE = "text/html;profile=mcp-app"


def study_environment():
    return {"plugin": "english-flow", "execution": "local", "notebook": "filesystem"}


def wiki_available():
    return WIKI == BUNDLED_WIKI or (WIKI / "local/manifesto.json").is_file()


def wiki_directory():
    if WIKI == BUNDLED_WIKI:
        prepare_bundled_wiki(BUNDLE, WIKI)
    return WIKI


def list_sources():
    return {**acervo.list_sources(DATA), "wiki_disponivel": wiki_available()}


def atomic_write(path, data, *, replace=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_bytes(data)
        if replace:
            temporary.replace(path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def download_sources():
    failures = []
    downloaded = []
    for key, (_, capture_url) in acervo.DOIST_SAMPLES.items():
        if acervo.get_doist(DATA, key)[1]:
            continue
        try:
            data = download(capture_url)
            atomic_write(DATA / (key + verified_image_extension(data)), data, replace=True)
            downloaded.append(key)
        except (OSError, ValueError, HTTPException) as exc:
            failures.append({"id": key, "error": str(exc)})
    for key, (url, channel, topic, anchor, ids) in acervo.ZULIP_SAMPLES.items():
        if acervo.get_zulip_sample(DATA, key)[0]["complete"]:
            continue
        try:
            messages = download_messages(channel, topic, anchor, ids)
            data = json.dumps({"fonte": url, "topico": topic, "mensagens": messages},
                              ensure_ascii=False, indent=2).encode()
            atomic_write(DATA / f"{key}.json", data, replace=True)
            downloaded.append(key)
        except (OSError, ValueError, KeyError, HTTPException) as exc:
            failures.append({"id": key, "error": str(exc)})
    return {**list_sources(), "downloaded": downloaded, "failures": failures}


def read_source(source_id):
    if acervo.has_doist(DATA, source_id):
        info, path = acervo.get_doist(DATA, source_id)
        if path is None:
            raise ValueError("Download the source collection first.")
        with path.open("rb") as stream:
            data = stream.read(MAX_DOWNLOAD + 1)
        extension = verified_image_extension(data)
        mime = "image/jpeg" if extension == ".jpg" else "image/" + extension[1:]
        return result(info, extra=[{"type": "image", "mimeType": mime, "data": base64.b64encode(data).decode()}])
    if source_id in acervo.ZULIP_SAMPLES:
        source, messages = acervo.get_zulip_sample(DATA, source_id)
        if not source["available"]:
            raise ValueError("Download the source collection first.")
        return result({**source, "messages": [acervo.sample_result(message) for message in messages]})
    if match := acervo.ZULIP_MESSAGE_ID.fullmatch(source_id):
        message = acervo.read_zulip_message(DATA, int(match[1]))
        if message is None:
            raise ValueError("Message missing from the local collection.")
        return result(message)
    raise ValueError("Unknown source.")


def search_zulip(query):
    query = query.strip()
    if not 2 <= len(query) <= 120:
        raise ValueError("Use a search term of 2 to 120 characters.")
    return acervo.search_zulip(DATA, query)


def open_graph():
    path = wiki_directory() / "local" / "grafo.sqlite3"
    if not path.is_file():
        raise ValueError("Graph missing. Restore the wiki in ENGLISH_FLOW_PROJECT_DIR/wiki, including local/grafo.sqlite3.")
    indice = path.with_name("consulta.sqlite3")
    if indice.is_file() or wiki_available():
        connect(WIKI).close()
    return grafo.open_read_only(path, indice)


def search_graph(topic=None, situation=None, source=None, text=None, curated_only=False, limit=10, offset=0):
    with open_graph() as db:
        db.row_factory = sqlite3.Row
        rows = grafo.find_examples(db, WIKI, tema=topic, situacao=situation, fonte=source,
                                     texto=text, curados=curated_only, limite=limit + 1, pular=offset)
    matches = rows[:limit]
    for row in matches:
        if row["pagina_local"]:
            row["pagina_local"] = (WIKI / row["pagina_local"]).as_posix()
    return {"matches": matches, "next_offset": offset + limit if len(rows) > limit else None}


def read_graph_node(node_id):
    with open_graph() as db:
        db.row_factory = sqlite3.Row
        item = grafo.read_node(db, WIKI, node_id)
    if item["pagina_local"]:
        item["pagina_local"] = (WIKI / item["pagina_local"]).as_posix()
    return item


def search_wiki(**filtros):
    return wiki_search.consultar(wiki_directory(), wiki_search.buscar, **filtros)


def read_wiki_item(item_id, offset=0, limit=9000):
    return wiki_search.consultar(wiki_directory(), wiki_search.abrir, chave=item_id, offset=offset, limit=limit)


def source_ref(key):
    if wiki_available() or (WIKI / "local/consulta.sqlite3").is_file():
        try:
            item = read_wiki_item(key, limit=1)
        except ValueError:
            pass
        else:
            return {"id": key, "title": item["titulo"], "url": item["url"],
                    "pagina_local": item["pagina_local"], "tool": "read_wiki_item"}
    ref = acervo.source_ref(DATA, key)
    if ref or not (WIKI / "local" / "grafo.sqlite3").is_file():
        return ref
    with open_graph() as db:
        row = db.execute("SELECT titulo, url FROM nos WHERE id=? AND tipo IN ('mensagem','captura')",
                         (key,)).fetchone()
    if row and row[1] and row[1].startswith("https://"):
        return {"id": key, "title": row[0], "url": row[1]}
    return None


def load_entry(path):
    if path.is_symlink() or path.stat().st_size > 262144:
        raise ValueError("Invalid notebook file format.")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".md":
        if text.startswith("---\n"):
            header, separator, body = text[4:].partition("\n---\n")
            if separator:
                try:
                    data = yaml.safe_load(header)
                except yaml.YAMLError:
                    if re.search(r"^schema_version\s*:", header, re.MULTILINE):
                        raise
                    data = None
                if isinstance(data, dict):
                    if "schema_version" in data:
                        return validated_entry(path, data, body.strip())
                    return markdown_entry(path, body.lstrip("\n"), data)
        return markdown_entry(path, text)
    data = yaml.safe_load(text)
    return validated_entry(path, data, data.get("content") if isinstance(data, dict) else None)


def validated_entry(path, data, content):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unknown YAML version.")
    if any(not isinstance(data.get(key), str) for key in ("title", "kind")) or not isinstance(content, str):
        raise ValueError("Invalid YAML entry.")
    sources = data.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
        raise ValueError("Invalid references.")
    return entry_record(path, data, content, sources)


def markdown_entry(path, content, data=None):
    data = data or {}
    data = {
        **data,
        "title": data.get("title") if isinstance(data.get("title"), str) else
                 next((line[2:] for line in content.splitlines() if line.startswith("# ")), path.stem),
        "kind": data["kind"] if data.get("kind") in KINDS else ("note" if data else "lesson"),
    }
    sources = data.get("sources")
    return entry_record(path, data, content,
                        [source for source in sources if isinstance(source, str)] if isinstance(sources, list) else [])


def entry_record(path, data, content, sources):
    created_at = data.get("created_at")
    if isinstance(created_at, (datetime, date)):
        created_at = created_at.isoformat()
    return {"id": path.name, "title": data["title"], "kind": data["kind"], "content": content,
            "sources": sources, "source_refs": data.get("source_refs", []),
            "created_at": created_at if isinstance(created_at, str) else ""}


def open_notebook():
    entries = []
    skipped = []
    for path in sorted(NOTEBOOK.iterdir() if NOTEBOOK.is_dir() else []):
        if path.suffix not in (".md", ".yaml", ".yml"):
            continue
        try:
            entry = load_entry(path)
            entries.append(entry)
        except (OSError, ValueError, yaml.YAMLError):
            skipped.append(path.name)
    entries.sort(key=lambda entry: (entry.get("created_at", ""), entry["id"]))
    summaries = [{key: entry[key] for key in ("id", "title", "kind")} for entry in entries]
    return {"entries": summaries, "skipped": skipped, **list_sources()}


def read_entry(entry_id):
    if not re.fullmatch(r"[^/\\:<>|?*\x00-\x1f]+\.(md|yaml|yml)", entry_id):
        raise ValueError("Invalid entry ID.")
    entry = load_entry(NOTEBOOK / entry_id)
    source_refs = entry.pop("source_refs")
    refs = {}
    if isinstance(source_refs, list):
        for ref in source_refs:
            if (isinstance(ref, dict) and ref.get("tool") == "read_wiki_item"
                    and isinstance(ref.get("id"), str) and ref.get("id") in entry["sources"] and isinstance(ref.get("title"), str)):
                url = ref.get("url")
                refs[ref["id"]] = source_ref(ref["id"]) or {
                    "id": ref["id"], "title": ref["title"], "tool": "read_wiki_item",
                    "url": url if isinstance(url, str) and url.startswith("https://") else None,
                }
                continue
            if isinstance(ref, dict) and all(isinstance(ref.get(key), str) for key in ("id", "title", "url")):
                if ref["id"] in entry["sources"] and ref["url"].startswith("https://"):
                    refs[ref["id"]] = {key: ref[key] for key in ("id", "title", "url")}
    entry["source_refs"] = [ref for key in entry["sources"] if (ref := refs.get(key) or source_ref(key))]
    return entry


def save_entry(kind, title, content, sources=None):
    entry_id, entry = entry_data(kind, title, content, sources)
    refs = [source_ref(source) for source in entry["sources"]]
    if any(ref is None for ref in refs):
        raise ValueError("Use source IDs from search_wiki, list_sources, search_zulip, or search_graph.")
    path = NOTEBOOK / entry_id
    try:
        atomic_write(path, markdown_bytes(entry, refs))
    except FileExistsError:
        saved = load_entry(path)
        if saved["content"] != entry["content"] or any(saved[field] != entry[field] for field in ("title", "kind", "sources")):
            raise ValueError("The existing file has different content.")
    return {"id": path.name, "path": str(path)}


def tool(name, description, properties=None, required=(), *, ui=False, writes=False):
    schema = {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}
    definition = {"name": name, "description": description, "inputSchema": schema,
                  "annotations": {"readOnlyHint": not writes, "destructiveHint": False,
                                  "openWorldHint": name == "download_sources"}}
    if ui:
        definition["_meta"] = {"ui": {"resourceUri": UI_URI}}
    return definition


TOOLS = [
    tool("study_environment", "Identify the local English Flow runtime without opening files or using the network."),
    tool("open_notebook", "Open the panel and list notebook entries and sources.", ui=True),
    tool("read_entry", "Read a notebook entry by ID.", {"entry_id": STRING}, ("entry_id",)),
    tool("save_entry", "Save a lesson, practice session, review, or note in Markdown with YAML metadata.", SAVE_ENTRY_FIELDS, ("kind", "title", "content"), writes=True),
    tool("list_sources", "List public sources and show which are available locally."),
    tool("read_source", "Read a passage or image from the local collection.", {"source_id": STRING}, ("source_id",)),
    tool("search_zulip", "Search the local Zulip messages.", {"query": STRING}, ("query",)),
    tool("search_wiki", "Search the wiki offline. Use a literal phrase for text. Filters use Portuguese IDs. "
         "A verified item ('conferido') requires evidence. Read citar_id before quoting. 'arquivo' is a filename match.", SEARCH_WIKI_FIELDS),
    tool("read_wiki_item", "Open an ID on its current page. Read its evidence, sources, and nearby messages. "
         "Use next_offset to continue reading a long item.", READ_WIKI_ITEM_FIELDS, ("item_id",)),
    tool("search_graph", "Search Doist and Zulip by topic, situation, source, and text. "
         "Use curated_only for verified uses in each selected study filter. "
         "The result includes a node ID, preview, local page, and source reference.", {
             "topic": {"type": "string", "enum": list(grafo.TOPICS)},
             "situation": {"type": "string", "enum": list(grafo.SITUATIONS)},
             "source": {"type": "string", "enum": ["Doist", "Zulip"]},
             "text": {"type": "string", "minLength": 1, "maxLength": 200},
             "curated_only": {"type": "boolean"},
             "limit": {"type": "integer", "minimum": 1, "maximum": 50},
             "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
         }),
    tool("read_graph_node", "Read the text and relations of a graph node by ID. "
         "You can also open topic and situation IDs from its links.",
         {"node_id": {"type": "string", "minLength": 1, "maxLength": 200}}, ("node_id",)),
    tool("download_sources", "Download missing public Doist and Zulip samples on request.", writes=True),
]
FUNCTIONS = {item["name"]: globals()[item["name"]] for item in TOOLS}


def result(data, *, extra=(), error=False):
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}, *extra],
            "structuredContent": data, "isError": error}


def call_tool(params):
    name = params.get("name")
    definition = next((item for item in TOOLS if item["name"] == name), None)
    if definition is None:
        return result({"error": "Unknown tool."}, error=True)
    arguments = params.get("arguments", {})
    schema = definition["inputSchema"]
    try:
        validate(arguments, schema["properties"], schema["required"])
        data = FUNCTIONS[name](**arguments)
        return data if name == "read_source" else result(data)
    except (OSError, ValueError, sqlite3.Error, yaml.YAMLError) as exc:
        return result({"error": str(exc)}, error=True)


def dispatch(method, params):
    ui = {"uri": UI_URI, "name": "Study notebook", "mimeType": UI_TYPE}
    if method == "initialize":
        versions = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
        requested = params.get("protocolVersion")
        return {"protocolVersion": requested if requested in versions else versions[-1],
                "capabilities": {"tools": {}, "resources": {}},
                "instructions": ("In a local chat, call study_environment to select the local wiki and notebook. "
                                 "Start each new learner conversation in English. A request written in another language "
                                 "does not change the reply language. When the learner asks to switch, use that language "
                                 "for instructions, explanations, and feedback until asked to switch again. Keep English "
                                 "examples, exercises, and role-play in English. Use natural workplace language."),
                "serverInfo": {"name": "english-flow", "version": "0.7.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params)
    if method == "resources/list":
        return {"resources": [ui]}
    if method == "resources/templates/list":
        return {"resourceTemplates": []}
    if method == "resources/read" and params.get("uri") == UI_URI:
        return {"contents": [{**ui, "text": (PLUGIN / "notebook.html").read_text(encoding="utf-8")}]}
    raise LookupError("Unknown method or resource.")


def serve():
    output = Lock()

    def reply(response):
        with output:
            print(json.dumps(response, ensure_ascii=True), flush=True)

    def respond(response, method, params):
        try:
            response["result"] = dispatch(method, params)
        except (ValueError, TypeError, LookupError, OSError) as exc:
            response["error"] = {"code": -32601 if isinstance(exc, LookupError) else -32602,
                                 "message": str(exc)}
        reply(response)

    with ThreadPoolExecutor(max_workers=1) as worker:
        active_download = None
        for line in sys.stdin.buffer:
            response = {"jsonrpc": "2.0", "id": None}
            try:
                request = json.loads(line)
                if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                    raise TypeError("Invalid JSON-RPC message.")
                if "id" not in request:
                    continue
                response["id"] = request["id"]
                method, params = request["method"], request.get("params", {})
                if not isinstance(params, dict):
                    raise TypeError("Invalid parameters.")
            except (ValueError, TypeError) as exc:
                response["error"] = {"code": -32700 if isinstance(exc, json.JSONDecodeError) else -32602,
                                     "message": str(exc)}
                reply(response)
                continue
            if method == "tools/call" and params.get("name") == "download_sources":
                if active_download and not active_download.done():
                    response["result"] = result({"error": "A download is already in progress."}, error=True)
                    reply(response)
                else:
                    active_download = worker.submit(respond, response, method, params)
            else:
                respond(response, method, params)


if __name__ == "__main__":
    serve()
