import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

import preparar_nuvem
from construir_grafo import ESQUEMA
from ingerir_acervo import Edicao

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nuvem"))
from empacotar import empacotar, limpar


class PacoteNuvem(unittest.TestCase):
    def test_edicao_textual_integridade_e_preservacao_do_original(self):
        with TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            local, pacote, destino = (raiz / nome for nome in ("origem", "pacote", "restaurado"))
            edicao = Edicao(local)
            corpo = "Can we wait until Friday?"
            token = "xoxb-" + "9" * 11 + "-" + "T" * 27
            nome = "doist/doist-prazo.md"
            edicao.escrever(nome, f"![Captura Doist](imagens/doist-prazo.png)\n\n{corpo}\n{token}\n")
            arquivo = raiz / "imagem.png"
            arquivo.write_bytes(b"fixture de imagem")
            edicao.copiar("doist/imagens/doist-prazo.png", arquivo)
            db_path = raiz / "grafo.sqlite3"
            db = sqlite3.connect(db_path)
            with db:
                db.executescript(ESQUEMA)
                db.execute("INSERT INTO nos(id,tipo,titulo,texto,caminho) VALUES (?,?,?,?,?)",
                           ("doist-prazo", "captura", "Prazo", corpo + " " + token, "capturas/prazo.png"))
            db.close()
            edicao.copiar("grafo.sqlite3", db_path)
            edicao.finalizar({"capturas": 1, "imagens": 1})
            empacotar(local, pacote)
            preparar_nuvem.restaurar(pacote, destino)
            self.assertEqual(preparar_nuvem.restaurar(pacote, destino), "Edição já presente.")
            self.assertIn(corpo, (destino / nome).read_text(encoding="utf-8"))
            self.assertNotIn("imagens/", (destino / nome).read_text(encoding="utf-8"))
            self.assertNotIn(token.encode(), (destino / "grafo.sqlite3").read_bytes())
            self.assertFalse(list(destino.rglob("*.png")))
            self.assertIn(token.encode(), (local / nome).read_bytes())
            db = sqlite3.connect(destino / "grafo.sqlite3")
            self.assertEqual(db.execute("select texto,caminho from nos").fetchone(), (corpo + " [credencial omitida]", None))
            db.close()
            with self.assertRaisesRegex(ValueError, "outro conteúdo"):
                preparar_nuvem.restaurar(pacote, local)
            meta = json.loads((pacote / "acervo.json").read_bytes())
            (pacote / meta["partes"][0]["arquivo"]).write_bytes(b"parte danificada")
            with self.assertRaisesRegex(ValueError, "Parte divergente"):
                preparar_nuvem.restaurar(pacote, raiz / "falhou")
            self.assertFalse((raiz / "falhou").exists())

    def test_preserva_frase_e_oculta_assinatura_com_a_chave(self):
        chave = "-----BEGIN PRIVATE KEY-----\naGVsbG8=\n-----END PRIVATE KEY-----"
        texto = f"Could you review it? {chave}\nhttps://example.invalid/?X-Amz-Signature=fake12345"
        self.assertEqual(limpar(texto), "Could you review it? [credencial omitida]\nhttps://example.invalid/?X-Amz-Signature=REDACTED")
        self.assertEqual(limpar("See data:image/png;base64,YWJj. Deadline?"),
                         "See [mídia embutida omitida]. Deadline?")
