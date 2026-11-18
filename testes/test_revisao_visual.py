import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'wiki'))
import executar_terra_ocr as terra
import ingerir_anexos
import revisar_ocr


class RevisaoVisualTests(unittest.TestCase):
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

    def test_associa_indices_deduplica_pixels_e_preserva_parcial(self):
        a, b, duplicado = self.imagem('a', 'red'), self.imagem('b', 'blue'), self.imagem('c', 'red')
        chamadas = []

        def cli_fake(args, **kwargs):
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

        with patch.object(terra.subprocess, 'run', side_effect=cli_fake):
            terra.revisar_lote(Path('codex-fake'), [a, b, duplicado], self.dados, self.root / 'tmp')
        self.assertEqual(len(chamadas), 1)
        resultados = [json.loads((self.pasta / 'terra' / (i['id'] + '.json')).read_text(encoding='utf-8'))
                      for i in (a, b, duplicado)]
        self.assertEqual([(r['id'], r['texto'], r['estado']) for r in resultados], [
            (a['id'], 'primeiro', 'extraido'), (b['id'], 'segundo', 'parcial'),
            (duplicado['id'], 'primeiro', 'extraido')])
        self.assertIn('linha cortada', resultados[1]['detalhe'])

    def test_reexecucao_usa_sha_e_preserva_ocr_bruto(self):
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
            revisar_ocr.preparar(fila, {item['id']: item}, self.pasta)
        with closing(sqlite3.connect(caminho_fila)) as fila:
            revisar_ocr.preparar(fila, {item['id']: item}, self.pasta)
            self.assertEqual(fila.execute('SELECT estado FROM fila').fetchone()[0], 'revisado')
            revisoes = ingerir_anexos.ler_revisoes_manuais(self.anexos)
            self.assertEqual(revisoes[item['id'], item['sha256']][0][:2], ('parcial', 'revisado'))
            self.assertEqual(ingerir_anexos.ler_transcricoes(self.anexos)[item['id'], item['sha256']][1], 'OCR bruto')
        with closing(sqlite3.connect(caminho_fila)) as fila:
            novo = dict(item, sha256='0' * 64)
            revisar_ocr.preparar(fila, {item['id']: novo}, self.pasta)
            self.assertEqual(fila.execute('SELECT estado FROM fila').fetchone()[0], 'pendente')
            self.assertNotIn((item['id'], novo['sha256']), revisoes)


if __name__ == '__main__':
    unittest.main()
