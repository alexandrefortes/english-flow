import argparse
import gzip
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from tools import PLUGIN, ROOT
from tools.packaging.pack_sources import add_member, sha


ARCHIVE = PLUGIN / "corpus"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def write_archive(path, tree):
    entries = git("ls-tree", "-rz", f"{tree}:wiki")
    with path.open("wb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0, compresslevel=6) as stream:
        with tarfile.open(fileobj=stream, mode="w|") as archive:
            for entry in entries.split(b"\0"):
                if not entry:
                    continue
                metadata, filename = entry.split(b"\t", 1)
                name = filename.decode("utf-8")
                if Path(name).suffix in {".md", ".json", ".gz"}:
                    object_id = metadata.split()[2].decode("ascii")
                    add_member(archive, name, git("cat-file", "blob", object_id))


def main():
    parser = argparse.ArgumentParser(description="Build the editorial archive from a Git snapshot.")
    parser.add_argument("--ref", help="Use the wiki at this commit or tag. The default is the Git index.")
    parser.add_argument("--check", action="store_true", help="Compare the package with the snapshot.")
    args = parser.parse_args()
    tree = git("rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{tree}}") if args.ref else git("write-tree")
    with TemporaryDirectory(dir=None if args.check else ARCHIVE) as stage:
        package = Path(stage) / "project.tar.gz"
        write_archive(package, tree.decode("ascii").strip())
        digest = sha(package)
        checksum = ARCHIVE / "project.sha256"
        if args.check:
            if digest != sha(ARCHIVE / package.name) or digest != checksum.read_text(encoding="ascii").strip():
                parser.exit(1, "The editorial archive differs from the Git snapshot.\n")
            print("The editorial archive matches the Git snapshot.")
            return
        signature = Path(stage) / checksum.name
        signature.write_text(digest + "\n", encoding="ascii", newline="\n")
        package.replace(ARCHIVE / package.name)
        signature.replace(checksum)


if __name__ == "__main__":
    main()
