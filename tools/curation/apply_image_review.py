import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from tools.curation.build_graph import PROJECT, open_read_only, apply_doist_reviews
from tools.curation.build_wiki import WikiEdition, LEARNING_USES, copy_images, read_classifications, rotulo, source_text
from tools.curation.build_attachments import (HAS_TEXT, write_attachment_page, read_downloads,
                            find_message)
from tools.curation.review_records import read_receipt, needs_review


def _hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _write_atomic(path, conteudo):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(conteudo)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _received_records(dados, grafo, anteriores=None, *, verificar_todos=False):
    anteriores = anteriores or {}
    pasta = dados / 'revisao-ocr' / 'terra'
    raiz = (dados / 'zulip' / 'anexos').resolve()
    validos = {}
    erros = []
    with open_read_only(raiz / 'estado.sqlite3') as anexos, open_read_only(grafo) as db:
        for arquivo in sorted(pasta.glob('*.json')):
            try:
                item = read_receipt(arquivo)
                if needs_review(item):
                    continue
                chave = item['id']
                if chave.startswith('zulip-anexo-'):
                    linha = anexos.execute("SELECT arquivo, sha256 FROM arquivos WHERE id=? AND estado='baixado'", (chave,)).fetchone()
                    base = raiz
                else:
                    linha = db.execute("SELECT caminho, NULL FROM nos WHERE id=? AND tipo='captura'", (chave,)).fetchone()
                    base = dados.resolve()
                if not linha or not linha[0]:
                    raise ValueError("Original file missing from the catalog.")
                original = (base / linha[0]).resolve()
                if not original.is_relative_to(base) or not original.is_file():
                    raise ValueError("Original file missing or outside the directory.")
                recibo_hash = _hash(arquivo)
                if linha[1] and linha[1] != item['sha256']:
                    raise ValueError("The SHA-256 differs from the inventory.")
                cache_valido = (not verificar_todos and linha[1] == item['sha256']
                                and anteriores.get(chave) == recibo_hash)
                if not cache_valido and _hash(original) != item['sha256']:
                    raise ValueError("The SHA-256 differs from the original.")
                validos[chave] = (item, recibo_hash)
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                erros.append(f'{arquivo.name}: {exc}')
    return validos, erros


