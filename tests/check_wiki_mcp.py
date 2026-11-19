import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins/english-flow/server.py"


class McpSession:
    def __init__(self, caderno, projeto=ROOT, servidor=SERVER):
        env = {**os.environ, "ENGLISH_FLOW_NOTEBOOK_DIR": str(caderno)}
        if projeto is None:
            env.pop("ENGLISH_FLOW_PROJECT_DIR", None)
        else:
            env["ENGLISH_FLOW_PROJECT_DIR"] = str(projeto)
        self.proc = subprocess.Popen([sys.executable, "-B", "-u", servidor], env=env, cwd=servidor.parent, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.seq = 0
        self.initialization = self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                "clientInfo": {"name": "conferencia", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def rpc(self, metodo, params):
        self.seq += 1
        self.send({"jsonrpc": "2.0", "id": self.seq, "method": metodo, "params": params})
        resposta = json.loads(self.proc.stdout.readline())
        if "error" in resposta:
            raise AssertionError((metodo, params, resposta["error"]))
        return resposta["result"]

    def chamar(self, nome, **args):
        resposta = self.rpc("tools/call", {"name": nome, "arguments": args})
        if resposta["isError"]:
            raise AssertionError((nome, args, resposta["structuredContent"]))
        return resposta["structuredContent"]

    def close_session(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=15)
        self.proc.stdout.close()


class OfflineWikiTests(unittest.TestCase):
    projeto = ROOT
    servidor = SERVER

    @classmethod
    def setUpClass(cls):
        cls.caderno = TemporaryDirectory()
        cls.addClassCleanup(cls.caderno.cleanup)
        cls.mcp = McpSession(cls.caderno.name, cls.projeto, cls.servidor)
        cls.addClassCleanup(cls.mcp.close_session)

    def buscar(self, **filtros):
        res = self.mcp.chamar("search_wiki", **filtros)
        print("search_wiki", filtros, [(r["id"], r["correspondencia"]) for r in res["matches"]], flush=True)
        return res["matches"]

    def abrir(self, chave, **args):
        return self.mcp.chamar("read_wiki_item", item_id=chave, **args)

    def test_plugin_name_language_and_panel(self):
        self.assertEqual(self.mcp.initialization["serverInfo"]["name"], "english-flow")
        instructions = self.mcp.initialization["instructions"]
        self.assertIn("Start each new learner conversation in English", instructions)
        self.assertIn("When the learner asks to switch", instructions)
        self.assertIn("examples, exercises, and role-play in English", instructions)
        resources = self.mcp.rpc("resources/list", {})["resources"]
        self.assertEqual([r["uri"] for r in resources], ["ui://english-flow/notebook.html"])
        panel = self.mcp.rpc("resources/read", {"uri": resources[0]["uri"]})["contents"][0]["text"]
        self.assertIn("<title>English Flow</title>", panel)
        self.assertNotIn("em português", panel.lower())
        self.assertNotIn("explain in portuguese", panel.lower())

    def test_unique_sources_notebook_and_original(self):
        casos = [
            ("Could you help me identify the right direction for my proposal?", "zulip-anexo-0d1d5afcd4c82604931d79ec8832512a"),
            ("The briefing's ready. I'll send it out after lunch.", "wiki/phrasal-verbs.md"),
        ]
        for texto, chave in casos:
            with self.subTest(chave=chave):
                geral = self.buscar(text=texto)
                self.assertEqual([r["id"] for r in geral], [chave], (texto, geral))
                filtrado = self.buscar(text=texto, curation="conferido")
                self.assertEqual([(r["id"], r["pagina_local"]) for r in filtrado], [(chave, geral[0]["pagina_local"])])
                item = self.abrir(chave)
                self.assertIn(texto, " ".join(item["texto"].split()))
                self.assertEqual(geral[0]["pagina_local"], item["pagina_local"])
                if self.projeto is None:
                    self.assertTrue(Path(item["pagina_local"]).is_file())
                if item["tipo"] == "anexo":
                    self.assertEqual(item["qualidade_transcricao"], "parcial")
                    self.assertEqual(self.buscar(text="fixing CSS specificity problems", curation="conferido"), [])
                    origem, = item["origens"]
                    self.assertEqual(origem["id"], "zulip-msg-2407782")
                    mensagem = self.abrir(origem["id"])
                    self.assertTrue(mensagem["texto"].strip())
                    self.assertIn(chave, [ref["id"] for ref in mensagem["anexos"]])
                else:
                    self.assertEqual(item["fonte"], "Projeto")
                registro = self.mcp.chamar("save_entry", kind="note", title=chave, content=texto, sources=[chave])
                self.assertEqual(Path(registro["path"]).parent, Path(self.caderno.name))
                entrada = self.mcp.chamar("read_entry", entry_id=registro["id"])
                ref, = entrada["source_refs"]
                reaberto = self.mcp.chamar(ref["tool"], item_id=ref["id"])
                self.assertEqual((reaberto["id"], reaberto["pagina_local"]), (chave, item["pagina_local"]))

    def test_reviewer_feedback(self):
        filtros = dict(source="Doist", curation="conferido", situation="dar-feedback")
        oferecido = self.buscar(**filtros, text="A small intro on Twist")
        self.assertEqual([r["citar_id"] for r in oferecido], ["doist-dar-feedback"])
        item = self.abrir(oferecido[0]["citar_id"])
        self.assertIn("would be helpful!", item["texto"])
        pedido = self.buscar(**filtros, text="Could you check out this Twist intro?")
        self.assertNotIn(item["id"], [r["citar_id"] for r in pedido])

    def test_deadline_requests(self):
        for pedido in ("Como peço mais tempo para entregar um relatório?",
                       "How can I ask for more time to finish a report?"):
            with self.subTest(pedido=pedido):
                filtros = dict(situation="negociar-prazo", function="pedido", curation="conferido")
                achados = self.buscar(**filtros)
                self.assertTrue(achados, (pedido, filtros))
                item = self.abrir(achados[0]["citar_id"])
                self.assertEqual(item["id"], "doist-combinar-prazo", (pedido, achados))
                self.assertIn("Can we do Thursday instead of Monday?", item["texto"])
                self.assertIn("End of your day Wed should work well", item["texto"])

    def test_rephrase_and_widen_one_filter(self):
        exigidos = dict(source="Doist", curation="conferido")
        opcionais = dict(situation="negociar-prazo", topic="phrasal-verbs")
        self.assertEqual(self.buscar(**exigidos, **opcionais, text="extend my report deadline"), [])
        self.assertEqual(self.buscar(**exigidos, **opcionais, text="instead of Monday"), [])
        achados = self.buscar(**exigidos, situation="negociar-prazo", text="instead of Monday")
        self.assertEqual([r["id"] for r in achados], ["doist-combinar-prazo"])
        self.assertIn("Can we do Thursday instead of Monday?", self.abrir(achados[0]["id"])["texto"])

    def test_gap_after_three_searches(self):
        exigidos = dict(source="Doist", curation="conferido")
        consultas = [
            dict(situation="comunicar-risco", topic="vocabulario", text="Kubernetes rollback deadline"),
            dict(situation="comunicar-risco", topic="vocabulario", text="roll back the Kubernetes deployment"),
            dict(situation="comunicar-risco", text="roll back the Kubernetes deployment"),
        ]
        for consulta in consultas:
            self.assertEqual(self.buscar(**exigidos, **consulta), [], consulta)

    def test_attachment_filename_and_context(self):
        exigidos = dict(kind="anexo", source="Zulip")
        arquivo = "Screen-Shot-2021-12-07-at-10.25.36-AM.png"
        achados = self.buscar(**exigidos, text=arquivo)
        self.assertEqual([(r["correspondencia"], r["id"]) for r in achados],
                         [("arquivo", "zulip-anexo-02df8e70f418d822abc204d2b65aa964")])
        anexo = self.abrir(achados[0]["id"])
        self.assertFalse(anexo["texto"])
        origem, = anexo["origens"]
        mensagem = self.abrir(origem["id"])
        self.assertEqual(origem["id"], "zulip-msg-1293440")
        trecho = "scheduling rather than sending"
        self.assertIn(trecho, mensagem["texto"])
        achados = self.buscar(**exigidos, text=trecho)
        self.assertEqual([r["citar_id"] for r in achados], [mensagem["id"]])
        self.assertEqual(achados[0]["correspondencia"], "contexto")
        geral = self.buscar(text=trecho)
        self.assertEqual([r["id"] for r in geral], [mensagem["id"]])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--plugin", type=Path, help="Check the installed plugin without a project wiki override.")
    opcoes, outros = parser.parse_known_args()
    if opcoes.plugin:
        OfflineWikiTests.servidor = opcoes.plugin.resolve() / "server.py"
        OfflineWikiTests.projeto = None
    unittest.main(argv=[sys.argv[0], *outros])
