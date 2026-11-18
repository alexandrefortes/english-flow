"""Exporta somente a edição materializada da wiki para um pacote de curadoria."""
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


MASCARA = "[credencial omitida]"
CHAVE = re.compile(r"-----BEGIN (?P<tipo>(?:RSA |DSA |EC |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?)-----"
                   r".*?-----END (?P=tipo)-----", re.DOTALL)
TOKEN = re.compile(r"(?<![\w-])(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}|"
                   r"xox[baprs]-[0-9]{8,}-[A-Za-z0-9-]{12,}|(?:AKIA|ASIA)[A-Z0-9]{16}|"
                   r"AIza[0-9A-Za-z_-]{35}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}T3BlbkFJ[A-Za-z0-9_-]{12,})")
ATRIBUTO = re.compile(r"""(?ix)(\b(?:aws_secret_access_key|api[_-]?key|client[_-]?secret|access[_-]?token|
                     refresh[_-]?token|password|passwd)\b["']?\s*[:=]\s*["']?|
                     \bAuthorization:\s*(?:Basic|Bearer)\s+)([A-Za-z0-9+/_=.~-]{16,})""")
URL_ASSINADA = re.compile(r"(?i)([?&](?:X-Amz-(?:Signature|Security-Token|Credential)|Signature|"
                          r"AWSAccessKeyId|access_token|api_key)=)[^&#\s<>\"'`]+")
MIDIA = re.compile(r"(data:(?:image|audio|video)/[\w.+-]+(?:;[\w=.-]+)*;base64,)[A-Za-z0-9+/=]+", re.I)


def limpar(texto):
    texto = CHAVE.sub(MASCARA, texto)
    texto = URL_ASSINADA.sub(lambda m: m[1] + "REDACTED", texto)
    texto = TOKEN.sub(MASCARA, texto)
    texto = MIDIA.sub("[mídia embutida omitida]", texto)
    return ATRIBUTO.sub(lambda m: m[1] + MASCARA, texto)


def tem_marca(texto):
    return MASCARA in texto or "[mídia embutida omitida]" in texto or "=REDACTED" in texto


