import argparse
from collections import Counter
from contextlib import closing
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import tarfile
from tempfile import TemporaryDirectory


MASK = "[credencial omitida]"
KEY = re.compile(r"-----BEGIN (?P<tipo>(?:RSA |DSA |EC |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?)-----"
                   r".*?-----END (?P=tipo)-----", re.DOTALL)
TOKEN = re.compile(r"(?<![\w-])(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}|"
                   r"xox[baprs]-[0-9]{8,}-[A-Za-z0-9-]{12,}|(?:AKIA|ASIA)[A-Z0-9]{16}|"
                   r"AIza[0-9A-Za-z_-]{35}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}T3BlbkFJ[A-Za-z0-9_-]{12,})")
ATTRIBUTE = re.compile(r"""(?ix)(\b(?:aws_secret_access_key|api[_-]?key|client[_-]?secret|access[_-]?token|
                     refresh[_-]?token|password|passwd)\b["']?\s*[:=]\s*["']?|
                     \bAuthorization:\s*(?:Basic|Bearer)\s+)([A-Za-z0-9+/_=.~-]{16,})""")
SIGNED_URL = re.compile(r"(?i)([?&](?:X-Amz-(?:Signature|Security-Token|Credential)|Signature|"
                          r"AWSAccessKeyId|access_token|api_key)=)[^&#\s<>\"'`]+")
INLINE_MEDIA = re.compile(r"(data:(?:image|audio|video)/[\w.+-]+(?:;[\w=.-]+)*;base64,)[A-Za-z0-9+/=]+", re.I)


def clean_text(texto):
    texto = KEY.sub(MASK, texto)
    texto = SIGNED_URL.sub(lambda m: m[1] + "REDACTED", texto)
    texto = TOKEN.sub(MASK, texto)
    texto = INLINE_MEDIA.sub("[mídia embutida omitida]", texto)
    return ATTRIBUTE.sub(lambda m: m[1] + MASK, texto)


def contains_marker(texto):
    return MASK in texto or "[mídia embutida omitida]" in texto or "=REDACTED" in texto


