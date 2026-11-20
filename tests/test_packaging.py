import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest

from tools import ROOT
from tools.packaging import restore_wiki
from edition import bundled_cache_path, file_hash, prepare_bundled_wiki
from tools.curation.build_graph import SCHEMA
from tools.curation.build_wiki import WikiEdition

from tools.packaging.pack_sources import add_member, pack, clean_text


class PackagingTests(unittest.TestCase):
    def test_bundled_edition_includes_sources_and_reviews(self):
        with TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            local, pacote, destino = (raiz / nome for nome in ("origem", "pacote", "cache/wiki"))
            edicao = WikiEdition(local)
            edicao.write_page("index.md", "# Conversas\n\nConsulte a imagem ao usar o OCR da Doist.\n")
            banco = raiz / "grafo.sqlite3"
            with sqlite3.connect(banco) as db:
                db.executescript(SCHEMA)
            db.close()
            edicao.copiar(banco.name, banco)
            edicao.finish({"imagens": 0})
            subprocess.run(
                [sys.executable, "-B", "-m", "tools.packaging.pack_sources", local, pacote],
                cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
            )

            projeto = pacote / "project.tar.gz"
            with tarfile.open(projeto, "w:gz") as tar:
                add_member(tar, "situacoes.md", b"# Situacoes\n")
            selo = pacote / "project.sha256"
            selo.write_text("0" * 64)
            antigo = bundled_cache_path(pacote)
            with self.assertRaisesRegex(ValueError, "Editorial archive checksum mismatch"):
                prepare_bundled_wiki(pacote, destino)
            self.assertFalse(destino.exists())
            selo.write_text(file_hash(projeto))
            self.assertNotEqual(antigo, bundled_cache_path(pacote))
            with ThreadPoolExecutor(max_workers=2) as executor:
                a = executor.submit(prepare_bundled_wiki, pacote, destino)
                b = executor.submit(prepare_bundled_wiki, pacote, destino)
                a.result()
                b.result()
            self.assertEqual((destino / "situacoes.md").read_bytes(), b"# Situacoes\n")
            self.assertIn("Leia a transcrição da Doist.", (destino / "local/index.md").read_text(encoding="utf-8"))
            self.assertIn("Consulte a imagem", (local / "index.md").read_text(encoding="utf-8"))

    def test_text_edition_integrity_and_original_files(self):
        with TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            local, pacote, destino = (raiz / nome for nome in ("origem", "pacote", "restaurado"))
            edicao = WikiEdition(local)
            corpo = "Can we wait until Friday?"
            token = "xoxb-" + "9" * 11 + "-" + "T" * 27
            nome = "doist/doist-prazo.md"
            edicao.write_page(nome, f"![Captura Doist](imagens/doist-prazo.png)\n\n{corpo}\n{token}\n")
            arquivo = raiz / "imagem.png"
            arquivo.write_bytes(b"fixture de imagem")
            edicao.copiar("doist/imagens/doist-prazo.png", arquivo)
            db_path = raiz / "grafo.sqlite3"
            db = sqlite3.connect(db_path)
            with db:
                db.executescript(SCHEMA)
                db.execute("INSERT INTO nos(id,tipo,titulo,texto,caminho) VALUES (?,?,?,?,?)",
                           ("doist-prazo", "captura", "Prazo", corpo + " " + token, "capturas/prazo.png"))
            db.close()
            edicao.copiar("grafo.sqlite3", db_path)
            edicao.finish({"capturas": 1, "imagens": 1})
            pack(local, pacote)
            restore_wiki.restore(pacote, destino)
            self.assertEqual(restore_wiki.restore(pacote, destino), "Edition already present.")
            self.assertIn(corpo, (destino / nome).read_text(encoding="utf-8"))
            self.assertNotIn("imagens/", (destino / nome).read_text(encoding="utf-8"))
            self.assertNotIn(token.encode(), (destino / "grafo.sqlite3").read_bytes())
            self.assertFalse(list(destino.rglob("*.png")))
            self.assertIn(token.encode(), (local / nome).read_bytes())
            db = sqlite3.connect(destino / "grafo.sqlite3")
            self.assertEqual(db.execute("select texto,caminho from nos").fetchone(), (corpo + " [credencial omitida]", None))
            db.close()
            with self.assertRaisesRegex(ValueError, "different data"):
                restore_wiki.restore(pacote, local)
            meta = json.loads((pacote / "manifest.json").read_bytes())
            (pacote / meta["partes"][0]["arquivo"]).write_bytes(b"parte danificada")
            with self.assertRaisesRegex(ValueError, "Archive part checksum mismatch"):
                restore_wiki.restore(pacote, raiz / "falhou")
            self.assertFalse((raiz / "falhou").exists())

    def test_preserves_sentence_and_masks_signature_and_key(self):
        chave = "-----BEGIN PRIVATE KEY-----\naGVsbG8=\n-----END PRIVATE KEY-----"
        texto = f"Could you review it? {chave}\nhttps://example.invalid/?X-Amz-Signature=fake12345"
        self.assertEqual(clean_text(texto), "Could you review it? [credencial omitida]\nhttps://example.invalid/?X-Amz-Signature=REDACTED")
        self.assertEqual(clean_text("See data:image/png;base64,YWJj. Deadline?"),
                         "See [mídia embutida omitida]. Deadline?")
