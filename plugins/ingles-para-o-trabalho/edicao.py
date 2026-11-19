import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from tempfile import TemporaryDirectory


PACOTE = Path(__file__).resolve().parent / "acervo"


def hash_arquivo(caminho):
    with caminho.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def verificar(pasta):
    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    if manifesto.get("schema_version") != 1:
        raise ValueError("Versão desconhecida do manifesto da edição.")
    for nome, resumo in manifesto["arquivos"].items():
        arquivo = (pasta / nome).resolve()
        if not arquivo.is_relative_to(pasta) or hash_arquivo(arquivo) != resumo:
            raise ValueError(f"Arquivo da edição divergente: {nome}.")
    return {**manifesto["totais"], "arquivos_verificados": len(manifesto["arquivos"])}


def extrair(arquivo, edicao):
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


def restaurar(pacote, destino):
    pacote, destino = pacote.resolve(), destino.absolute()
    meta = json.loads((pacote / "acervo.json").read_text(encoding="utf-8"))
    if meta["versao"] != 1:
        raise ValueError("Versão desconhecida do pacote.")
    if destino.is_symlink():
        raise ValueError("Escolha uma pasta de destino real.")
    if destino.exists():
        manifesto = destino / "manifesto.json"
        if manifesto.is_file() and hash_arquivo(manifesto) == meta["manifesto_sha256"]:
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
        extrair(arquivo, edicao)
        if hash_arquivo(edicao / "manifesto.json") != meta["manifesto_sha256"]:
            raise ValueError("Manifesto divergente.")
        resultado = verificar(edicao)
        if resultado["arquivos_verificados"] != meta["arquivos_verificados"]:
            raise ValueError("Cobertura divergente.")
        edicao.rename(destino)
    return f"{resultado['arquivos_verificados']} arquivos conferidos e restaurados em {destino}."


def destino_incluido(pacote):
    descritores = (pacote / "acervo.json").read_bytes() + (pacote / "projeto.sha256").read_bytes()
    assinatura = hashlib.sha256(descritores).hexdigest()
    cache = os.environ.get("XDG_CACHE_HOME") or os.environ.get("LOCALAPPDATA") or Path.home() / ".cache"
    return Path(cache).expanduser().resolve() / "ingles-para-o-trabalho" / assinatura / "wiki"


def preparar_incluida(pacote, destino):
    manifesto = destino / "local/manifesto.json"
    if manifesto.is_file():
        return
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".preparo-", dir=destino.parent) as tmp:
        wiki = Path(tmp) / "wiki"
        wiki.mkdir()
        projeto = pacote / "projeto.tar.gz"
        if hash_arquivo(projeto) != (pacote / "projeto.sha256").read_text(encoding="ascii").strip():
            raise ValueError("Arquivo das páginas e decisões de curadoria divergente.")
        extrair(projeto, wiki)
        restaurar(pacote, wiki / "local")
        try:
            wiki.rename(destino)
        except OSError:
            if not manifesto.is_file():
                raise
