import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
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

import acervo_local as acervo
import consulta_grafo as grafo
import busca_wiki
from edicao import PACOTE, destino_incluido, preparar_incluida
from indice_wiki import TIPOS, ESTADOS, conectar
from acervo_original import MAX_DOWNLOAD, baixar, baixar_mensagens, verified_image_extension


PROJETO = os.environ.get("INGLEST_PROJECT_DIR")
ROOT = Path(PROJETO or Path.home() / "Inglês para o Trabalho").expanduser().resolve()
NOTEBOOK = Path(os.environ.get("INGLEST_NOTEBOOK_DIR") or ROOT / "caderno de estudos").expanduser().resolve()
DATA = ROOT / "dados"
WIKI_INCLUIDA = destino_incluido(PACOTE) if not PROJETO and (PACOTE / "acervo.json").is_file() else None
WIKI = WIKI_INCLUIDA or ROOT / "wiki"
UI_URI = "ui://ingles-trabalho/caderno.html"
UI_TYPE = "text/html;profile=mcp-app"
KINDS = ("lesson", "practice", "review", "note")


def wiki_disponivel():
    return WIKI == WIKI_INCLUIDA or (WIKI / "local/manifesto.json").is_file()


def pasta_wiki():
    if WIKI == WIKI_INCLUIDA:
        preparar_incluida(PACOTE, WIKI)
    return WIKI


def list_sources():
    return {**acervo.list_sources(DATA), "wiki_disponivel": wiki_disponivel()}


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
            data = baixar(capture_url)
            atomic_write(DATA / (key + verified_image_extension(data)), data, replace=True)
            downloaded.append(key)
        except (OSError, ValueError, HTTPException) as exc:
            failures.append({"id": key, "error": str(exc)})
    for key, (url, channel, topic, anchor, ids) in acervo.ZULIP_SAMPLES.items():
        if acervo.get_zulip_sample(DATA, key)[0]["complete"]:
            continue
        try:
            messages = baixar_mensagens(channel, topic, anchor, ids)
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
            raise ValueError("Baixe o acervo primeiro.")
        with path.open("rb") as stream:
            data = stream.read(MAX_DOWNLOAD + 1)
        extension = verified_image_extension(data)
        mime = "image/jpeg" if extension == ".jpg" else "image/" + extension[1:]
        return result(info, extra=[{"type": "image", "mimeType": mime, "data": base64.b64encode(data).decode()}])
    if source_id in acervo.ZULIP_SAMPLES:
        source, messages = acervo.get_zulip_sample(DATA, source_id)
        if not source["available"]:
            raise ValueError("Baixe o acervo primeiro.")
        return result({**source, "messages": [acervo.sample_result(message) for message in messages]})
    if match := acervo.ZULIP_MESSAGE_ID.fullmatch(source_id):
        message = acervo.read_zulip_message(DATA, int(match[1]))
        if message is None:
            raise ValueError("Mensagem ausente no acervo local.")
        return result(message)
    raise ValueError("Fonte desconhecida.")


def search_zulip(query):
    query = query.strip()
    if not 2 <= len(query) <= 120:
        raise ValueError("Use um termo de 2 a 120 caracteres.")
    return acervo.search_zulip(DATA, query)


def abrir_grafo():
    path = pasta_wiki() / "local" / "grafo.sqlite3"
    if not path.is_file():
        raise ValueError("Grafo ausente. Coloque a wiki completa em INGLEST_PROJECT_DIR/wiki, incluindo local/grafo.sqlite3.")
    indice = path.with_name("consulta.sqlite3")
    if indice.is_file() or wiki_disponivel():
        conectar(WIKI).close()
    return grafo.abrir_leitura(path, indice)


def search_graph(topic=None, situation=None, source=None, text=None, curated_only=False, limit=10, offset=0):
    with abrir_grafo() as db:
        db.row_factory = sqlite3.Row
        rows = grafo.buscar_exemplos(db, WIKI, tema=topic, situacao=situation, fonte=source,
                                     texto=text, curados=curated_only, limite=limit + 1, pular=offset)
    matches = rows[:limit]
    for row in matches:
        if row["pagina_local"]:
            row["pagina_local"] = (WIKI / row["pagina_local"]).as_posix()
    return {"matches": matches, "next_offset": offset + limit if len(rows) > limit else None}


def read_graph_node(node_id):
    with abrir_grafo() as db:
        db.row_factory = sqlite3.Row
        item = grafo.ler_no(db, WIKI, node_id)
    if item["pagina_local"]:
        item["pagina_local"] = (WIKI / item["pagina_local"]).as_posix()
    return item


def search_wiki(**filtros):
    return busca_wiki.consultar(pasta_wiki(), busca_wiki.buscar, **filtros)


