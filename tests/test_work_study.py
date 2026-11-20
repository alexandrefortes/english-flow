import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools import PLUGIN
from tools.packaging import pack_work
import server
import work_study


class WorkStudyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.cache = self.root / "cache"
        self.release = self.root / "corpus.json"
        self.output = self.root / "drafts"

    def test_build_and_run_the_work_package_without_a_local_plugin(self):
        package = self.root / "work.zip"
        pack_work.pack(package)
        first = package.read_bytes()
        pack_work.pack(package)
        self.assertEqual(package.read_bytes(), first)
        with ZipFile(package) as archive:
            self.assertIsNone(archive.testzip())
            files = archive.namelist()
            manifest = json.loads(archive.read("plugin.json"))
            local = json.loads((PLUGIN / "plugin.json").read_bytes())
            self.assertEqual((manifest["name"], manifest["version"]), (local["name"], local["version"]))
            extension = manifest["extensions"]["com.openai"]
            apps = json.loads(archive.read(extension["apps"].removeprefix("./")))["apps"]
            self.assertEqual(apps, {"google-drive": {"id": pack_work.DRIVE_APP, "required": False}})
            self.assertNotIn("apps", local["extensions"]["com.openai"])
            self.assertTrue((PLUGIN / ".mcp.json").is_file())
            self.assertFalse({"mcp.json", ".mcp.json", ".codex-plugin/plugin.json", "server.py"} & set(files))
            self.assertFalse(any(name.endswith((".bin", ".tar.gz")) for name in files))
            skills = [name for name in files if name.endswith("/SKILL.md")]
            self.assertEqual(len(skills), 3)
            for name in skills:
                self.assertEqual(archive.read(name), (PLUGIN / name).read_bytes())
                self.assertIn(b"select the study environment", archive.read(name).lower())
            review = "skills/notebook-review/"
            self.assertIn(review + "references/work.md", files)
            scripts = review + "scripts/"
            lock = json.loads(archive.read(scripts + "corpus.json"))
            self.assertIn("/" + pack_work.CORPUS_REVISION + "/", lock["base_url"])
            self.assertEqual(lock["manifest"], json.loads((PLUGIN / "corpus/manifest.json").read_bytes()))
            self.assertEqual(lock["project_bytes"], (PLUGIN / "corpus/project.tar.gz").stat().st_size)
            archive.extractall(self.root / "install")
        program = self.root / "install" / scripts / "work_study.py"
        probe = subprocess.run([sys.executable, "-E", "-S", "-B", str(program), "study_environment"],
                               cwd=self.root, input="{}", capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(probe.stdout),
                         {"plugin": "english-flow", "execution": "work-cloud", "notebook": "google-drive"})
        args = {"kind": "note", "title": "An offline draft", "content": "Let's review this."}
        result = subprocess.run([sys.executable, "-E", "-S", "-B", str(program),
                                 "prepare_entry", "--cache", str(self.cache),
                                 "--output-dir", str(self.output)], cwd=self.root, input=json.dumps(args),
                                capture_output=True, text=True, check=True)
        draft = json.loads(result.stdout)
        self.assertEqual(draft["status"], "prepared")
        self.assertTrue(Path(draft["path"]).is_file())
        self.assertFalse(self.cache.exists())

    def test_archive_part_integrity_cache_and_retry(self):
        content = b"published source"
        digest = hashlib.sha256(content).hexdigest()
        target = self.root / "wiki-001.bin"
        for data in (content[:-1], content + b"!", content.upper()):
            with self.subTest(data=data), patch.object(work_study, "urlopen", return_value=BytesIO(data)):
                with self.assertRaises(ValueError):
                    work_study.download_part("https://example.invalid/", target, len(content), digest)
                self.assertEqual(list(self.root.iterdir()), [])
        with patch.object(work_study, "urlopen", return_value=BytesIO(content)) as fetch:
            work_study.download_part("https://example.invalid/", target, len(content), digest)
            work_study.download_part("https://example.invalid/", target, len(content), digest)
            fetch.assert_called_once()
        self.assertEqual(target.read_bytes(), content)

    def test_same_source_and_entry_on_both_computers(self):
        wiki = self.root / "wiki"
        (wiki / "local").mkdir(parents=True)
        quote = "Can we move the deadline to Friday?"
        (wiki / "example.md").write_text("# Request\n\n" + quote, encoding="utf-8")
        self.enterContext(patch.object(work_study, "work_wiki", return_value=wiki))
        self.enterContext(patch.object(server, "WIKI", wiki))
        self.enterContext(patch.object(server, "NOTEBOOK", self.root / "local-notebook"))
        filters = {"text": quote, "source": "Projeto", "kind": "didatica"}
        match, = work_study.run("search_wiki", filters, self.cache, self.release)["matches"]
        local, = server.search_wiki(**filters)["matches"]
        self.assertEqual((match["id"], match["trecho"]), (local["id"], local["trecho"]))
        self.assertEqual(match["pagina_local"], "wiki/example.md")
        item = work_study.run("read_wiki_item", {"item_id": match["id"]}, self.cache, self.release)
        self.assertIn(quote, item["texto"])
        self.assertEqual(item["pagina_local"], match["pagina_local"])
        args = {"kind": "note", "title": 'Revisão “Friday” 🗓\u2028deadline',
                "content": "## Request\r\n\r\n" + quote, "sources": [match["id"], match["id"]]}
        draft = work_study.run("prepare_entry", args, self.cache, self.release, self.output)
        saved = server.save_entry(**args)
        self.assertEqual(draft["id"], saved["id"])
        self.assertEqual(server.save_entry(**args), saved)
        self.assertEqual(server.read_entry(saved["id"])["title"], args["title"])
        path = Path(draft["path"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), draft["sha256"])
        self.assertNotIn(str(wiki), path.read_text(encoding="utf-8"))
        with patch.object(server, "NOTEBOOK", path.parent):
            cloud_note = server.read_entry(draft["id"])
        self.assertEqual(cloud_note["content"], args["content"].replace("\r\n", "\n"))
        self.assertEqual(cloud_note["sources"], [match["id"]])
        self.assertEqual(cloud_note["source_refs"][0]["id"], match["id"])

    def test_unknown_source_and_invalid_query_do_not_create_a_note(self):
        wiki = self.root / "wiki"
        (wiki / "local").mkdir(parents=True)
        with patch.object(work_study, "work_wiki", return_value=wiki):
            args = {"kind": "lesson", "title": "Missing", "content": "Try again.", "sources": ["missing"]}
            with self.assertRaisesRegex(ValueError, "Wiki item not found: missing"):
                work_study.run("prepare_entry", args, self.cache, self.release, self.output)
        with patch.object(work_study, "work_wiki", side_effect=AssertionError("unexpected download")):
            with self.assertRaises(ValueError):
                work_study.run("search_wiki", {"curation": "invalid"}, self.cache, self.release)
        self.assertFalse(self.output.exists())
