import hashlib
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools.collection import download_attachments as anexos


URL = "https://chat.zulip.org/user_uploads/2/hash1/test.png"


class HttpResponse(BytesIO):
    def __init__(self, data, **headers):
        super().__init__(data)
        self.headers = HTTPMessage()
        for nome, valor in headers.items():
            self.headers[nome.replace("_", "-")] = valor
        self.status = 200


class AttachmentDownloadTests(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="test-anexos-"))).resolve()
        self.assertEqual(self.raiz.parent, Path(tempfile.gettempdir()).resolve())

    def test_redirects_only_to_allowed_route(self):
        hosts = {anexos.ZULIP_HOST}
        for location in (
            "http://chat.zulip.org/user_uploads/2/hash/test.png",
            "https://fora.example/a",
            "https://anon@chat.zulip.org/user_uploads/2/hash/test.png",
            "https://chat.zulip.org/user_uploads/%2e%2e/config",
        ):
            self.assertEqual(anexos.redirect_target(URL, location, hosts),
                             (None, "redirecionamento_bloqueado"))
        for location in ("/login/?next=/test", "/accounts/login/?next=/test"):
            self.assertEqual(anexos.redirect_target(URL, location, hosts), (None, "sem_acesso_anonimo"))
        self.assertEqual(anexos.redirect_target(URL, "/user_uploads/2/hash2/test.png", hosts),
                         ("https://chat.zulip.org/user_uploads/2/hash2/test.png", None))

    def test_verifies_attachment_and_removes_partial_file(self):
        chave = anexos.attachment_id(URL)
        resultado = anexos.write_file(HttpResponse(b"imagem", Content_Type="image/png", Content_Length="6"),
                                  self.raiz, chave, Event())
        self.assertEqual((resultado.estado, resultado.bytes), ("baixado", 6))
        self.assertEqual(resultado.sha256, hashlib.sha256(b"imagem").hexdigest())
        self.assertEqual((self.raiz / resultado.arquivo).read_bytes(), b"imagem")
        with self.assertRaises(anexos.RetryableDownload):
            anexos.write_file(HttpResponse(b"novo", Content_Type="image/png", Content_Length="99"), self.raiz, chave, Event())
        self.assertEqual((self.raiz / resultado.arquivo).read_bytes(), b"imagem")
        self.assertEqual(list(self.raiz.rglob("*.part")), [])
        html = HttpResponse(b"<form></form>", Content_Type="text/html")
        self.assertEqual(anexos.write_file(html, self.raiz, chave, Event()).estado, "resposta_ambigua")

    def test_temporary_http_error_sets_global_pause(self):
        class Opener:
            def open(self, pedido, timeout):
                headers = HTTPMessage()
                headers["Retry-After"] = "17"
                raise HTTPError(pedido.full_url, 429, "Rate limit", headers, BytesIO())

        with self.assertRaises(anexos.RetryableDownload) as error:
            anexos.attempt_download(Opener(), URL, self.raiz, anexos.attachment_id(URL),
                          anexos.RateLimiter(0.1, Event()), {anexos.ZULIP_HOST}, 1)
        self.assertTrue(error.exception.global_)
        self.assertEqual(error.exception.retry_after, "17")

    def test_failed_file_stays_in_queue(self):
        with patch.object(anexos, "attempt_download", side_effect=PermissionError(13, "arquivo em uso")):
            resultado = anexos.download(URL, anexos.attachment_id(URL), self.raiz,
                                       anexos.RateLimiter(0.1, Event()), {anexos.ZULIP_HOST}, 1, 3)
        self.assertEqual(resultado.estado, "pendente")
        self.assertIn("13", resultado.detalhe)

    def test_resume_preserves_references_and_valid_files(self):
        urls = [URL, URL + "-ausente", URL + "-novo"]
        referencias = {url: [{"id": 57}, {"id": 57}] for url in urls}
        cache = {urls[0]: {"status": "publico"}, urls[1]: {"status": "indisponivel"}}
        banco = sqlite3.connect(":memory:")
        self.addCleanup(banco.close)
        banco.executescript(anexos.SCHEMA)
        anexos.preparar(banco, referencias, cache)
        anexos.preparar(banco, referencias, cache)
        fila = anexos.candidatos(banco, referencias, cache, self.raiz, False)
        self.assertEqual([url for url, _ in fila], [urls[0], urls[2]])
        resultado = anexos.write_file(HttpResponse(b"imagem", Content_Type="image/png"),
                                  self.raiz, fila[0][1], Event())
        anexos.salvar(banco, urls[0], resultado)
        self.assertEqual(anexos.resumo(banco)["referencias"], 3)
        self.assertEqual([url for url, _ in anexos.candidatos(banco, referencias, cache, self.raiz, False)], [urls[2]])
        (self.raiz / resultado.arquivo).write_bytes(b"")
        self.assertEqual([url for url, _ in anexos.candidatos(banco, referencias, cache, self.raiz, False)],
                         [urls[2], urls[0]])
