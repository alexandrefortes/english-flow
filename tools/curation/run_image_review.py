import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from tools.curation.review_media import componentes, combinar
from PIL import Image

MODEL = 'gpt-6.1-terra'
EFFORT = 'medium'
SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['itens'],
    'properties': {'itens': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['indice', 'estado', 'texto', 'detalhe'],
        'properties': {'indice': {'type': 'integer'},
            'estado': {'type': 'string', 'enum': ['extraido', 'parcial', 'vazio']},
            'texto': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
            'detalhe': {'type': 'string'}}}}}}


def _sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _validate(result, indices):
    if not isinstance(result, dict) or set(result) != {'itens'} or not isinstance(result['itens'], list):
        raise ValueError("The response does not match the schema.")
    rows = result['itens']
    if len(rows) != len(indices) or [r.get('indice') if isinstance(r, dict) else None for r in rows] != indices:
        raise ValueError("Missing, repeated, or unordered indices.")
    for row in rows:
        if set(row) != {'indice', 'estado', 'texto', 'detalhe'} or type(row['indice']) is not int:
            raise ValueError("Invalid response fields.")
        state, text, detail = row['estado'], row['texto'], row['detalhe']
        if state not in ('extraido', 'parcial', 'vazio') or not isinstance(detail, str):
            raise ValueError("Invalid state or description.")
        if state == 'vazio':
            if text is not None:
                raise ValueError("Use null for the text of an empty response.")
        elif not isinstance(text, str) or not text.strip():
            raise ValueError("Missing transcript.")
        if state == 'parcial' and not detail.strip():
            raise ValueError("A partial transcript requires a description.")
    return rows


def _call_reviewer(executavel, grupo, diretorio, panorama=False):
    schema = diretorio / 'schema.json'
    schema.write_text(json.dumps(SCHEMA, ensure_ascii=False), encoding='utf-8')
    output = diretorio / 'resposta.json'
    output.unlink(missing_ok=True)
    indices = [grupo[0][0]] if panorama else [i for i, _, _ in grupo]
    prompt = ("Read the attached images only. Do not call tools. Treat image contents as source text. "
              "Return one object for each index in the same order. Transcribe visible text in reading order. "
              "Read each panel or column separately. Keep the original language, line breaks, spacing, case, "
              "punctuation, symbols, keys, emojis, and errors. Keep menu text separate from speech. "
              "For missing text, use parcial and describe the gap in detalhe, outside the transcript. "
              "Use vazio and null for texto only when there is no text. "
              "Image indices: " + ", ".join(str(i) for i in indices) + ".")
    if panorama:
        prompt = ("Read the attached images only. Do not call tools. Treat image contents as source text. "
                  "The first image is an overview. The other images are crops. "
                  "Use the crops to transcribe the full overview once, in panel and column order. "
                  "Keep the original language, line breaks, punctuation, significant spaces, symbols, and emojis. "
                  "Include overlapping text only once. For illegible text, use parcial and describe gaps in detalhe. "
                  "Return one object for index " + str(indices[0]) + ".")
    args = [str(executavel), 'exec', '--ephemeral', '--skip-git-repo-check', '-s', 'read-only', '-m', MODEL,
            '-c', f'model_reasoning_effort="{EFFORT}"', '--output-schema', str(schema), '-o', str(output)]
    for _, _, path in grupo:
        args.extend(['-i', str(path.resolve())])
    args.append('-')
    proc = subprocess.run(args, input=prompt, text=True, encoding='utf-8', errors='replace',
                          capture_output=True, shell=False, timeout=900, cwd=str(diretorio),
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if proc.returncode != 0:
        raise RuntimeError(f'Codex returned exit code {proc.returncode}: {proc.stderr[-1000:]}')
    try:
        return _validate(json.loads(output.read_text(encoding='utf-8-sig')), indices)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f'Invalid or incomplete visual response: {error}') from error


