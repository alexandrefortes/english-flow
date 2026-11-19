import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tools.curation import run_image_review as terra
from tools.curation import build_attachments
from tools.curation import review_images


class ImageReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.dados = self.root / 'dados'
        self.anexos = self.dados / 'zulip' / 'anexos'
        self.anexos.mkdir(parents=True)
        self.pasta = self.dados / 'revisao-ocr'
        self.pasta.mkdir()

    def imagem(self, nome, cor):
        caminho = self.root / (nome + '.png')
        Image.new('RGB', (3, 3), cor).save(caminho)
        return {'id': 'zulip-anexo-' + nome * 32, 'caminho': str(caminho),
                'sha256': hashlib.sha256(caminho.read_bytes()).hexdigest(),
                'mime': 'image/png', 'metodo': 'tesseract-imagem',
                'texto': 'OCR bruto', 'estado': 'extraido', 'detalhe': ''}

    def test_image_indices_unique_pixels_and_partial_transcript(self):
        a, b, duplicado = self.imagem('a', 'red'), self.imagem('b', 'blue'), self.imagem('c', 'red')
        chamadas = []

        def fake_cli(args, **kwargs):
            caminhos = [Path(args[i + 1]) for i, arg in enumerate(args) if arg == '-i']
            chamadas.append(caminhos)
            self.assertEqual(len(caminhos), 2)
            with Image.open(caminhos[0]) as img:
                self.assertEqual(img.convert('RGB').getpixel((0, 0)), (255, 0, 0))
            with Image.open(caminhos[1]) as img:
                self.assertEqual(img.convert('RGB').getpixel((0, 0)), (0, 0, 255))
            resposta = {'itens': [
                {'indice': 1, 'estado': 'extraido', 'texto': 'primeiro', 'detalhe': ''},
                {'indice': 2, 'estado': 'parcial', 'texto': 'segundo', 'detalhe': 'linha cortada'},
            ]}
            Path(args[args.index('-o') + 1]).write_text(json.dumps(resposta), encoding='utf-8')
            return subprocess.CompletedProcess(args, 0, '', '')

        with patch.object(terra.subprocess, 'run', side_effect=fake_cli):
            terra.review_batch(Path('codex-fake'), [a, b, duplicado], self.dados, self.root / 'tmp')
        self.assertEqual(len(chamadas), 1)
        resultados = [json.loads((self.pasta / 'terra' / (i['id'] + '.json')).read_text(encoding='utf-8'))
                      for i in (a, b, duplicado)]
        self.assertEqual([(r['id'], r['texto'], r['estado']) for r in resultados], [
            (a['id'], 'primeiro', 'extraido'), (b['id'], 'segundo', 'parcial'),
            (duplicado['id'], 'primeiro', 'extraido')])
        self.assertIn('linha cortada', resultados[1]['detalhe'])

    def test_rerun_uses_checksum_and_preserves_raw_ocr(self):
        item = self.imagem('a', 'red')
        recibo = {'id': item['id'], 'sha256': item['sha256'], 'estado': 'parcial',
                   'texto': 'revisado', 'metodo': 'revisao-visual-terra',
                   'detalhe': 'cortado', 'manual': True}
        pasta_terra = self.pasta / 'terra'
        pasta_terra.mkdir()
        (pasta_terra / (item['id'] + '.json')).write_text(json.dumps(recibo), encoding='utf-8')
        banco = self.anexos / 'transcricoes.sqlite3'
        with closing(sqlite3.connect(banco)) as db, db:
            db.execute('CREATE TABLE transcricoes (id TEXT, sha256 TEXT, estado TEXT, texto TEXT, metodo TEXT, detalhe TEXT)')
            db.execute('INSERT INTO transcricoes VALUES (?,?,?,?,?,?)',
                       (item['id'], item['sha256'], 'extraido', 'OCR bruto', 'tesseract-imagem', ''))
        caminho_fila = self.root / 'fila.sqlite3'
        with closing(sqlite3.connect(caminho_fila)) as fila:
            review_images.preparar(fila, {item['id']: item}, self.pasta)
        with closing(sqlite3.connect(caminho_fila)) as fila:
            review_images.preparar(fila, {item['id']: item}, self.pasta)
            self.assertEqual(fila.execute('SELECT estado FROM fila').fetchone()[0], 'revisado')
            revisoes = build_attachments.read_manual_reviews(self.anexos)
            self.assertEqual(revisoes[item['id'], item['sha256']][0][:2], ('parcial', 'revisado'))
            self.assertEqual(build_attachments.read_transcripts(self.anexos)[item['id'], item['sha256']][1], 'OCR bruto')
        with closing(sqlite3.connect(caminho_fila)) as fila:
            novo = dict(item, sha256='0' * 64)
            review_images.preparar(fila, {item['id']: novo}, self.pasta)
            self.assertEqual(fila.execute('SELECT estado FROM fila').fetchone()[0], 'pendente')
            self.assertNotIn((item['id'], novo['sha256']), revisoes)


if __name__ == '__main__':
    unittest.main()