def read_wiki_item(item_id, offset=0, limit=9000):
    return busca_wiki.consultar(pasta_wiki(), busca_wiki.abrir, chave=item_id, offset=offset, limit=limit)


def source_ref(key):
    if wiki_disponivel() or (WIKI / "local/consulta.sqlite3").is_file():
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
    with abrir_grafo() as db:
        row = db.execute("SELECT titulo, url FROM nos WHERE id=? AND tipo IN ('mensagem','captura')",
                         (key,)).fetchone()
    if row and row[1] and row[1].startswith("https://"):
        return {"id": key, "title": row[0], "url": row[1]}
    return None


def load_entry(path):
    if path.is_symlink() or path.stat().st_size > 262144:
        raise ValueError("Arquivo fora do formato do caderno.")
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
        raise ValueError("Versão de YAML não reconhecida.")
    if any(not isinstance(data.get(key), str) for key in ("title", "kind")) or not isinstance(content, str):
        raise ValueError("Registro YAML inválido.")
    sources = data.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
        raise ValueError("Referências inválidas.")
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
        raise ValueError("Identificador de registro inválido.")
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
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if kind not in KINDS or not title.strip() or not content.strip():
        raise ValueError("Informe um tipo, título e conteúdo válidos.")
    if len(title) > 160 or len(content.encode()) > 50000:
        raise ValueError("Título ou conteúdo excede o limite.")
    sources = sorted(set(sources or []))
    refs = [source_ref(source) for source in sources]
    if any(ref is None for ref in refs):
        raise ValueError("Use IDs de fontes retornados por search_wiki, list_sources, search_zulip ou search_graph.")
    entry = {"schema_version": 1, "kind": kind, "language": "en", "title": title.strip(),
             "content": content.strip(), "sources": sources}
    key = hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    path = NOTEBOOK / f"{kind}-{key}.md"
    body = entry.pop("content")
    entry["created_at"] = datetime.now(timezone.utc).isoformat()
    entry["source_refs"] = refs
    try:
        header = yaml.safe_dump(entry, allow_unicode=True, sort_keys=False)
        atomic_write(path, f"---\n{header}---\n\n{body}\n".encode())
    except FileExistsError:
        saved = load_entry(path)
        if saved["content"] != body or any(saved[field] != entry[field] for field in ("title", "kind", "sources")):
            raise ValueError("O arquivo existente tem conteúdo diferente.")
    return {"id": path.name, "path": str(path)}


def tool(name, description, properties=None, required=(), *, ui=False, writes=False):
    schema = {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}
    definition = {"name": name, "description": description, "inputSchema": schema,
                  "annotations": {"readOnlyHint": not writes, "destructiveHint": False,
                                  "openWorldHint": name == "download_sources"}}
    if ui:
        definition["_meta"] = {"ui": {"resourceUri": UI_URI}}
    return definition


STRING = {"type": "string"}
TOOLS = [
    tool("open_notebook", "Abre o painel e lista o caderno e o acervo.", ui=True),
    tool("read_entry", "Lê um registro listado no caderno.", {"entry_id": STRING}, ("entry_id",)),
    tool("save_entry", "Grava uma aula, prática, revisão ou nota em Markdown com cabeçalho YAML.", {
        "kind": {"type": "string", "enum": list(KINDS)}, "title": STRING, "content": STRING,
        "sources": {"type": "array", "items": STRING},
    }, ("kind", "title", "content"), writes=True),
    tool("list_sources", "Lista as fontes públicas e indica quais estão disponíveis no disco."),
    tool("read_source", "Lê um trecho ou imagem do acervo local.", {"source_id": STRING}, ("source_id",)),
    tool("search_zulip", "Busca termos nas mensagens do Zulip já coletadas no disco.", {"query": STRING}, ("query",)),
    tool("search_wiki", "Busca na wiki offline. O texto é uma expressão literal. Os filtros usam IDs "
         "em português. 'conferido' exige evidência. Leia citar_id antes de citar. 'arquivo' é só nome.", {
             "kind": {"type": "string", "enum": list(TIPOS)},
             "source": {"type": "string", "enum": ["Doist", "Zulip", "Projeto"]},
             "situation": {"type": "string", "enum": list(grafo.SITUACOES)},
             "topic": {"type": "string", "enum": [*grafo.TEMAS, "leitura-contextual"]},
             "function": STRING,
             "text": {"type": "string", "minLength": 1, "maxLength": 200},
             "curation": {"type": "string", "enum": list(ESTADOS)},
             "limit": {"type": "integer", "minimum": 1, "maximum": 50},
             "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
         }),
    tool("read_wiki_item", "Abre o ID na página atual. Retorna evidência, origens e mensagens próximas. "
         "Para continuar um texto longo, use next_offset.", {
             "item_id": STRING, "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
             "limit": {"type": "integer", "minimum": 1, "maximum": 20000},
         }, ("item_id",)),
    tool("search_graph", "Busca exemplos offline da Doist e do Zulip por tema, situação, fonte e texto. "
         "curated_only exige curadoria em cada filtro pedagógico. Retorna IDs para read_graph_node, "
         "prévia, classificação, página local e referência original.", {
             "topic": {"type": "string", "enum": list(grafo.TEMAS)},
             "situation": {"type": "string", "enum": list(grafo.SITUACOES)},
             "source": {"type": "string", "enum": ["Doist", "Zulip"]},
             "text": {"type": "string", "minLength": 1, "maxLength": 200},
             "curated_only": {"type": "boolean"},
             "limit": {"type": "integer", "minimum": 1, "maximum": 50},
             "offset": {"type": "integer", "minimum": 0, "maximum": 2147483647},
         }),
    tool("read_graph_node", "Lê o texto e as relações de um item do grafo pelo ID. "
         "Use também com IDs de tópico, tema ou situação encontrados nas ligações.",
         {"node_id": {"type": "string", "minLength": 1, "maxLength": 200}}, ("node_id",)),
    tool("download_sources", "Baixa sob demanda os exemplos públicos que faltam da Doist e do Zulip.", writes=True),
]
FUNCTIONS = {item["name"]: globals()[item["name"]] for item in TOOLS}


