import argparse
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tools import PLUGIN, ROOT


DRIVE_APP = "connector_5f3c8c41a1e54ad7a76272c89e2554fa"
SOURCE_REPOSITORY = "alexandrefortes/workplace-english-practice"
CORPUS_REVISION = "55d520cf4b616a970bef813f68ac3564ddb5c1bb"
WORK_MODULES = ("work_study.py", "edition.py", "graph_reader.py", "wiki_index.py",
                "wiki_search.py", "notebook_format.py", "tool_inputs.py")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def corpus_release(repository, ref):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Use the GitHub owner and repository name.")
    commit = git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
    prefix = "plugins/english-flow/corpus/"
    source = f"{commit}:{prefix}"
    manifest = git("show", source + "manifest.json")
    digest = git("show", source + "project.sha256")
    for name, data in (("manifest.json", manifest), ("project.sha256", digest)):
        if (PLUGIN / "corpus" / name).read_bytes() != data:
            raise ValueError("Choose a published revision with the same corpus as this checkout.")
    return {"base_url": f"https://raw.githubusercontent.com/{repository}/{commit}/{prefix}",
            "manifest": json.loads(manifest), "project_sha256": digest.decode("ascii").strip(),
            "project_bytes": int(git("cat-file", "-s", source + "project.tar.gz"))}


def pack(output, repository=SOURCE_REPOSITORY, ref=CORPUS_REVISION):
    manifest = json.loads((PLUGIN / "plugin.json").read_bytes())
    manifest["extensions"]["com.openai"]["apps"] = "./.app.json"
    files = {"plugin.json": json_bytes(manifest),
             ".app.json": json_bytes({"apps": {"google-drive": {"id": DRIVE_APP}}}),
             "LICENSE": (ROOT / "LICENSE").read_bytes(), "NOTICE": (ROOT / "NOTICE").read_bytes(),
             "README.md": (PLUGIN / "README.md").read_bytes()}
    for path in (PLUGIN / "skills").rglob("*"):
        if path.is_file() and path.suffix in (".md", ".yaml", ".yml"):
            files[path.relative_to(PLUGIN).as_posix()] = path.read_bytes()
    scripts = "skills/notebook-review/scripts/"
    for name in WORK_MODULES:
        files[scripts + name] = (PLUGIN / name).read_bytes()
    files[scripts + "corpus.json"] = json_bytes(corpus_release(repository, ref))
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as directory:
        archive = Path(directory) / "work.zip"
        with ZipFile(archive, "w") as package:
            for name, data in sorted(files.items()):
                package.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)
        archive.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the English Flow package for ChatGPT Work.")
    parser.add_argument("output", type=Path, help="Destination ZIP file.")
    parser.add_argument("--repository", default=SOURCE_REPOSITORY, help="Public GitHub repository with the edition.")
    parser.add_argument("--ref", default=CORPUS_REVISION, help="Published Git revision with the wiki archive.")
    args = parser.parse_args()
    pack(args.output, args.repository, args.ref)
    print(args.output.resolve())
