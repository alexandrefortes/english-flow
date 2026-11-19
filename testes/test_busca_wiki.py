from contextlib import closing
import gzip
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "plugins/ingles-para-o-trabalho"
sys.path.insert(0, str(PLUGIN))
from busca_wiki import abrir, buscar, consultar
from indice_wiki import conectar
sys.path.insert(0, str(PLUGIN.parents[1] / "wiki"))
from avaliar_acervo import registrar
from ingerir_acervo import texto_original


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
            texto += f"## zulip-msg-{n}\n\nSam\n\n" + texto_original(turno)
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

    def test_respostas_com_citacoes_traduzidas_e_aninhadas(self):
        interna = self.resposta.replace("[said]", "[发言道]").replace("):", ")：")
        replica = ("Jo [disse](https://chat.zulip.org/#narrow/channel/2/topic/Review/near/2):\n"
                   "````quote\n" + interna + "\n````\n\nThanks.")
        self.escrever(self.pedido, interna, replica)
        original, = self.buscar(text=self.pedido)
        self.assertEqual(original["id"], "zulip-msg-1")
        resposta, = self.buscar(text="Friday works.")
        self.assertEqual(resposta["id"], "zulip-msg-2")

    def test_busca_preserva_o_trecho_original_em_linhas_diferentes(self):
        texto = "Could we  move\n\nthe deadline?"
        self.escrever(texto)
        item, = self.buscar(text=self.pedido)
        self.assertEqual((item["id"], item["trecho"]), ("zulip-msg-1", texto))

    def test_paginacao_de_catalogo_em_caracteres(self):
        texto = json.dumps(["ação " * 14000, "último"], ensure_ascii=False)
        (self.wiki / "catalogo.json").write_text(texto, encoding="utf-8-sig")
        for offset in (0, 65535, 65536, len(texto) - 3, len(texto), len(texto) + 10):
            with self.subTest(offset=offset):
                item = consultar(self.wiki, abrir, chave="wiki/catalogo.json", offset=offset, limit=3)
                self.assertEqual(item["texto"], texto[offset:offset + 3])
                self.assertEqual(item["next_offset"], offset + 3 if offset + 3 < len(texto) else None)

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

    def test_lote_de_revisao_preserva_pendencias_e_rejeita_trecho_divergente(self):
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
        with closing(conectar(self.wiki)) as db:
            with self.assertRaises(ValueError):
                registrar(db, self.wiki, [lote])
            self.assertEqual(json_curadoria.read_text(), "{}")
            self.assertFalse((self.wiki / "decisoes.tsv.gz").exists())
            registrar(db, self.wiki, [])
            self.assertEqual(self.abrir(chave)["estado"], "pendente")
            lote.write_text(json.dumps(decisao))
            registrar(db, self.wiki, [lote])
        self.assertEqual(self.abrir(chave)["estado"], "conferido")
        self.assertEqual(self.abrir("zulip-msg-2")["estado"], "pendente")
        self.escrever(self.pedido, "We are quoting an old discussion here.")
        with closing(conectar(self.wiki)) as db, self.assertRaises(ValueError):
            registrar(db, self.wiki, [lote])

    def test_anexo_sem_rotulo_automatico_com_uso_conferido(self):
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
