from contextlib import closing
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


from tools.curation.review_items import record
from tools.curation.build_wiki import source_text
from wiki_search import abrir, buscar, consultar
from wiki_index import connect


class WikiSearchTests(unittest.TestCase):
    def setUp(self):
        self.wiki = Path(self.enterContext(TemporaryDirectory()))
        self.topico = self.wiki / "local/zulip/canal-2/zulip-topico-exemplo.md"
        self.topico.parent.mkdir(parents=True)
        self.pedido = "Could we move the deadline?"
        self.resposta = ("Sam [said](https://chat.zulip.org/#narrow/channel/2/topic/Review/near/1):\n"
                         "```quote\n" + self.pedido + "\n```\n\nFriday works.")
        self.write_page(self.pedido, self.resposta)

    def write_page(self, *turnos):
        texto = "# Review\n\n[Discussão no Zulip](<https://chat.zulip.org/#narrow/channel/2/topic/Review>)\n\n"
        for n, turno in enumerate(turnos, 1):
            texto += f"## zulip-msg-{n}\n\nSam\n\n" + source_text(turno)
        self.topico.write_text(texto, encoding="utf-8")

    def buscar(self, **kw):
        return consultar(self.wiki, buscar, **kw)["matches"]

    def abrir(self, chave):
        return consultar(self.wiki, abrir, chave=chave)

    def test_anchored_quote_and_independent_occurrence(self):
        self.write_page(self.pedido, self.resposta, self.pedido)
        guia = self.wiki / "revisao.md"
        guia.write_text(f'# Pedidos\n\nO original “{self.pedido}” está na [fonte](fontes.md#zulip-msg-1).\n')
        matches = self.buscar(text=self.pedido)
        self.assertEqual([(r["id"], r["citar_id"]) for r in matches],
                         [("zulip-msg-1", "zulip-msg-1"), ("zulip-msg-3", "zulip-msg-3")])
        pagina, = self.buscar(text=self.pedido, kind="didatica")
        self.assertEqual((pagina["id"], pagina["citar_id"]), ("wiki/revisao.md", "zulip-msg-1"))

    def test_replies_with_translated_and_nested_quotes(self):
        interna = self.resposta.replace("[said]", "[发言道]").replace("):", ")：")
        replica = ("Jo [disse](https://chat.zulip.org/#narrow/channel/2/topic/Review/near/2):\n"
                   "````quote\n" + interna + "\n````\n\nThanks.")
        self.write_page(self.pedido, interna, replica)
        original, = self.buscar(text=self.pedido)
        self.assertEqual(original["id"], "zulip-msg-1")
        resposta, = self.buscar(text="Friday works.")
        self.assertEqual(resposta["id"], "zulip-msg-2")

    def test_search_preserves_multiline_source_text(self):
        texto = "Could we  move\n\nthe deadline?"
        self.write_page(texto)
        item, = self.buscar(text=self.pedido)
        self.assertEqual((item["id"], item["trecho"]), ("zulip-msg-1", texto))

    def test_catalog_pagination_counts_characters(self):
        texto = json.dumps(["ação " * 14000, "último"], ensure_ascii=False)
        (self.wiki / "catalogo.json").write_text(texto, encoding="utf-8-sig")
        for offset in (0, 65535, 65536, len(texto) - 3, len(texto), len(texto) + 10):
            with self.subTest(offset=offset):
                item = consultar(self.wiki, abrir, chave="wiki/catalogo.json", offset=offset, limit=3)
                self.assertEqual(item["texto"], texto[offset:offset + 3])
                self.assertEqual(item["next_offset"], offset + 3 if offset + 3 < len(texto) else None)

    def test_edit_delete_and_change_context(self):
        chave = "zulip-msg-1"
        item = self.abrir(chave)
        self.assertEqual(item["contexto"][0]["id"], "zulip-msg-2")
        e = {"trecho": self.pedido, "funcao": "pedido", "usos": ["negociar-prazo"], "assinatura": item["assinatura"]}
        (self.wiki / "curadoria.json").write_text(json.dumps({chave: [e]}))
        with gzip.open(self.wiki / "decisoes.tsv.gz", "wt") as out:
            out.write(f"{chave}\tmensagem\t{item['assinatura']}\tconferido\tpedido\n")
        match, = self.buscar(text=self.pedido, curation="conferido")
        self.assertEqual(match["id"], chave)
        self.write_page(self.pedido, "That's a quotation from the training manual.")
        self.assertFalse(self.buscar(text=self.pedido, curation="conferido"))
        self.assertEqual(self.abrir(chave)["estado"], "pendente")
        self.write_page("Can we talk tomorrow?")
        self.assertFalse(self.buscar(text=self.pedido))
        self.assertEqual(self.buscar(text="talk tomorrow")[0]["id"], chave)
        with self.assertRaises(ValueError):
            self.abrir("zulip-msg-2")
        self.topico.unlink()
        self.assertFalse(self.buscar(text="talk tomorrow"))
        with self.assertRaises(ValueError):
            self.abrir(chave)

    def test_review_batch_preserves_pending_and_checks_evidence(self):
        chave = "zulip-msg-1"
        json_curadoria = self.wiki / "curadoria.json"
        json_curadoria.write_text("{}")
        lote = self.wiki.parent / (self.wiki.name + "-revisoes.jsonl")
        self.addCleanup(lote.unlink, missing_ok=True)
        item = self.abrir(chave)
        evidencia = {"trecho": self.pedido, "funcao": "pedido", "usos": ["negociar-prazo"]}
        decisao = dict(id=chave, assinatura=item["assinatura"], tipo="mensagem",
                       estado="conferido", motivo="pedido de alteração", evidencias=[evidencia])
        outra = dict(decisao, id="zulip-msg-2", assinatura=self.abrir("zulip-msg-2")["assinatura"],
                     evidencias=[dict(evidencia, trecho="not present")])
        lote.write_text(json.dumps(decisao) + "\n" + json.dumps(outra))
        with closing(connect(self.wiki)) as db:
            with self.assertRaises(ValueError):
                record(db, self.wiki, [lote])
            self.assertEqual(json_curadoria.read_text(), "{}")
            self.assertFalse((self.wiki / "decisoes.tsv.gz").exists())
            record(db, self.wiki, [])
            self.assertEqual(self.abrir(chave)["estado"], "pendente")
            lote.write_text(json.dumps(decisao))
            record(db, self.wiki, [lote])
        self.assertEqual(self.abrir(chave)["estado"], "conferido")
        self.assertEqual(self.abrir("zulip-msg-2")["estado"], "pendente")
        self.write_page(self.pedido, "We are quoting an old discussion here.")
        with closing(connect(self.wiki)) as db, self.assertRaises(ValueError):
            record(db, self.wiki, [lote])

    def test_verified_attachment_without_automatic_label(self):
        pasta = self.wiki / "local/anexos"
        pasta.mkdir()
        chave = "zulip-anexo-revisado"
        nome = "proposta.png"
        texto = "Could we extend the deadline by a week?"
        (pasta / "extracao.json").write_text(json.dumps({chave: {"name": nome, "transcription": "parcial"}}))
        (pasta / (chave + ".md")).write_text(
            f"---\nlearning_uses: [dar-feedback]\n---\n# {nome}\n\n## Content\n\n```text\n{texto}\n```\n")
        assinatura = self.abrir(chave)["assinatura"]
        exemplo = {"trecho": texto, "funcao": "pedido", "usos": ["negociar-prazo"], "assinatura": assinatura}
        (self.wiki / "curadoria.json").write_text(json.dumps({chave: [exemplo]}))
        with gzip.open(self.wiki / "decisoes.tsv.gz", "wt") as out:
            out.write(f"{chave}\tanexo\t{assinatura}\tconferido\tpedido\n")
        for curation in (None, "conferido"):
            resultado, = self.buscar(kind="anexo", situation="negociar-prazo", curation=curation)
            self.assertEqual((resultado["id"], resultado["citar_id"], resultado["trecho"]), (chave, chave, texto))
            rotulo, = self.buscar(kind="anexo", text="pedido", curation=curation)
            self.assertEqual((rotulo["correspondencia"], rotulo["trecho"]), ("rotulo", texto))
        self.assertEqual(self.buscar(kind="anexo", text="dar-feedback", curation="conferido"), [])
        self.assertEqual(self.buscar(kind="anexo", text="dar-feedback")[0]["correspondencia"], "rotulo")

    def test_missing_transcript_with_multiple_sources(self):
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
