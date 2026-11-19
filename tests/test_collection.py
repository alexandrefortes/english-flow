from base64 import b64decode
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch

from tools.collection import collect_sources
from tools.collection import download_doist
from tools.collection import download_zulip
from tools.collection import list_attachments
from tools.collection import read_zulip


PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWPQAAAAASUVORK5CYII=")
UPLOAD = "/user_uploads/42/synthetic-upload/example.txt"


def pagina(ancora, ids, inicio=False):
    return {
        "anchor": ancora,
        "found_newest": ancora == "newest",
        "found_oldest": inicio,
        "found_anchor": False,
        "history_limited": False,
        "messages": [
            {
                "id": id_mensagem,
                "stream_id": 42,
                "type": "stream",
                "display_recipient": "Synthetic channel",
                "subject": "Planning & notes",
                "content": f"Can you send an update? [Draft]({UPLOAD}) <script>",
                "content_type": "text/x-markdown",
                "sender_id": 1,
                "sender_full_name": "Taylor Example",
                "timestamp": 1700000000 + id_mensagem,
            }
            for id_mensagem in ids
        ],
    }


class CollectionTests(unittest.TestCase):
    def test_collect_runs_independent_steps(self):
        etapas = [call("tools.collection.download_doist"), call("tools.collection.download_zulip"), call("tools.collection.list_attachments")]
        for codigos, resultado, chamadas in [
            ([0, 0, 0], 0, etapas),
            ([1, 0, 0], 1, etapas),
            ([0, 1], 1, etapas[:2]),
            ([0, 3, 0], 3, etapas),
        ]:
            with self.subTest(codigos=codigos), patch.object(collect_sources, "run", side_effect=codigos) as rodar:
                self.assertEqual(collect_sources.main([]), resultado)
                self.assertEqual(rodar.call_args_list, chamadas)

    def test_doist_creates_directory_and_reuses_image(self):
        with TemporaryDirectory() as temp:
            raiz = Path(temp)
            pasta = raiz / "dados" / "doist"
            fonte = raiz / "catalogo.json"
            url = "https://example.invalid/article"
            imagem = "https://example.invalid/capture"
            inventario = {
                "escopo": "Fixture sintética",
                "cobertura": "Uma captura",
                "publicacoes": [{"url": url, "titulo": "Example", "estado": "examinada"}],
                "itens": [{"id": "exemplo", "titulo": "Update", "publicacao": url, "url_secao": url,
                           "secao": "Updates", "url_original": imagem, "equipe": "Example team",
                           "evidencia": "Dados sintéticos", "estado": "elegível"}],
            }
            fonte.write_text(json.dumps(inventario, ensure_ascii=False), encoding="utf-8")
            with (patch.object(download_doist, "DIRECTORY", pasta), patch.object(download_doist, "INVENTORY", fonte),
                  patch.object(download_doist, "download_with_retry", return_value=PNG) as obter):
                self.assertEqual(download_doist.main(["--limit", "1"]), 0)
                self.assertEqual(download_doist.main([]), 0)
                obter.assert_called_once_with(imagem)
            registro = json.loads((pasta / "coleta.json").read_text(encoding="utf-8"))["exemplo"]
            self.assertEqual((pasta / registro["arquivo"]).read_bytes(), PNG)
            self.assertEqual(registro["sha256"], hashlib.sha256(PNG).hexdigest())
            self.assertIn(registro["arquivo"], (pasta / "index.html").read_text(encoding="utf-8"))

    def test_zulip_resumes_exports_and_checks_inventory(self):
        canais = {"channels": [
            {"stream_id": 42, "name": "Synthetic channel", "is_archived": False, "first_message_id": 11},
            {"stream_id": 43, "name": "Empty channel", "is_archived": True, "first_message_id": None},
        ]}
        respostas = [pagina("newest", [17, 20]), pagina(17, [11, 15], inicio=True)]
        with TemporaryDirectory() as temp:
            pasta = Path(temp)
            with (patch.object(download_zulip, "channel_inventory", return_value=canais),
                  patch.object(download_zulip, "oldest_probe", return_value={"id": 11, "history_limited": False}),
                  patch.object(download_zulip, "fetch_page", side_effect=respostas) as obter,
                  patch.object(download_zulip.time, "sleep")):
                piloto = download_zulip.collect(pasta, max_paginas=1)
                self.assertFalse(piloto["found_oldest"])
                self.assertFalse((pasta / "mensagens.jsonl").exists())
                coleta = download_zulip.collect(pasta)
                self.assertTrue(coleta["coverage_verified"], coleta["issues"])
                self.assertTrue(coleta["page_chain_verified"])
                self.assertEqual(coleta["cutoff_id"], 20)
                self.assertEqual(download_zulip.collect(pasta)["jsonl_sha256"], coleta["jsonl_sha256"])
                self.assertEqual(obter.call_args_list, [call("newest", 500), call(17, 1000)])

            mensagens = (pasta / "mensagens.jsonl").read_bytes()
            self.assertEqual(hashlib.sha256(mensagens).hexdigest(), coleta["jsonl_sha256"])
            self.assertEqual([json.loads(linha)["id"] for linha in mensagens.splitlines()], [20, 17, 15, 11])
            channel_list = json.loads((pasta / "canais.json").read_text(encoding="utf-8"))
            self.assertEqual([canal["count"] for canal in channel_list], [4, 0])

            with patch.object(list_attachments, "verify", return_value={"status": "publico"}) as sondar:
                anexos = list_attachments.build_inventory(pasta)
                self.assertEqual(anexos["pendencias"], 0)
                self.assertEqual(anexos["referencias"], 4)
                self.assertEqual(anexos["origem_sha256"], coleta["jsonl_sha256"])
                list_attachments.build_inventory(pasta)
                self.assertEqual(sondar.call_count, 1)

            with closing(sqlite3.connect(pasta / "coleta.sqlite3")) as banco:
                _, _, indice = read_zulip.indice(banco, pasta)
                self.assertIn("Empty channel", indice)
                _, _, topico = read_zulip.channel_page(banco, pasta, 42, {"topico": ["Planning & notes"]})
                self.assertIn("&lt;script&gt;", topico)
                self.assertIn("#11 on Zulip", topico)


if __name__ == "__main__":
    unittest.main()