def grafo_limpo(origem, destino, contagem):
    with closing(sqlite3.connect(origem.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(destino)) as db:
            src.backup(db)
            db.execute("PRAGMA secure_delete=ON")
            for campo in ("titulo", "texto"):
                with db:
                    for chave, texto in db.execute(f"SELECT id,{campo} FROM nos WHERE {campo} IS NOT NULL"):
                        seguro = limpar(texto)
                        if seguro != texto:
                            db.execute(f"UPDATE nos SET {campo}=? WHERE id=?", (seguro, chave))
                        if tem_marca(seguro):
                            contagem["campos_do_grafo"] += 1
            with db:
                db.execute("UPDATE nos SET caminho=NULL WHERE tipo='captura'")
                for origem_id, destino_id, relacao, trecho in db.execute(
                        "SELECT origem,destino,relacao,trecho FROM ligacoes WHERE trecho IS NOT NULL"):
                    seguro = limpar(trecho)
                    if seguro != trecho:
                        db.execute("UPDATE ligacoes SET trecho=? WHERE origem=? AND destino=? AND relacao=?",
                                   (seguro, origem_id, destino_id, relacao))
                    if tem_marca(seguro):
                        contagem["campos_do_grafo"] += 1
            db.execute("VACUUM")
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Grafo inválido após a exportação.")


def adicionar(tar, nome, conteudo):
    item = tarfile.TarInfo(nome)
    item.size = len(conteudo)
    tar.addfile(item, BytesIO(conteudo))


def sha(path):
    with path.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def empacotar(local, saida):
    local = local.resolve()
    saida.mkdir(parents=True, exist_ok=True)
    if (saida / "acervo.json").exists() or any(saida.glob("wiki-*.bin")):
        raise ValueError("Exporte em uma pasta sem pacote anterior.")
    manifesto = json.loads((local / "manifesto.json").read_bytes())
    for nome in list(manifesto["arquivos"]):
        if nome.startswith("doist/imagens/"):
            del manifesto["arquivos"][nome]
        elif Path(nome).suffix not in {".md", ".json", ".sqlite3"}:
            raise ValueError(f"Conteúdo inesperado na edição textual: {nome}")
    manifesto["totais"]["imagens"] = 0
    contagem = Counter()
    with TemporaryDirectory() as tmp:
        banco = Path(tmp) / "grafo.sqlite3"
        arquivo = Path(tmp) / "wiki.tar.gz"
        if sha(local / banco.name) != manifesto["arquivos"][banco.name]:
            raise ValueError("Grafo de origem divergente.")
        grafo_limpo(local / banco.name, banco, contagem)
        print("Grafo conferido. Empacotando a edição.", flush=True)
        with arquivo.open("wb") as stream, gzip.GzipFile(fileobj=stream, mode="wb", compresslevel=5, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w|") as tar:
                adicionar(tar, ".edicao-local", (local / ".edicao-local").read_bytes())
                for i, (nome, original) in enumerate(sorted(manifesto["arquivos"].items()), 1):
                    path = (local / nome).resolve()
                    if not path.is_relative_to(local):
                        raise ValueError(f"Arquivo fora da edição: {nome}")
                    if nome == banco.name:
                        item = tarfile.TarInfo(nome)
                        item.size = banco.stat().st_size
                        with banco.open("rb") as inp:
                            tar.addfile(item, inp)
                        manifesto["arquivos"][nome] = sha(banco)
                        continue
                    dados = path.read_bytes()
                    if hashlib.sha256(dados).hexdigest() != original:
                        raise ValueError(f"Arquivo local divergente: {nome}")
                    if path.suffix in (".md", ".json"):
                        texto = dados.decode("utf-8")
                        if nome.startswith("doist/") and path.suffix == ".md":
                            texto = re.sub(r"(?m)^!\[Captura Doist\]\(imagens/[^)\n]+\)\r?\n(?:\r?\n)?", "", texto, count=1)
                        if nome == "index.md":
                            texto = texto.replace("O conteúdo, as imagens e a navegação estão dentro da wiki.",
                                                  "Esta edição de curadoria reúne o texto e a navegação offline.")
                        if nome == "anexos/extracao.json":
                            catalogo = json.loads(texto)
                            raiz_origem = str(local.parent.parent)
                            alterado = False
                            for registro in catalogo.values():
                                if registro.get("note"):
                                    anterior = registro["note"]
                                    registro["note"] = limpar(anterior.replace(raiz_origem, "<projeto>"))
                                    alterado |= anterior != registro["note"]
                            seguro = (json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n") if alterado else texto
                        else:
                            seguro = limpar(texto)
                        if seguro != texto and path.suffix == ".json":
                            json.loads(seguro)
                        if tem_marca(seguro):
                            contagem["arquivos_de_texto"] += 1
                        dados = seguro.encode("utf-8")
                        manifesto["arquivos"][nome] = hashlib.sha256(dados).hexdigest()
                    adicionar(tar, nome, dados)
                    if i % 10000 == 0:
                        print(f"{i} arquivos conferidos.", flush=True)
                dados = (json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
                adicionar(tar, "manifesto.json", dados)
        partes = []
        with arquivo.open("rb") as stream:
            while bloco := stream.read(32 * 1024 * 1024):
                nome = f"wiki-{len(partes) + 1:03d}.bin"
                (saida / nome).write_bytes(bloco)
                partes.append({"arquivo": nome, "bytes": len(bloco), "sha256": hashlib.sha256(bloco).hexdigest()})
        meta = {"versao": 1, "manifesto_sha256": hashlib.sha256(dados).hexdigest(),
                "arquivos_verificados": len(manifesto["arquivos"]), "totais": manifesto["totais"],
                "mascaramento": dict(contagem), "partes": partes}
        (saida / "acervo.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wiki_local", type=Path)
    parser.add_argument("saida", type=Path)
    args = parser.parse_args()
    empacotar(args.wiki_local, args.saida)
