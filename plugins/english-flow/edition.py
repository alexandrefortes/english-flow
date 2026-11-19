import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from tempfile import TemporaryDirectory


BUNDLE = Path(__file__).resolve().parent / "corpus"


def file_hash(caminho):
    with caminho.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def verify(pasta):
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    if manifesto.get("schema_version") != 1:
        raise ValueError("Unknown edition manifest version.")
    for nome, resumo in manifesto["arquivos"].items():
        arquivo = (pasta / nome).resolve()
        if not arquivo.is_relative_to(pasta) or file_hash(arquivo) != resumo:
            raise ValueError(f'Edition file checksum mismatch: {nome}.')
    return {**manifesto["totais"], "arquivos_verificados": len(manifesto["arquivos"])}


def extract(arquivo, edicao):
    with tarfile.open(arquivo, "r|gz") as tar:
        for member in tar:
            rel = PurePosixPath(member.name)
            if (not member.isfile() or rel.is_absolute() or ".." in rel.parts
                    or re.search(r"[:\\]", member.name) or member.name != rel.as_posix()):
                raise ValueError("Invalid archive entry.")
            path = edicao / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as inp, path.open("xb") as out:
                shutil.copyfileobj(inp, out, 1024 * 1024)


def restore(pacote, destino):
    pacote, destino = pacote.resolve(), destino.absolute()
    meta = json.loads((pacote / "manifest.json").read_text(encoding="utf-8"))
    if meta["versao"] != 1:
        raise ValueError("Unknown archive version.")
    if destino.is_symlink():
        raise ValueError("Select a real destination directory.")
    if destino.exists():
        manifesto = destino / "manifesto.json"
        if manifesto.is_file() and file_hash(manifesto) == meta["manifesto_sha256"]:
            return "Edition already present."
        raise ValueError(f'The directory {destino} already contains different data. Choose another --destination to keep your work.')
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".restaurar-wiki-", dir=destino.parent) as tmp:
        tmp = Path(tmp)
        arquivo, edicao = tmp / "wiki.tar.gz", tmp / "local"
        edicao.mkdir()
        with arquivo.open("wb") as out:
            for i, parte in enumerate(meta["partes"], 1):
                nome = f"wiki-{i:03d}.bin"
                if parte["arquivo"] != nome:
                    raise ValueError("Invalid archive part sequence.")
                digest = hashlib.sha256()
                with (pacote / nome).open("rb") as inp:
                    for bloco in iter(lambda: inp.read(1024 * 1024), b""):
                        digest.update(bloco)
                        out.write(bloco)
                if digest.hexdigest() != parte["sha256"]:
                    raise ValueError(f'Archive part checksum mismatch: {nome}.')
        extract(arquivo, edicao)
        if file_hash(edicao / "manifesto.json") != meta["manifesto_sha256"]:
            raise ValueError("Manifest checksum mismatch.")
        resultado = verify(edicao)
        if resultado["arquivos_verificados"] != meta["arquivos_verificados"]:
            raise ValueError("File count mismatch.")
        edicao.rename(destino)
    return f"{resultado['arquivos_verificados']} files verified and restored in {destino}."


def bundled_cache_path(pacote):
    descritores = (pacote / "manifest.json").read_bytes() + (pacote / "project.sha256").read_bytes()
    assinatura = hashlib.sha256(descritores).hexdigest()
    cache = os.environ.get("XDG_CACHE_HOME") or os.environ.get("LOCALAPPDATA") or Path.home() / ".cache"
    return Path(cache).expanduser().resolve() / "english-flow" / assinatura / "wiki"


def prepare_bundled_wiki(pacote, destino):
    manifesto = destino / "local/manifesto.json"
    if manifesto.is_file():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".preparo-", dir=destino.parent) as tmp:
        wiki = Path(tmp) / "wiki"
        wiki.mkdir()
        projeto = pacote / "project.tar.gz"
        if file_hash(projeto) != (pacote / "project.sha256").read_text(encoding="ascii").strip():
            raise ValueError("Editorial archive checksum mismatch.")
        extract(projeto, wiki)
        restore(pacote, wiki / "local")
        try:
            wiki.rename(destino)
        except OSError:
            if not manifesto.is_file():
                raise
