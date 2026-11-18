"""Restaura a edição de curadoria a partir dos arquivos do próprio checkout."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "wiki"))
from ingerir_acervo import verificar


def restaurar(pacote, destino):
    pacote, destino = pacote.resolve(), destino.absolute()
    meta = json.loads((pacote / "acervo.json").read_text(encoding="utf-8"))
    if meta["versao"] != 1:
        raise ValueError("Versão desconhecida do pacote.")
    if destino.is_symlink():
        raise ValueError("Escolha uma pasta de destino real.")
    if destino.exists():
        manifesto = destino / "manifesto.json"
        if manifesto.is_file() and hashlib.sha256(manifesto.read_bytes()).hexdigest() == meta["manifesto_sha256"]:
            return "Edição já presente."
        raise ValueError(f"A pasta {destino} já existe com outro conteúdo. Escolha outro --destino para preservar seu trabalho.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".restaurar-wiki-", dir=destino.parent) as tmp:
        tmp = Path(tmp)
        arquivo, edicao = tmp / "wiki.tar.gz", tmp / "local"
        edicao.mkdir()
        with arquivo.open("wb") as out:
            for i, parte in enumerate(meta["partes"], 1):
                nome = f"wiki-{i:03d}.bin"
                if parte["arquivo"] != nome:
                    raise ValueError("Sequência de partes inválida.")
                digest = hashlib.sha256()
                with (pacote / nome).open("rb") as inp:
                    for bloco in iter(lambda: inp.read(1024 * 1024), b""):
                        digest.update(bloco)
                        out.write(bloco)
                if digest.hexdigest() != parte["sha256"]:
                    raise ValueError(f"Parte divergente: {nome}.")
        with tarfile.open(arquivo, "r|gz") as tar:
            for member in tar:
                rel = PurePosixPath(member.name)
                if (not member.isfile() or rel.is_absolute() or ".." in rel.parts
                        or re.search(r"[:\\]", member.name) or member.name != rel.as_posix()):
                    raise ValueError("Entrada inválida no pacote.")
                path = edicao / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as inp, path.open("xb") as out:
                    shutil.copyfileobj(inp, out, 1024 * 1024)
        if hashlib.sha256((edicao / "manifesto.json").read_bytes()).hexdigest() != meta["manifesto_sha256"]:
            raise ValueError("Manifesto divergente.")
        resultado = verificar(edicao)
        if resultado["arquivos_verificados"] != meta["arquivos_verificados"]:
            raise ValueError("Cobertura divergente.")
        edicao.rename(destino)
    return f"{resultado['arquivos_verificados']} arquivos conferidos e restaurados em {destino}."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=ROOT / "wiki/local")
    args = parser.parse_args()
    try:
        print(restaurar(ROOT / "nuvem", args.destino), flush=True)
        if args.destino.resolve() == (ROOT / "wiki/local").resolve():
            sys.path.insert(0, str(ROOT / "plugins/ingles-para-o-trabalho"))
            from indice_wiki import conectar
            from contextlib import closing
            with closing(conectar(ROOT / "wiki")) as db:
                print("IDs disponíveis para busca:", db.execute("SELECT count(*) FROM itens").fetchone()[0])
    except (ValueError, OSError, tarfile.TarError) as exc:
        parser.exit(1, f"{exc}\n")