def _temporary_graph(origem, dados):
    with NamedTemporaryFile(dir=origem.parent, suffix='.sqlite3', delete=False) as f:
        temp = Path(f.name)
    try:
        with closing(sqlite3.connect(origem.resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(temp)) as db:
            src.backup(db)
            with db:
                db.execute('PRAGMA foreign_keys=ON')
                apply_doist_reviews(db, dados)
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError("Invalid temporary graph.")
        return temp
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _topics(edicao, capturas):
    indice_path = edicao.pasta / 'temas/index.md'
    indice = indice_path.read_text(encoding='utf-8')
    for slug in LEARNING_USES:
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
        edicao.write_page(path, texto)
        padrao = rf'(\]\({re.escape(slug)}/index\.md\) · \d+ tópicos · )\d+( capturas)'
        indice, n = re.subn(padrao, lambda m: m[1] + str(len(itens)) + m[2], indice)
        if n != 1:
            raise ValueError(f'Invalid topic index: {slug}')
    edicao.write_page('temas/index.md', indice)


def publicar(dados: Path, wiki_local: Path):
    dados, wiki_local = dados.resolve(), wiki_local.resolve()
    grafo = dados / 'wiki/grafo.sqlite3'
    edicao = WikiEdition(wiki_local)
    manifesto = json.loads((wiki_local / 'manifesto.json').read_text(encoding='utf-8'))
    if manifesto.get('schema_version') != 1:
        raise ValueError("Unknown manifest version.")
    registro = dados / 'revisao-ocr/publicados.json'
    anteriores = json.loads(registro.read_text(encoding='utf-8')) if registro.is_file() else {}
    validos, erros = _received_records(dados, grafo, anteriores)
    atuais = {chave: digest for chave, (_, digest) in validos.items()}
    pendentes = {chave for chave, digest in atuais.items() if anteriores.get(chave) != digest}
    if not pendentes:
        return {'publicados': 0, 'invalidos': erros}
    edicao.arquivos.update(manifesto['arquivos'])
    tem_doist = any(chave.startswith('doist-') for chave in pendentes)
    temp = _temporary_graph(grafo, dados) if tem_doist else None
    try:
        with open_read_only(temp or wiki_local / 'grafo.sqlite3') as db:
            classificacoes = read_classifications(db)
            if tem_doist:
                _, por_tema = copy_images(db, dados, edicao, classificacoes)
                _topics(edicao, por_tema)
            pasta = dados / 'zulip/anexos'
            arquivos, referencias = read_downloads(pasta)
            por_id = {valor[0]: (url, valor) for url, valor in arquivos.items()}
            catalogo = json.loads((wiki_local / 'anexos/extracao.json').read_text(encoding='utf-8'))
            for chave in sorted(pendentes):
                if not chave.startswith('zulip-anexo-'):
                    continue
                if chave not in por_id or chave not in catalogo:
                    raise ValueError(f'Attachment missing from the edition: {chave}')
                url, (_, _, _, resumo) = por_id[chave]
                item_revisao = validos[chave][0]
                if item_revisao['sha256'] != resumo:
                    raise ValueError(f'The inventory changed during publication: {chave}')
                revisao = tuple(item_revisao[campo] for campo in ('estado', 'texto', 'metodo', 'detalhe'))
                ligacoes = []
                for mid in referencias.get(url, ()):
                    local = find_message(db, mid)
                    if local:
                        _, backlink, titulo = local
                        ligacoes.append((mid, backlink, titulo))
                write_attachment_page(edicao, chave, revisao, ligacoes, classificacoes)
                estado, _, metodo, detalhe = revisao
                item = catalogo[chave]
                item.update(transcription=estado, transcription_method=metodo, manual_review=True)
                if detalhe:
                    item['note'] = detalhe
                else:
                    item.pop('note', None)
            edicao.write_page('anexos/extracao.json', json.dumps(catalogo, ensure_ascii=False, indent=2) + '\n')
        totais = manifesto['totais'].copy()
        totais['anexos_com_texto'] = sum(item['transcription'] in HAS_TEXT for item in catalogo.values())
        totais['anexos_revisados_manualmente'] = sum(item.get('manual_review') is True for item in catalogo.values())
        indice = (wiki_local / 'anexos/index.md').read_text(encoding='utf-8')
        indice, n = re.subn(r'[\d,]+ têm texto extraído ou fala transcrita\.', f"{totais['anexos_com_texto']:,} têm texto extraído ou fala transcrita.", indice, count=1)
        if n != 1:
            raise ValueError("Invalid attachment index.")
        edicao.write_page('anexos/index.md', indice)
        if temp is not None:
            edicao.copiar('grafo.sqlite3', temp)
            temp.replace(grafo)
        edicao.finish(totais)
        nomes = {f'anexos/{chave}.md' for chave in pendentes if chave.startswith('zulip-anexo-')}
        nomes.update({'anexos/extracao.json', 'anexos/index.md'})
        nomes.update(nome for nome, resumo in edicao.arquivos.items()
                     if nome != 'manifesto.json' and manifesto['arquivos'].get(nome) != resumo)
        if tem_doist:
            nomes.update(nome for nome in edicao.arquivos if nome.startswith(('doist/', 'temas/'))
                         and nome.endswith('.md'))
            nomes.add('grafo.sqlite3')
        _verify_manifest(wiki_local, nomes)
        _write_atomic(registro, (json.dumps(atuais, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))
        return {'publicados': len(pendentes), 'invalidos': erros, 'arquivos_escritos': edicao.escritos}
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _verify_manifest(wiki_local, nomes):
    manifesto = json.loads((wiki_local / 'manifesto.json').read_text(encoding='utf-8'))
    if manifesto.get('schema_version') != 1:
        raise ValueError("Unknown manifest version.")
    raiz = wiki_local.resolve()
    for nome in nomes:
        caminho = (raiz / nome).resolve()
        if not caminho.is_relative_to(raiz) or not caminho.is_file():
            raise ValueError(f'File missing from the manifest: {nome}')
        if manifesto['arquivos'].get(nome) != _hash(caminho):
            raise ValueError(f'Manifest checksum mismatch: {nome}')


def verify_completion(dados: Path, wiki_local: Path):
    dados, wiki_local = dados.resolve(), wiki_local.resolve()
    registro = dados / 'revisao-ocr/publicados.json'
    anteriores = json.loads(registro.read_text(encoding='utf-8')) if registro.is_file() else {}
    validos, erros = _received_records(dados, dados / 'wiki/grafo.sqlite3', verificar_todos=True)
    atuais = {chave: digest for chave, (_, digest) in validos.items()}
    if erros or atuais != anteriores:
        raise ValueError(f'Missing, changed, or unpublished reviews: {erros}. Different records: {sorted((k for k in atuais.keys() | anteriores.keys() if atuais.get(k) != anteriores.get(k)))}')
    manifesto = json.loads((wiki_local / 'manifesto.json').read_text(encoding='utf-8'))
    _verify_manifest(wiki_local, manifesto['arquivos'])
    if _hash(dados / 'wiki/grafo.sqlite3') != _hash(wiki_local / 'grafo.sqlite3'):
        raise ValueError("The graph copies differ.")
    with open_read_only(wiki_local / 'grafo.sqlite3') as db:
        for chave, (item, _) in validos.items():
            doist = chave.startswith('doist-')
            pasta = 'doist' if doist else 'anexos'
            pagina = (wiki_local / pasta / f'{chave}.md').read_bytes()
            if item['texto']:
                if not pagina.endswith(source_text(item['texto']).encode('utf-8')):
                    raise ValueError(f'The published text differs from the review for {chave}')
            elif b'\n## Content\n' in pagina:
                raise ValueError(f'The page has content but the review has no text: {chave}')
            if doist:
                captura = db.execute('SELECT texto,estado FROM nos WHERE id=?', (chave,)).fetchone()
                if captura != (item['texto'], item['estado']):
                    raise ValueError(f'The graph differs from the review for {chave}')
    return {'recibos_verificados': len(atuais), 'arquivos_verificados': len(manifesto['arquivos'])}


def main():
    parser = argparse.ArgumentParser(description='Apply the image review records to the wiki.')
    parser.add_argument("--data", type=Path, default=PROJECT / 'dados')
    parser.add_argument("--local-wiki", type=Path, default=PROJECT / 'wiki/local')
    parser.add_argument("--verify-completion", action='store_true')
    args = parser.parse_args()
    resultado = verify_completion(args.data, args.local_wiki) if args.verify_completion else publicar(args.data, args.local_wiki)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
