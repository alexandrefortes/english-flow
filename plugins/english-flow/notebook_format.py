from datetime import datetime, timezone
import hashlib
import json


KINDS = ("lesson", "practice", "review", "note")
YAML_ESCAPES = {code: f"\\u{code:04x}" for code in (*range(0x7f, 0xa0), 0x2028, 0x2029, 0xfffe, 0xffff)}


def entry_data(kind, title, content, sources=None):
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if kind not in KINDS or not title.strip() or not content.strip():
        raise ValueError("Supply a valid entry type, title, and content.")
    if len(title) > 160 or len(content.encode()) > 50000:
        raise ValueError("Title or content exceeds the size limit.")
    entry = {"schema_version": 1, "kind": kind, "language": "en", "title": title.strip(),
             "content": content.strip(), "sources": sorted(set(sources or []))}
    key = hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    return f"{kind}-{key}.md", entry


def markdown_bytes(entry, references):
    header = {key: value for key, value in entry.items() if key != "content"}
    header["created_at"] = datetime.now(timezone.utc).isoformat()
    header["source_refs"] = [
        {key: ref[key] for key in ("id", "title", "url", "tool") if key in ref} for ref in references
    ]
    fields = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in header.items())
    fields = fields.translate(YAML_ESCAPES)
    return f"---\n{fields}\n---\n\n{entry['content']}\n".encode("utf-8")
