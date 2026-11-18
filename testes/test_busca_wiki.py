import gzip
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "plugins/ingles-para-o-trabalho"
sys.path.insert(0, str(PLUGIN))
from busca_wiki import abrir, buscar, consultar


class BuscaWiki(unittest.TestCase):
    def setUp(self):
        self.wiki = Path(self.enterContext(TemporaryDirectory()))
        self.topico = self.wiki / "local/zulip/canal-2/zulip-topico-exemplo.md"
        self.topico.parent.mkdir(parents=True)
        self.pedido = "Could we move the deadline?"
        self.resposta = ("Sam [said](https://chat.zulip.org/#narrow/channel/2/topic/Review/near/1):\n"
                         "```quote\n" + self.pedido + "\n```\n\nFriday works.")
        self.escrever(self.pedido, self.resposta)

    def escrever(self, *turnos):
        texto = "# Review\n\n[Discussão no Zulip](<https://chat.zulip.org/#narrow/channel/2/topic/Review>)\n\n"
        for n, turno in enumerate(turnos, 1):
            texto += f"## zulip-msg-{n}\n\nSam\n\n````text\n{turno}\n````\n\n"
        self.topico.write_text(texto, encoding="utf-8")

    def buscar(self, **kw):
        return consultar(self.wiki, buscar, **kw)["matches"]

    def abrir(self, chave):
        return consultar(self.wiki, abrir, chave=chave)

    def test_citacao_ancorada_e_repeticao_independente(self):
        self.escrever(self.pedido, self.resposta, self.pedido)
        guia = self.wiki / "revisao.md"
        guia.write_text(f'# Pedidos\n\nO original “{self.pedido}” está na [fonte](fontes.md#zulip-msg-1).\n')
        matches = self.buscar(text=self.pedido)
        self.assertEqual([(r["id"], r["citar_id"]) for r in matches],
                         [("zulip-msg-1", "zulip-msg-1"), ("zulip-msg-3", "zulip-msg-3")])
        pagina, = self.buscar(text=self.pedido, kind="didatica")
        self.assertEqual((pagina["id"], pagina["citar_id"]), ("wiki/revisao.md", "zulip-msg-1"))

    def test_edicao_remocao_e_mudanca_de_contexto(self):
        chave = "zulip-msg-1"
        item = self.abrir(chave)
        self.assertEqual(item["contexto"][0]["id"], "zulip-msg-2")
        e = {"trecho": self.pedido, "funcao": "pedido", "usos": ["negociar-prazo"], "assinatura": item["assinatura"]}
        (self.wiki / "curadoria.json").write_text(json.dumps({chave: [e]}))
        with gzip.open(self.wiki / "decisoes.tsv.gz", "wt") as out:
            out.write(f"{chave}\tmensagem\t{item['assinatura']}\tconferido\tpedido\n")
        match, = self.buscar(text=self.pedido, curation="conferido")
        self.assertEqual(match["id"], chave)
        self.escrever(self.pedido, "That's a quotation from the training manual.")
        self.assertFalse(self.buscar(text=self.pedido, curation="conferido"))
        self.assertEqual(self.abrir(chave)["estado"], "pendente")
        self.escrever("Can we talk tomorrow?")
        self.assertFalse(self.buscar(text=self.pedido))
        self.assertEqual(self.buscar(text="talk tomorrow")[0]["id"], chave)
        with self.assertRaises(ValueError):
            self.abrir("zulip-msg-2")
        self.topico.unlink()
        self.assertFalse(self.buscar(text="talk tomorrow"))
        with self.assertRaises(ValueError):
            self.abrir(chave)

    def test_sem_transcricao_e_varias_origens(self):
        pasta = self.wiki / "local/anexos"
        pasta.mkdir()
        ids = ["zulip-anexo-a", "zulip-anexo-b"]
        (pasta / "extracao.json").write_text(json.dumps({i: {"name": i + ".png", "transcription": "vazio"}
                                                        for i in ids}))
        for i in ids:
            (pasta / (i + ".md")).write_text("## backlinks\n\n- [zulip-msg-1](../zulip/x#zulip-msg-1)\n")
        item, = self.buscar(text=self.pedido, kind="anexo")
        self.assertEqual((item["correspondencia"], item["citar_id"]), ("contexto", "zulip-msg-1"))
        self.assertEqual(item["anexos"], ids)
        for i in ids:
            ref, = self.buscar(text=i + ".png")
            self.assertEqual(ref["correspondencia"], "arquivo")
            self.assertEqual(ref["origens"][0]["id"], item["citar_id"])
