"""Publica revisões visuais sem alterar as transcrições automáticas."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from construir_grafo import PROJETO, abrir_leitura, aplicar_revisoes_doist
from ingerir_acervo import Edicao, RESUMO, copiar_capturas, ler_classificacoes, rotulo, texto_original
from ingerir_anexos import (TEXTO_DISPONIVEL, escrever_pagina, ler_downloads,
                            localizar_mensagem)
from recibos_ocr import ler_recibo, precisa_releitura


def _hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _atomico(path, conteudo):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(conteudo)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _recebidos(dados, grafo, anteriores=None, *, verificar_todos=False):
    anteriores = anteriores or {}
    pasta = dados / 'revisao-ocr' / 'terra'
    raiz = (dados / 'zulip' / 'anexos').resolve()
    validos = {}
    erros = []
    with abrir_leitura(raiz / 'estado.sqlite3') as anexos, abrir_leitura(grafo) as db:
        for arquivo in sorted(pasta.glob('*.json')):
            try:
                item = ler_recibo(arquivo)
                if precisa_releitura(item):
                    continue
                chave = item['id']
                if chave.startswith('zulip-anexo-'):
                    linha = anexos.execute("SELECT arquivo, sha256 FROM arquivos WHERE id=? AND estado='baixado'", (chave,)).fetchone()
                    base = raiz
                else:
                    linha = db.execute("SELECT caminho, NULL FROM nos WHERE id=? AND tipo='captura'", (chave,)).fetchone()
                    base = dados.resolve()
                if not linha or not linha[0]:
                    raise ValueError('original ausente do catálogo')
                original = (base / linha[0]).resolve()
                if not original.is_relative_to(base) or not original.is_file():
                    raise ValueError('original ausente ou fora da pasta')
                recibo_hash = _hash(arquivo)
                if linha[1] and linha[1] != item['sha256']:
                    raise ValueError('SHA-256 não corresponde ao inventário')
                cache_valido = (not verificar_todos and linha[1] == item['sha256']
                                and anteriores.get(chave) == recibo_hash)
                if not cache_valido and _hash(original) != item['sha256']:
                    raise ValueError('SHA-256 não corresponde ao original')
                validos[chave] = (item, recibo_hash)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                erros.append(f'{arquivo.name}: {exc}')
    return validos, erros


def _grafo_temp(origem, dados):
    with NamedTemporaryFile(dir=origem.parent, suffix='.sqlite3', delete=False) as f:
        temp = Path(f.name)
    try:
        with closing(sqlite3.connect(origem.resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(temp)) as db:
            src.backup(db)
            with db:
                db.execute('PRAGMA foreign_keys=ON')
                aplicar_revisoes_doist(db, dados)
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Grafo temporário inválido')
        return temp
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _temas(edicao, capturas):
    indice_path = edicao.pasta / 'temas/index.md'
    indice = indice_path.read_text(encoding='utf-8')
    for slug in RESUMO:
        path = f'temas/{slug}/index.md'
        texto = (edicao.pasta / path).read_text(encoding='utf-8')
        texto = re.sub(r'## Capturas Doist\n\n.*?(?=## Tópicos do Zulip por canal\n\n|Nenhum exemplo classificado neste recorte\.\n|\Z)', '', texto, flags=re.S)
        itens = capturas.get(slug, [])
        secao = '## Capturas Doist\n\n' + ''.join(f'- [{rotulo(titulo)}](../../doist/{chave}.md)\n' for titulo, chave in itens) + '\n' if itens else ''
        marco = '## Tópicos do Zulip por canal\n\n'
        if marco in texto:
            texto = texto.replace(marco, secao + marco, 1)
        else:
            texto = texto.replace('Nenhum exemplo classificado neste recorte.\n', '') if itens else texto
            texto += secao
            if not itens and 'Nenhum exemplo classificado neste recorte.' not in texto:
                texto += 'Nenhum exemplo classificado neste recorte.\n'
        edicao.escrever(path, texto)
        padrao = rf'(\]\({re.escape(slug)}/index\.md\) · \d+ tópicos · )\d+( capturas)'
        indice, n = re.subn(padrao, lambda m: m[1] + str(len(itens)) + m[2], indice)
        if n != 1:
            raise ValueError(f'Índice temático inválido: {slug}')
    edicao.escrever('temas/index.md', indice)


def publicar(dados: Path, wiki_local: Path):
    dados, wiki_local = dados.resolve(), wiki_local.resolve()
    grafo = dados / 'wiki/grafo.sqlite3'
    edicao = Edicao(wiki_local)
    manifesto = json.loads((wiki_local / 'manifesto.json').read_text(encoding='utf-8'))
    if manifesto.get('schema_version') != 1:
        raise ValueError('Manifesto de versão desconhecida')
    registro = dados / 'revisao-ocr/publicados.json'
    anteriores = json.loads(registro.read_text(encoding='utf-8')) if registro.is_file() else {}
    validos, erros = _recebidos(dados, grafo, anteriores)
    atuais = {chave: digest for chave, (_, digest) in validos.items()}
    pendentes = {chave for chave, digest in atuais.items() if anteriores.get(chave) != digest}
    if not pendentes:
        return {'publicados': 0, 'invalidos': erros}
    edicao.arquivos.update(manifesto['arquivos'])
    tem_doist = any(chave.startswith('doist-') for chave in pendentes)
    temp = _grafo_temp(grafo, dados) if tem_doist else None
    try:
        with abrir_leitura(temp or wiki_local / 'grafo.sqlite3') as db:
            classificacoes = ler_classificacoes(db)
            if tem_doist:
                _, por_tema = copiar_capturas(db, dados, edicao, classificacoes)
                _temas(edicao, por_tema)
            pasta = dados / 'zulip/anexos'
            arquivos, referencias = ler_downloads(pasta)
            por_id = {valor[0]: (url, valor) for url, valor in arquivos.items()}
            catalogo = json.loads((wiki_local / 'anexos/extracao.json').read_text(encoding='utf-8'))
            for chave in sorted(pendentes):
                if not chave.startswith('zulip-anexo-'):
                    continue
                if chave not in por_id or chave not in catalogo:
                    raise ValueError(f'Anexo ausente da edição: {chave}')
                url, (_, _, _, resumo) = por_id[chave]
                item_revisao = validos[chave][0]
                if item_revisao['sha256'] != resumo:
                    raise ValueError(f'Inventário mudou durante publicação: {chave}')
                revisao = tuple(item_revisao[campo] for campo in ('estado', 'texto', 'metodo', 'detalhe'))
                ligacoes = []
                for mid in referencias.get(url, ()):
                    local = localizar_mensagem(db, mid)
                    if local:
                        _, backlink, titulo = local
                        ligacoes.append((mid, backlink, titulo))
                escrever_pagina(edicao, chave, revisao, ligacoes, classificacoes)
                estado, _, metodo, detalhe = revisao
                item = catalogo[chave]
                item.update(transcription=estado, transcription_method=metodo, manual_review=True)
                if detalhe:
                    item['note'] = detalhe
                else:
                    item.pop('note', None)
            edicao.escrever('anexos/extracao.json', json.dumps(catalogo, ensure_ascii=False, indent=2) + '\n')
        totais = manifesto['totais'].copy()
        totais['anexos_com_texto'] = sum(item['transcription'] in TEXTO_DISPONIVEL for item in catalogo.values())
        totais['anexos_revisados_manualmente'] = sum(item.get('manual_review') is True for item in catalogo.values())
        indice = (wiki_local / 'anexos/index.md').read_text(encoding='utf-8')
        indice, n = re.subn(r'[\d,]+ têm texto extraído ou fala transcrita\.', f"{totais['anexos_com_texto']:,} têm texto extraído ou fala transcrita.", indice, count=1)
        if n != 1:
            raise ValueError('Índice de anexos inválido')
        edicao.escrever('anexos/index.md', indice)
        if temp is not None:
            edicao.copiar('grafo.sqlite3', temp)
            # A retomada refaz a troca se houver interrupção antes do registro.
            temp.replace(grafo)
        edicao.finalizar(totais)
        nomes = {f'anexos/{chave}.md' for chave in pendentes if chave.startswith('zulip-anexo-')}
        nomes.update({'anexos/extracao.json', 'anexos/index.md'})
        nomes.update(nome for nome, resumo in edicao.arquivos.items()
                     if nome != 'manifesto.json' and manifesto['arquivos'].get(nome) != resumo)
        if tem_doist:
            nomes.update(nome for nome in edicao.arquivos if nome.startswith(('doist/', 'temas/'))
                         and nome.endswith('.md'))
            nomes.add('grafo.sqlite3')
        _verificar_manifesto(wiki_local, nomes)
        _atomico(registro, (json.dumps(atuais, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))
        return {'publicados': len(pendentes), 'invalidos': erros, 'arquivos_escritos': edicao.escritos}
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _verificar_manifesto(wiki_local, nomes):
    manifesto = json.loads((wiki_local / 'manifesto.json').read_text(encoding='utf-8'))
    if manifesto.get('schema_version') != 1:
        raise ValueError('Manifesto de versão desconhecida')
    raiz = wiki_local.resolve()
    for nome in nomes:
        caminho = (raiz / nome).resolve()
        if not caminho.is_relative_to(raiz) or not caminho.is_file():
            raise ValueError(f'Arquivo ausente no manifesto: {nome}')
        if manifesto['arquivos'].get(nome) != _hash(caminho):
            raise ValueError(f'Hash do manifesto não confere: {nome}')


def verificar_fechamento(dados: Path, wiki_local: Path):
    dados, wiki_local = dados.resolve(), wiki_local.resolve()
    registro = dados / 'revisao-ocr/publicados.json'
    anteriores = json.loads(registro.read_text(encoding='utf-8')) if registro.is_file() else {}
    validos, erros = _recebidos(dados, dados / 'wiki/grafo.sqlite3', verificar_todos=True)
    atuais = {chave: digest for chave, (_, digest) in validos.items()}
    if erros or atuais != anteriores:
        raise ValueError(f'Revisões inválidas, alteradas ou não publicadas: {erros}; divergentes: '
                         f'{sorted(k for k in atuais.keys() | anteriores.keys() if atuais.get(k) != anteriores.get(k))}')
    manifesto = json.loads((wiki_local / 'manifesto.json').read_text(encoding='utf-8'))
    _verificar_manifesto(wiki_local, manifesto['arquivos'])
    if _hash(dados / 'wiki/grafo.sqlite3') != _hash(wiki_local / 'grafo.sqlite3'):
        raise ValueError('As cópias do grafo divergem')
    with abrir_leitura(wiki_local / 'grafo.sqlite3') as db:
        for chave, (item, _) in validos.items():
            doist = chave.startswith('doist-')
            pasta = 'doist' if doist else 'anexos'
            pagina = (wiki_local / pasta / f'{chave}.md').read_bytes()
            if item['texto']:
                if not pagina.endswith(texto_original(item['texto']).encode('utf-8')):
                    raise ValueError(f'Texto publicado difere da revisão de {chave}')
            elif b'\n## Content\n' in pagina:
                raise ValueError(f'Página com conteúdo para revisão sem texto: {chave}')
            if doist:
                captura = db.execute('SELECT texto,estado FROM nos WHERE id=?', (chave,)).fetchone()
                if captura != (item['texto'], item['estado']):
                    raise ValueError(f'O grafo difere da revisão de {chave}')
    return {'recibos_verificados': len(atuais), 'arquivos_verificados': len(manifesto['arquivos'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dados', type=Path, default=PROJETO / 'dados')
    parser.add_argument('--wiki-local', type=Path, default=PROJETO / 'wiki/local')
    parser.add_argument('--verificar-fechamento', action='store_true')
    args = parser.parse_args()
    resultado = verificar_fechamento(args.dados, args.wiki_local) if args.verificar_fechamento else publicar(args.dados, args.wiki_local)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