def clean_graph(origem, destino, contagem):
    with closing(sqlite3.connect(origem.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(destino)) as db:
            src.backup(db)
            db.execute("PRAGMA secure_delete=ON")
            for campo in ("titulo", "texto"):
                with db:
                    for chave, texto in db.execute(f"SELECT id,{campo} FROM nos WHERE {campo} IS NOT NULL"):
                        seguro = clean_text(texto)
                        if seguro != texto:
                            db.execute(f"UPDATE nos SET {campo}=? WHERE id=?", (seguro, chave))
                        if contains_marker(seguro):
                            contagem["campos_do_grafo"] += 1
            with db:
                db.execute("UPDATE nos SET caminho=NULL WHERE tipo='captura'")
                for origem_id, destino_id, relacao, trecho in db.execute(
                        "SELECT origem,destino,relacao,trecho FROM ligacoes WHERE trecho IS NOT NULL"):
                    seguro = clean_text(trecho)
                    if seguro != trecho:
                        db.execute("UPDATE ligacoes SET trecho=? WHERE origem=? AND destino=? AND relacao=?",
                                   (seguro, origem_id, destino_id, relacao))
                    if contains_marker(seguro):
                        contagem["campos_do_grafo"] += 1
            db.execute("VACUUM")
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Invalid graph after export.")


def add_member(tar, nome, conteudo):
    item = tarfile.TarInfo(nome)
    item.size = len(conteudo)
    tar.addfile(item, BytesIO(conteudo))


def sha(path):
    with path.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def published_index(text):
    return (text.replace("O conteúdo, as imagens e a navegação estão dentro da wiki.",
                         "Esta edição de curadoria reúne o texto e a navegação offline.")
            .replace("Consulte a imagem ao usar o OCR da Doist.",
                     "Leia a transcrição da Doist. O link da publicação identifica a origem da captura.")
            .replace(" capturas com OCR.", " transcrições de capturas da Doist.")
            .replace(" capturas da Doist](doist/index.md)", " transcrições da Doist](doist/index.md)"))


def pack(local, saida):
    local = local.resolve()
    saida.mkdir(parents=True, exist_ok=True)
    if (saida / "manifest.json").exists() or any(saida.glob("wiki-*.bin")):
        raise ValueError("Use a directory without an existing source archive.")
    manifesto = json.loads((local / "manifesto.json").read_bytes())
    for nome in list(manifesto["arquivos"]):
        if nome.startswith("doist/imagens/"):
            del manifesto["arquivos"][nome]
        elif Path(nome).suffix not in {".md", ".json", ".sqlite3"}:
            raise ValueError(f'Unexpected file in the text edition: {nome}')
    manifesto["totais"]["imagens"] = 0
    contagem = Counter()
    with TemporaryDirectory() as tmp:
        banco = Path(tmp) / "grafo.sqlite3"
        arquivo = Path(tmp) / "wiki.tar.gz"
        if sha(local / banco.name) != manifesto["arquivos"][banco.name]:
            raise ValueError("Source graph checksum mismatch.")
        clean_graph(local / banco.name, banco, contagem)
        print("Graph verified. Building the archive.", flush=True)
        with arquivo.open("wb") as stream, gzip.GzipFile(fileobj=stream, mode="wb", compresslevel=5, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w|") as tar:
                add_member(tar, ".edicao-local", (local / ".edicao-local").read_bytes())
                for i, (nome, original) in enumerate(sorted(manifesto["arquivos"].items()), 1):
                    path = (local / nome).resolve()
                    if not path.is_relative_to(local):
                        raise ValueError(f'File outside the edition directory: {nome}')
                    if nome == banco.name:
                        item = tarfile.TarInfo(nome)
                        item.size = banco.stat().st_size
                        with banco.open("rb") as inp:
                            tar.addfile(item, inp)
                        manifesto["arquivos"][nome] = sha(banco)
                        continue
                    dados = path.read_bytes()
                    if hashlib.sha256(dados).hexdigest() != original:
                        raise ValueError(f'Local file checksum mismatch: {nome}')
                    if path.suffix in (".md", ".json"):
                        texto = dados.decode("utf-8")
                        if nome.startswith("doist/") and path.suffix == ".md":
                            texto = re.sub(r"(?m)^!\[Captura Doist\]\(imagens/[^)\n]+\)\r?\n(?:\r?\n)?", "", texto, count=1)
                        if nome == "index.md":
                            texto = published_index(texto)
                        if nome == "anexos/extracao.json":
                            catalogo = json.loads(texto)
                            raiz_origem = str(local.parent.parent)
                            alterado = False
                            for registro in catalogo.values():
                                if registro.get("note"):
                                    anterior = registro["note"]
                                    registro["note"] = clean_text(anterior.replace(raiz_origem, "<projeto>"))
                                    alterado |= anterior != registro["note"]
                            seguro = (json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n") if alterado else texto
                        else:
                            seguro = clean_text(texto)
                        if seguro != texto and path.suffix == ".json":
                            json.loads(seguro)
                        if contains_marker(seguro):
                            contagem["arquivos_de_texto"] += 1
                        dados = seguro.encode("utf-8")
                        manifesto["arquivos"][nome] = hashlib.sha256(dados).hexdigest()
                    add_member(tar, nome, dados)
                    if i % 10000 == 0:
                        print(f'Verified {i} files.', flush=True)
                dados = (json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
                add_member(tar, "manifesto.json", dados)
        partes = []
        with arquivo.open("rb") as stream:
            while bloco := stream.read(32 * 1024 * 1024):
                nome = f"wiki-{len(partes) + 1:03d}.bin"
                (saida / nome).write_bytes(bloco)
                partes.append({"arquivo": nome, "bytes": len(bloco), "sha256": hashlib.sha256(bloco).hexdigest()})
        meta = {"versao": 1, "manifesto_sha256": hashlib.sha256(dados).hexdigest(),
                "arquivos_verificados": len(manifesto["arquivos"]), "totais": manifesto["totais"],
                "mascaramento": dict(contagem), "partes": partes}
        (saida / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Build the source archive from the local wiki.')
    parser.add_argument("local_wiki", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    pack(args.local_wiki, args.output_directory)
