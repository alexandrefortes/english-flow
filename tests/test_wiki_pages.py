from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.curation.build_wiki import WikiEdition
from tools.curation.build_attachments import write_attachment_page


class AttachmentPageTests(unittest.TestCase):
    def setUp(self):
        self.edicao = WikiEdition(Path(self.enterContext(TemporaryDirectory())))
        self.chave = "zulip-anexo-" + "1" * 32
        self.pagina = self.edicao.pasta / "anexos" / (self.chave + ".md")

    def test_preserves_literal_text_and_context_labels(self):
        texto = "what do you mean by that?\n\n  ```\n"
        referencia = ("zulip-msg-1", "../zulip/canal-2/topico.md#zulip-msg-1", "general")
        contexto = {"zulip-msg-1": [("vocabulario", "curado", None)]}
        write_attachment_page(self.edicao, self.chave, ("extraido", texto, "ocr", ""), [referencia], contexto)
        pagina = self.pagina.read_bytes().decode()
        self.assertEqual(pagina.split("---\n\n", 1)[0].splitlines(), [
            "---",
            'learning_uses: ["conversacao", "dia-a-dia", "esclarecer", "vocabulario"]',
            'learning_from_text: ["conversacao", "dia-a-dia", "esclarecer"]',
            'learning_from_context: ["vocabulario"]',
        ])
        self.assertIn("## backlinks\n\n- [zulip-msg-1](" + referencia[1] + ")", pagina)
        self.assertIn("## Content\n\n````text\n" + texto + "````\n", pagina)

    def test_attachment_without_text_preserves_navigation(self):
        write_attachment_page(self.edicao, self.chave, ("vazio", None, "ocr", ""), [], {})
        pagina = self.pagina.read_text(encoding="utf-8")
        self.assertIn('learning_uses: ["leitura-contextual"]', pagina)
        self.assertIn("[Índice de anexos](index.md)", pagina)
        self.assertNotIn("## Content", pagina)
        self.assertNotIn("## backlinks", pagina)