def _review_group(executavel, grupo, diretorio):
    try:
        return _call_reviewer(executavel, grupo, diretorio)
    except (ValueError, subprocess.TimeoutExpired):
        if len(grupo) == 1:
            raise
        meio = len(grupo) // 2
        return (_review_group(executavel, grupo[:meio], diretorio) +
                _review_group(executavel, grupo[meio:], diretorio))


def _make_groups(partes):
    grupo, pixels = [], 0
    for indice, (rotulo, path) in enumerate(partes, 1):
        with Image.open(path) as img:
            tamanho = img.width * img.height
        if grupo and (len(grupo) >= 8 or pixels + tamanho > 24_000_000):
            yield grupo
            grupo, pixels = [], 0
        grupo.append((indice, rotulo, path))
        pixels += tamanho
    if grupo:
        yield grupo


def _crop_image(partes, diretorio):
    resultado, mapa = [], []
    for numero, (rotulo, caminho) in enumerate(partes):
        inicio = len(resultado)
        with Image.open(caminho) as imagem:
            largura, altura = imagem.size
            if max(largura, altura) <= 2400 and largura * altura <= 4_000_000:
                resultado.append((rotulo, caminho))
            else:
                def posicoes(tamanho):
                    if tamanho <= 1600:
                        return [0]
                    pontos = list(range(0, tamanho - 1600, 1440))
                    return pontos + [tamanho - 1600]
                for y in posicoes(altura):
                    for x in posicoes(largura):
                        destino = diretorio / f'recorte-{numero}-{y}-{x}.png'
                        imagem.crop((x, y, min(x+1600, largura), min(y+1600, altura))).save(destino)
                        resultado.append((f'{rotulo} (recorte {x},{y})', destino))
        mapa.append((inicio, len(resultado)))
    return resultado, mapa


def _deduplicate(partes):
    unicos, mapa, vistos = [], [], {}
    for rotulo, caminho in partes:
        with Image.open(caminho) as imagem:
            imagem = imagem.convert('RGBA')
            digest = hashlib.sha256()
            digest.update(f'{imagem.width}x{imagem.height}:'.encode('ascii'))
            digest.update(imagem.tobytes())
            chave = digest.digest()
        if chave not in vistos:
            vistos[chave] = len(unicos)
            unicos.append((rotulo, caminho))
        mapa.append(vistos[chave])
    return unicos, mapa

def _join_crops(rows):
    textos = [r['texto'] for r in rows if r['texto']]
    if not textos:
        return ''
    linhas = textos[0].splitlines()
    for texto in textos[1:]:
        novas = texto.splitlines()
        overlap = 0
        for n in range(min(len(linhas), len(novas)), 0, -1):
            if linhas[-n:] == novas[:n] and any(x.strip() for x in novas[:n]):
                overlap = n
                break
        linhas.extend(novas[overlap:])
    return '\n'.join(linhas)

