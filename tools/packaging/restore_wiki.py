import argparse
from contextlib import closing
from pathlib import Path
import tarfile

from tools import ROOT
from edition import BUNDLE, restore


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Restore the local wiki from the source archive.')
    parser.add_argument("--destination", type=Path, default=ROOT / "wiki/local")
    args = parser.parse_args()
    try:
        print(restore(BUNDLE, args.destination), flush=True)
        if args.destination.resolve() == (ROOT / "wiki/local").resolve():
            from wiki_index import connect
            with closing(connect(ROOT / "wiki")) as db:
                print("Searchable IDs:", db.execute("SELECT count(*) FROM itens").fetchone()[0])
    except (ValueError, OSError, tarfile.TarError) as exc:
        parser.exit(1, f"{exc}\n")