def result(data, *, extra=(), error=False):
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}, *extra],
            "structuredContent": data, "isError": error}


def call_tool(params):
    name = params.get("name")
    definition = next((item for item in TOOLS if item["name"] == name), None)
    if definition is None:
        return result({"error": "Ferramenta desconhecida."}, error=True)
    arguments = params.get("arguments", {})
    schema = definition["inputSchema"]
    fields = schema["properties"]
    try:
        if not isinstance(arguments, dict) or arguments.keys() - fields.keys() or set(schema["required"]) - arguments.keys():
            raise ValueError("Argumentos inválidos.")
        for key, value in arguments.items():
            if fields[key]["type"] == "string" and not isinstance(value, str):
                raise ValueError(f"{key} deve ser texto.")
            field = fields[key]
            if "enum" in field and value not in field["enum"]:
                raise ValueError(f"Valor inválido para {key}.")
            if "minLength" in field and (len(value.strip()) < field["minLength"] or len(value) > field["maxLength"]):
                raise ValueError(f"Tamanho inválido para {key}.")
            if field["type"] == "boolean" and type(value) is not bool:
                raise ValueError(f"{key} deve ser verdadeiro ou falso.")
            if field["type"] == "integer" and (
                type(value) is not int or not field["minimum"] <= value <= field["maximum"]
            ):
                raise ValueError(f"Use um número inteiro entre {field['minimum']} e {field['maximum']} para {key}.")
            if fields[key]["type"] == "array" and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
                raise ValueError(f"{key} deve ser uma lista de textos.")
        data = FUNCTIONS[name](**arguments)
        return data if name == "read_source" else result(data)
    except (OSError, ValueError, sqlite3.Error, yaml.YAMLError) as exc:
        return result({"error": str(exc)}, error=True)


def dispatch(method, params):
    ui = {"uri": UI_URI, "name": "Caderno de estudos", "mimeType": UI_TYPE}
    if method == "initialize":
        versions = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
        requested = params.get("protocolVersion")
        return {"protocolVersion": requested if requested in versions else versions[-1],
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "ingles-para-o-trabalho", "version": "0.5.0"}}
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
        return {"contents": [{**ui, "text": (PLUGIN / "caderno.html").read_text(encoding="utf-8")}]}
    raise LookupError("Método ou recurso desconhecido.")


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
                    raise TypeError("Mensagem JSON-RPC inválida.")
                if "id" not in request:
                    continue
                response["id"] = request["id"]
                method, params = request["method"], request.get("params", {})
                if not isinstance(params, dict):
                    raise TypeError("Parâmetros inválidos.")
            except (ValueError, TypeError) as exc:
                response["error"] = {"code": -32700 if isinstance(exc, json.JSONDecodeError) else -32602,
                                     "message": str(exc)}
                reply(response)
                continue
            if method == "tools/call" and params.get("name") == "download_sources":
                if active_download and not active_download.done():
                    response["result"] = result({"error": "Já há um download em andamento."}, error=True)
                    reply(response)
                else:
                    active_download = worker.submit(respond, response, method, params)
            else:
                respond(response, method, params)


if __name__ == "__main__":
    serve()
