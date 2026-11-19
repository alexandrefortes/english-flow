"""Restaura a edição de curadoria a partir dos arquivos do próprio checkout."""
import argparse
from contextlib import closing
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "plugins/ingles-para-o-trabalho"))
from edicao import PACOTE, restaurar


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=ROOT / "wiki/local")
    args = parser.parse_args()
    try:
        print(restaurar(PACOTE, args.destino), flush=True)
        if args.destino.resolve() == (ROOT / "wiki/local").resolve():
            from indice_wiki import conectar
            with closing(conectar(ROOT / "wiki")) as db:
                print("IDs disponíveis para busca:", db.execute("SELECT count(*) FROM itens").fetchone()[0])
    except (ValueError, OSError, tarfile.TarError) as exc:
        parser.exit(1, f"{exc}\n")
