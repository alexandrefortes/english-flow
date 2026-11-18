import hashlib
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wiki"))
import baixar_anexos as anexos


URL = "https://chat.zulip.org/user_uploads/2/hash1/test.png"


class Resposta(BytesIO):
    def __init__(self, data, **headers):
        super().__init__(data)
        self.headers = HTTPMessage()
        for nome, valor in headers.items():
            self.headers[nome.replace("_", "-")] = valor
        self.status = 200


class BaixarAnexosTests(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="test-anexos-"))).resolve()
        self.assertEqual(self.raiz.parent, Path(tempfile.gettempdir()).resolve())

    def test_redireciona_apenas_para_rota_permitida(self):
        hosts = {anexos.HOST_ZULIP}
        for location in (
            "http://chat.zulip.org/user_uploads/2/hash/test.png",
            "https://fora.example/a",
            "https://anon@chat.zulip.org/user_uploads/2/hash/test.png",
            "https://chat.zulip.org/user_uploads/%2e%2e/config",
        ):
            self.assertEqual(anexos.destino_redirecionado(URL, location, hosts),
                             (None, "redirecionamento_bloqueado"))
        for location in ("/login/?next=/test", "/accounts/login/?next=/test"):
            self.assertEqual(anexos.destino_redirecionado(URL, location, hosts), (None, "sem_acesso_anonimo"))
        self.assertEqual(anexos.destino_redirecionado(URL, "/user_uploads/2/hash2/test.png", hosts),
                         ("https://chat.zulip.org/user_uploads/2/hash2/test.png", None))

    def test_confirmacao_de_anexo_e_retirada_de_arquivo_parcial(self):
        chave = anexos.id_anexo(URL)
        resultado = anexos.gravar(Resposta(b"imagem", Content_Type="image/png", Content_Length="6"),
                                  self.raiz, chave, Event())
        self.assertEqual((resultado.estado, resultado.bytes), ("baixado", 6))
        self.assertEqual(resultado.sha256, hashlib.sha256(b"imagem").hexdigest())
        self.assertEqual((self.raiz / resultado.arquivo).read_bytes(), b"imagem")
        with self.assertRaises(anexos.Transitorio):
            anexos.gravar(Resposta(b"novo", Content_Type="image/png", Content_Length="99"), self.raiz, chave, Event())
        self.assertEqual((self.raiz / resultado.arquivo).read_bytes(), b"imagem")
        self.assertEqual(list(self.raiz.rglob("*.part")), [])
        html = Resposta(b"<form></form>", Content_Type="text/html")
        self.assertEqual(anexos.gravar(html, self.raiz, chave, Event()).estado, "resposta_ambigua")

    def test_http_temporario_pede_pausa_global(self):
        class Opener:
            def open(self, pedido, timeout):
                headers = HTTPMessage()
                headers["Retry-After"] = "17"
                raise HTTPError(pedido.full_url, 429, "Rate limit", headers, BytesIO())

        with self.assertRaises(anexos.Transitorio) as error:
            anexos.tentar(Opener(), URL, self.raiz, anexos.id_anexo(URL),
                          anexos.Limitador(0.1, Event()), {anexos.HOST_ZULIP}, 1)
        self.assertTrue(error.exception.global_)
        self.assertEqual(error.exception.retry_after, "17")

    def test_falha_local_de_um_arquivo_permanece_na_fila(self):
        with patch.object(anexos, "tentar", side_effect=PermissionError(13, "arquivo em uso")):
            resultado = anexos.baixar(URL, anexos.id_anexo(URL), self.raiz,
                                       anexos.Limitador(0.1, Event()), {anexos.HOST_ZULIP}, 1, 3)
        self.assertEqual(resultado.estado, "pendente")
        self.assertIn("13", resultado.detalhe)

    def test_retomada_preserva_referencias_e_arquivos_validos(self):
        urls = [URL, URL + "-ausente", URL + "-novo"]
        referencias = {url: [{"id": 57}, {"id": 57}] for url in urls}
        cache = {urls[0]: {"status": "publico"}, urls[1]: {"status": "indisponivel"}}
        banco = sqlite3.connect(":memory:")
        self.addCleanup(banco.close)
        banco.executescript(anexos.ESQUEMA)
        anexos.preparar(banco, referencias, cache)
        anexos.preparar(banco, referencias, cache)
        fila = anexos.candidatos(banco, referencias, cache, self.raiz, False)
        self.assertEqual([url for url, _ in fila], [urls[0], urls[2]])
        resultado = anexos.gravar(Resposta(b"imagem", Content_Type="image/png"),
                                  self.raiz, fila[0][1], Event())
        anexos.salvar(banco, urls[0], resultado)
        self.assertEqual(anexos.resumo(banco)["referencias"], 3)
        self.assertEqual([url for url, _ in anexos.candidatos(banco, referencias, cache, self.raiz, False)], [urls[2]])
        (self.raiz / resultado.arquivo).write_bytes(b"")
        self.assertEqual([url for url, _ in anexos.candidatos(banco, referencias, cache, self.raiz, False)],
                         [urls[2], urls[0]])