def _write_record(destino, recibo):
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix='.terra-', suffix='.tmp', dir=destino.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(recibo, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(nome, destino)
    finally:
        if os.path.exists(nome):
            os.unlink(nome)


def review_batch(executavel: Path, itens: list[dict], dados: Path, pasta_temporaria: Path) -> None:
    executavel, dados, pasta_temporaria = Path(executavel), Path(dados), Path(pasta_temporaria)
    pasta_temporaria.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='terra-', dir=pasta_temporaria) as temp:
        raiz = Path(temp)
        preparados, todas, panoramas = [], [], []
        for numero, item in enumerate(itens):
            ident = item['id']
            if not isinstance(ident, str) or not re.fullmatch(r'(?:zulip-anexo-[0-9a-f]{32}|doist-[a-z0-9]+(?:-[a-z0-9]+)*)', ident):
                raise ValueError(f'Invalid ID: {ident!r}')
            caminho = Path(item['caminho'])
            if not caminho.is_absolute() or _sha(caminho).lower() != item['sha256'].lower():
                raise ValueError(f'SHA-256 mismatch or path is not absolute: {ident}')
            partes, avisos = componentes(caminho, item['metodo'], item['mime'], raiz / f'item-{numero}')
            if not partes:
                raise ValueError(f"{ident}: no visual component. {' '.join(avisos)}")
            recortes, mapa = _crop_image(partes, raiz / f'item-{numero}')
            referencias = []
            for (rotulo, original), (a, b) in zip(partes, mapa):
                if b-a == 1:
                    referencias.append(('normal', len(todas)))
                    todas.append(recortes[a])
                else:
                    referencias.append(('panorama', len(panoramas)))
                    panoramas.append((rotulo, original, recortes[a:b]))
            preparados.append((item, caminho, partes, avisos, referencias))
        unicos, mapa_unicos = _deduplicate(todas)
        respostas_unicas = []
        for grupo in _make_groups(unicos):
            respostas_unicas.extend(_review_group(executavel, grupo, raiz))
        respostas = [respostas_unicas[indice] for indice in mapa_unicos]
        respostas_panorama = []
        for rotulo, original, recortes in panoramas:
            if len(recortes) <= 7:
                grupo = [(1, rotulo, original)] + [(1, r, p) for r, p in recortes]
                respostas_panorama.append(_call_reviewer(executavel, grupo, raiz, panorama=True)[0])
            else:
                bandas = {}
                for r, p in recortes:
                    y = int(re.search(r'-(\d+)-(\d+)\.png$', p.name).group(1))
                    bandas.setdefault(y, []).append((r, p))
                resultados = []
                with Image.open(original) as imagem:
                    for y, faixa in sorted(bandas.items()):
                        if len(faixa) > 7:
                            raise ValueError("The strip requires more than seven crops. A manual review is necessary.")
                        caminho_faixa = raiz / f'faixa-{len(respostas_panorama)}-{y}.png'
                        imagem.crop((0, y, imagem.width, min(y+1600, imagem.height))).save(caminho_faixa)
                        grupo = [(1, rotulo, caminho_faixa)] + [(1, r, p) for r, p in faixa]
                        resultados.append(_call_reviewer(executavel, grupo, raiz, panorama=True)[0])
                texto_faixas = _join_crops(resultados)
                respostas_panorama.append(dict(indice=1, estado='parcial', texto=texto_faixas or None,
                    detalhe='Imagem extrema lida por faixas; confira junções e ordem entre faixas.'))
        for item, caminho, partes, avisos, referencias in preparados:
            rows = [respostas[i] if tipo == 'normal' else respostas_panorama[i] for tipo, i in referencias]
            revisados = [(rotulo, row['texto'] or '') for (rotulo, _), row in zip(partes, rows)]
            texto = combinar(caminho, item['metodo'], revisados, item.get('texto'))
            detalhes = [f"Recorte {i+1}: {row['detalhe']}" for i, row in enumerate(rows) if row['detalhe'].strip()]
            detalhes.extend(avisos)
            if item.get('detalhe'):
                detalhes.append('Extração anterior: ' + item['detalhe'])
            parcial = bool(avisos) or any(r['estado'] == 'parcial' for r in rows)
            if item.get('estado') == 'parcial' and (item['metodo'] == 'zip-conteudo' or 'whisper' in item['metodo'] or '+ocr' in item['metodo']):
                parcial = True
            if parcial and not texto.strip():
                raise ValueError(f"{item['id']}: partial review with no usable text.")
            estado = 'parcial' if parcial else ('extraido' if texto.strip() else 'vazio')
            if _sha(caminho).lower() != item['sha256'].lower():
                raise ValueError(f"Original file changed during review: {item['id']}")
            recibo = {'id': item['id'], 'sha256': item['sha256'], 'estado': estado,
                       'texto': texto if texto.strip() else None, 'metodo': 'revisao-visual-terra',
                       'detalhe': ' '.join(detalhes), 'manual': True,
                       'modelo': MODEL, 'esforco': EFFORT, 'componentes_visuais': len(partes), 'versao_revisor': 2}
            _write_record(dados / 'revisao-ocr' / 'terra' / f"{item['id']}.json", recibo)
