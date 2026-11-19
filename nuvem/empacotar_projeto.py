"""Atualiza as páginas e as decisões da wiki incluídas na distribuição do plugin."""
import gzip
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from empacotar import adicionar, sha


RAIZ = Path(__file__).resolve().parents[1]
PACOTE = RAIZ / "plugins/ingles-para-o-trabalho/acervo"


def paginas_publicadas():
    wiki = RAIZ / "wiki"
    saida = subprocess.check_output(["git", "ls-files", "-z"], cwd=wiki)
    return [wiki / nome for nome in saida.decode("utf-8").split("\0")
            if nome and Path(nome).suffix in {".md", ".json", ".gz"}]


def empacotar():
    with TemporaryDirectory(dir=PACOTE) as pasta:
        pacote = Path(pasta) / "projeto.tar.gz"
        with pacote.open("wb") as arquivo, gzip.GzipFile(filename="", fileobj=arquivo, mode="wb", mtime=0, compresslevel=6) as gz:
            with tarfile.open(fileobj=gz, mode="w|") as tar:
                for pagina in paginas_publicadas():
                    adicionar(tar, pagina.relative_to(RAIZ / "wiki").as_posix(), pagina.read_bytes())
        assinatura = Path(pasta) / "projeto.sha256"
        assinatura.write_text(sha(pacote) + "\n", encoding="ascii", newline="\n")
        pacote.replace(PACOTE / pacote.name)
        assinatura.replace(PACOTE / assinatura.name)


if __name__ == "__main__":
    empacotar()
