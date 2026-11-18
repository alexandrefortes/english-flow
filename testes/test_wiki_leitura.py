from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wiki"))
from ingerir_acervo import Edicao
from ingerir_anexos import escrever_pagina


class PaginaDeAnexo(unittest.TestCase):
    def setUp(self):
        self.edicao = Edicao(Path(self.enterContext(TemporaryDirectory())))
        self.chave = "zulip-anexo-" + "1" * 32
        self.pagina = self.edicao.pasta / "anexos" / (self.chave + ".md")

    def test_preserva_texto_literal_e_separa_sinais_do_contexto(self):
        texto = "what do you mean by that?\n\n  ```\n"
        referencia = ("zulip-msg-1", "../zulip/canal-2/topico.md#zulip-msg-1", "general")
        contexto = {"zulip-msg-1": [("vocabulario", "curado", None)]}
        escrever_pagina(self.edicao, self.chave, ("extraido", texto, "ocr", ""), [referencia], contexto)
        pagina = self.pagina.read_bytes().decode()
        self.assertEqual(pagina.split("---\n\n", 1)[0].splitlines(), [
            "---",
            'learning_uses: ["conversacao", "dia-a-dia", "esclarecer", "vocabulario"]',
            'learning_from_text: ["conversacao", "dia-a-dia", "esclarecer"]',
            'learning_from_context: ["vocabulario"]',
        ])
        self.assertIn("## backlinks\n\n- [zulip-msg-1](" + referencia[1] + ")", pagina)
        self.assertIn("## Content\n\n````text\n" + texto + "````\n", pagina)

    def test_anexo_sem_texto_conserva_navegacao(self):
        escrever_pagina(self.edicao, self.chave, ("vazio", None, "ocr", ""), [], {})
        pagina = self.pagina.read_text(encoding="utf-8")
        self.assertIn('learning_uses: ["leitura-contextual"]', pagina)
        self.assertIn("[Índice de anexos](index.md)", pagina)
        self.assertNotIn("## Content", pagina)
        self.assertNotIn("## backlinks", pagina)
