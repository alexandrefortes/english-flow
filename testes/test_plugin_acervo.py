import base64
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "ingles-para-o-trabalho"
sys.path.insert(0, str(PLUGIN))
import acervo_local as acervo
import server


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jYbQAAAAASUVORK5CYII="
)
SAMPLE = "zulip-combinar-proximos-passos"
MESSAGE = "zulip-msg-2499678"


class PluginAcervoTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.data = self.root / "dados"
        self.data.mkdir()
        self.notebook = self.root / "notes"
        self.enterContext(patch.object(server, "DATA", self.data))
        self.enterContext(patch.object(server, "NOTEBOOK", self.notebook))
        self.enterContext(patch.object(server, "WIKI", self.root / "wiki"))

    def test_graph_without_raw_collection_search_read_and_save(self):
        wiki = server.WIKI
        local = wiki / "local"
        topic = "zulip-topico-" + "a" * 24
        page = local / "zulip/canal-6" / (topic + ".md")
        page.parent.mkdir(parents=True)
        page.write_text("# Decisions", encoding="utf-8")
        url = "https://chat.zulip.org/#narrow/channel/6/topic/Decisions"
        with sqlite3.connect(local / "grafo.sqlite3") as db:
            db.executescript("""
                CREATE TABLE nos (id TEXT PRIMARY KEY,tipo,titulo,fonte,origem,url,caminho,texto,estado,ordem);
                CREATE TABLE ligacoes (origem,destino,relacao,trecho);
            """)
            db.executemany("INSERT INTO nos (id,tipo,titulo,fonte,url,texto,ordem) VALUES (?,?,?,?,?,?,?)", [
                (f"zulip-msg-{i}", "mensagem", "Decisions", "Zulip", f"{url}/near/{i}", "By Thursday.", i)
                for i in (11, 12)
            ] + [(topic, "conversa", "Decisions", "Zulip", url, None, None),
                 ("negociar-prazo", "situacao", "Negociar prazo", None, None, None, None),
                 ("gramatica", "tema", "Gramática", None, None, None, None)])
            for i in (11, 12):
                db.executemany("INSERT INTO ligacoes VALUES (?,?,?,?)", [
                    (f"zulip-msg-{i}", topic, "pertence", None),
                    (f"zulip-msg-{i}", "negociar-prazo", "curado", None),
                    (f"zulip-msg-{i}", "gramatica", "curado" if i == 11 else "candidato", None)])
        db.close()
        def call(name, **arguments):
            response = server.dispatch("tools/call", {"name": name, "arguments": arguments})
            self.assertFalse(response["isError"], response["structuredContent"])
            return response["structuredContent"]

        filters = dict(situation="negociar-prazo", topic="gramatica", source="Zulip", text="thurs")
        first = call("search_graph", **filters, limit=1)
        second = call("search_graph", **filters, limit=1, offset=first["next_offset"])
        self.assertIsNone(second["next_offset"])
        self.assertNotEqual(first["matches"][0]["id"], second["matches"][0]["id"])
        item, = call("search_graph", **filters, curated_only=True)["matches"]
        self.assertEqual(item["id"], "zulip-msg-11")
        self.assertEqual(item["pagina_local"], page.as_posix() + "#zulip-msg-11")
        self.assertEqual(call("search_graph", source="Doist")["matches"], [])
        detail = call("read_graph_node", node_id=item["id"])
        self.assertEqual(detail["no"]["texto"], "By Thursday.")
        self.assertIn(topic, [link["id"] for link in detail["ligacoes"]])
        self.assertEqual(call("read_graph_node", node_id=topic)["pagina_local"], page.as_posix())
        saved = call("save_entry", kind="lesson", title="Deadline", content="By Thursday.", sources=[item["id"]])
        self.assertEqual(call("read_entry", entry_id=saved["id"])["source_refs"][0]["url"], item["url"])

        # Once the wiki index is available, legacy tools also follow the edited Markdown.
        self.assertEqual(call("read_wiki_item", item_id=topic)["titulo"], "Decisions")
        page.write_text("# After review\n\n## zulip-msg-11\n\nSam\n\n```text\nBy Friday.\n```\n", encoding="utf-8")
        edited, = call("search_graph", text="By Friday.")["matches"]
        self.assertEqual((edited["id"], edited["titulo"]), ("zulip-msg-11", "After review"))
        page.unlink()
        self.assertEqual(call("search_graph", text="By Friday.")["matches"], [])

    def test_graph_errors_and_portable_reader(self):
        tools = {tool["name"]: tool for tool in server.dispatch("tools/list", {})["tools"]}
        for name in ("search_graph", "read_graph_node"):
            self.assertTrue(tools[name]["annotations"]["readOnlyHint"])
        for arguments in ({"limit": True}, {"limit": 0}, {"offset": -1}, {"curated_only": "yes"},
                          {"situation": "unknown"}, {"text": "  "}):
            response = server.call_tool({"name": "search_graph", "arguments": arguments})
            self.assertTrue(response["isError"])
            self.assertNotIn("Grafo ausente", response["structuredContent"]["error"])
        missing = server.call_tool({"name": "search_graph"})
        self.assertIn("Grafo ausente", missing["structuredContent"]["error"])
        self.assertFalse(server.WIKI.exists())
        # The wiki and the installed plugin each work when copied on their own.
        self.assertEqual((PLUGIN / "consulta_grafo.py").read_text(encoding="utf-8"),
                         (PLUGIN.parents[1] / "wiki/consulta_grafo.py").read_text(encoding="utf-8"))

    def write_sample(self):
        sample = self.data / f"{SAMPLE}.json"
        sample.write_text(json.dumps({"mensagens": [
            {"id": 2499678, "texto": "I'll reopen the discussion.", "autor": "Example"},
            {"id": 12, "texto": "Unrelated payload"},
        ]}), encoding="utf-8")
        return sample

    def test_sample_search_and_stable_message_reference(self):
        sample = self.write_sample()
        search = server.search_zulip("REOPEN")
        match, = search["matches"]
        self.assertEqual(match["id"], MESSAGE)
        self.assertEqual(match["scope"], "sample")
        self.assertTrue(match["url"].endswith("/near/2499678"))
        self.assertEqual(server.read_source(MESSAGE)["structuredContent"], match)
        self.assertTrue(search["coverage"]["zulip"]["searchable"])
        self.assertFalse(next(item for item in server.list_sources()["sources"] if item["id"] == SAMPLE)["complete"])
        saved = server.save_entry("lesson", "Next steps", "Example", [MESSAGE])
        sample.unlink()
        entry = server.read_entry(saved["id"])
        self.assertEqual(entry["sources"], [MESSAGE])
        self.assertEqual(entry["source_refs"], [{"id": MESSAGE, "title": match["topic"], "url": match["url"]}])

    def test_sqlite_search_prefers_larger_archive_and_retains_working_samples(self):
        self.write_sample()
        pilot = self.data / "zulip-piloto"
        pilot.mkdir()
        with sqlite3.connect(pilot / "coleta.sqlite3") as database:
            database.execute("CREATE TABLE mensagens (id, channel, topic, content, url)")
            database.execute("INSERT INTO mensagens VALUES (?, ?, ?, ?, ?)",
                             (2499678, "API", "Decisions", "Reopen the discussion.", "https://zulip.example/2499678"))
        database.close()
        full = self.data / "zulip"
        full.mkdir()
        (full / "coleta.sqlite3").write_bytes(b"damaged")
        result = server.search_zulip("reopen")
        self.assertEqual([(row["id"], row["scope"]) for row in result["matches"]], [(MESSAGE, "pilot")])
        self.assertEqual(result["coverage"]["zulip"]["full"]["error"], "base_unreadable")

    def test_doist_aliases_and_download_repairs_are_independent(self):
        canonical = "doist-pedir-atualizacao"
        alias = "pedido-atualizacao-newsletter"
        captures = self.data / "doist" / "capturas"
        captures.mkdir(parents=True)
        (captures / f"{alias}.png").write_bytes(PNG)
        listing = server.list_sources()["sources"]
        item = next(row for row in listing if row["id"] == canonical)
        self.assertTrue(item["available"])
        self.assertEqual(item["aliases"], [alias])
        self.assertNotIn(alias, [row["id"] for row in listing])
        self.assertEqual(server.read_source(alias)["structuredContent"]["aliases"], [canonical])
        bad = self.data / "doist-dar-feedback.png"
        bad.write_bytes(PNG[:-12])
        self.assertFalse(acervo.get_doist(self.data, "doist-dar-feedback")[0]["available"])
        with patch.object(server, "baixar", side_effect=[PNG, OSError("offline")]) as image_download:
            with patch.object(server, "baixar_mensagens", side_effect=OSError("offline")):
                result = server.download_sources()
        self.assertEqual(image_download.call_count, 2)
        self.assertEqual(result["downloaded"], ["doist-dar-feedback"])
        self.assertEqual(bad.read_bytes(), PNG)
        self.assertEqual(len(result["failures"]), 3)

    def test_existing_markdown_with_general_front_matter_is_listed(self):
        self.notebook.mkdir()
        (self.notebook / "legacy.md").write_text("# Old lesson\n\nBody.", encoding="utf-8")
        (self.notebook / "plain-note.md").write_text(
            "---\ntitle: Meeting notes\ntags: [work, review]\ncreated_at: 2026-11-17\n---\n\nMy notes.",
            encoding="utf-8",
        )
        listing = server.open_notebook()
        self.assertEqual(listing["skipped"], [])
        self.assertEqual([(row["title"], row["kind"]) for row in listing["entries"]],
                         [("Old lesson", "lesson"), ("Meeting notes", "note")])
        self.assertEqual(server.read_entry("plain-note.md")["content"], "My notes.")


if __name__ == "__main__":
    unittest.main()
