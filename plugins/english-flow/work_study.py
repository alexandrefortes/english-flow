import argparse
from contextlib import closing
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
from tempfile import NamedTemporaryFile, TemporaryDirectory, mkdtemp
from urllib.request import urlopen

from edition import file_hash, prepare_bundled_wiki
from notebook_format import entry_data, markdown_bytes
from tool_inputs import READ_WIKI_ITEM_FIELDS, SAVE_ENTRY_FIELDS, SEARCH_WIKI_FIELDS, validate
from wiki_index import connect
from wiki_search import abrir, buscar


def download_part(base_url, path, size, digest):
    if path.is_file() and path.stat().st_size == size and file_hash(path) == digest:
        return
    checksum = hashlib.sha256()
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with urlopen(base_url + path.name, timeout=60) as source, temporary.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                if target.tell() + len(chunk) > size:
                    raise ValueError(f"Archive part exceeds its published size: {path.name}")
                checksum.update(chunk)
                target.write(chunk)
        if temporary.stat().st_size != size or checksum.hexdigest() != digest:
            raise ValueError(f"Archive checksum mismatch: {path.name}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def work_wiki(cache, release):
    if cache is None:
        raise ValueError("Supply --cache for a source lookup.")
    metadata = release.read_bytes()
    root = cache.resolve() / hashlib.sha256(metadata).hexdigest()
    wiki = root / "wiki"
    if (wiki / "local/manifesto.json").is_file():
        return wiki
    data = json.loads(metadata)
    parts = root / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    files = [("project.tar.gz", data["project_bytes"], data["project_sha256"])]
    for number, part in enumerate(data["manifest"]["partes"], 1):
        name = f"wiki-{number:03d}.bin"
        if part["arquivo"] != name:
            raise ValueError("Invalid source archive sequence.")
        files.append((name, part["bytes"], part["sha256"]))
    for name, size, digest in files:
        download_part(data["base_url"], parts / name, size, digest)
    with TemporaryDirectory(dir=parts) as temp:
        stage = Path(temp)
        (stage / "manifest.json").write_text(json.dumps(data["manifest"]), encoding="utf-8")
        (stage / "project.sha256").write_text(data["project_sha256"] + "\n", encoding="ascii")
        for name in ("manifest.json", "project.sha256"):
            (stage / name).replace(parts / name)
    prepare_bundled_wiki(parts, wiki)
    return wiki


def portable_pages(value, wiki):
    if isinstance(value, list):
        for child in value:
            portable_pages(child, wiki)
    if isinstance(value, dict):
        if "pagina_local" in value:
            value["pagina_local"] = "wiki/" + Path(value["pagina_local"]).relative_to(wiki).as_posix()
        for child in value.values():
            portable_pages(child, wiki)
    return value


def run(operation, arguments, cache, release, output=None):
    if operation == "study_environment":
        validate(arguments, {})
        return {"plugin": "english-flow", "execution": "work-cloud", "notebook": "google-drive"}
    if operation == "prepare_entry":
        validate(arguments, SAVE_ENTRY_FIELDS, ("kind", "title", "content"))
        if output is None:
            raise ValueError("Supply --output-dir for the file to upload.")
        name, entry = entry_data(**arguments)
        refs = []
        if entry["sources"]:
            wiki = work_wiki(cache, release)
            with closing(connect(wiki)) as db:
                for key in entry["sources"]:
                    item = abrir(db, wiki, key, limit=1)
                    refs.append({"id": key, "title": item["titulo"], "url": item["url"], "tool": "read_wiki_item"})
        output.mkdir(parents=True, exist_ok=True)
        path = Path(mkdtemp(dir=output.resolve())) / name
        content = markdown_bytes(entry, refs)
        path.write_bytes(content)
        return {"id": name, "path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "status": "prepared"}
    if operation == "search_wiki":
        validate(arguments, SEARCH_WIKI_FIELDS)
    elif operation == "read_wiki_item":
        validate(arguments, READ_WIKI_ITEM_FIELDS, ("item_id",))
    else:
        raise ValueError("Unknown study operation.")
    wiki = work_wiki(cache, release)
    with closing(connect(wiki)) as db:
        if operation == "search_wiki":
            result = buscar(db, wiki, **arguments)
        else:
            result = abrir(db, wiki, arguments["item_id"], arguments.get("offset", 0), arguments.get("limit", 9000))
    return portable_pages(result, wiki)


def main():
    parser = argparse.ArgumentParser(description="Query the published wiki or prepare a notebook entry in a Work task.")
    parser.add_argument("operation", choices=("study_environment", "search_wiki", "read_wiki_item", "prepare_entry"))
    parser.add_argument("--cache", type=Path, help="Task directory for public wiki files.")
    parser.add_argument("--output-dir", type=Path, help="Private task directory for a prepared Markdown file.")
    args = parser.parse_args()
    try:
        release = Path(__file__).with_name("corpus.json")
        result = run(args.operation, json.load(sys.stdin), args.cache, release, args.output_dir)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, HTTPException, sqlite3.Error, tarfile.TarError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
