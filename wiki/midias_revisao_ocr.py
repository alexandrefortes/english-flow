"""Prepara imagens para revisão visual e conserva texto não visual existente."""
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import ZipFile

from PIL import Image, ImageOps
try:
    from . import transcrever_anexos as t
except ImportError:
    import transcrever_anexos as t


def zip_com_imagens(caminho):
    """Consulta somente o diretório central; erros de ZIP são propagados."""
    with ZipFile(caminho) as arquivo:
        return any(not m.is_dir() and PurePosixPath(m.filename).suffix.lower() in t.IMAGE_EXTENSIONS
                   for m in arquivo.infolist())


def _imagem(origem, destino):
    with Image.open(origem) as img:
        img.seek(0)
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA') or 'transparency' in img.info:
            rgba = img.convert('RGBA')
            fundo = Image.new('RGBA', rgba.size, 'white')
            img = Image.alpha_composite(fundo, rgba).convert('RGB')
        else:
            img = img.convert('RGB')
        img.save(destino, 'PNG')


def _pdf(caminho, diretorio):
    import pymupdf
    saida, avisos = [], []
    with t.PDF_LOCK, pymupdf.open(caminho) as doc:
        if doc.needs_pass:
            raise ValueError('PDF protegido por senha.')
        pendentes = [i for i, page in enumerate(doc) if not page.get_text(sort=True).strip()]
        if len(pendentes) > 20:
            avisos.append(f'{len(pendentes)-20} páginas sem camada de texto excedem o limite de 20.')
        for i in pendentes[:20]:
            try:
                page = doc[i]
                scale = min(2.0, 2200 / max(1, page.rect.width, page.rect.height))
                output = diretorio / f'pagina-{i+1:04d}.png'
                page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(output)
                saida.append((f'Página {i+1}', output))
            except (OSError, RuntimeError, ValueError) as error:
                avisos.append(f'Página {i+1}: {error}')
    return saida, avisos


def _video(caminho, diretorio):
    info = json.loads(t.run_tool('ffprobe', '-v', 'error', '-show_entries',
        'format=duration:stream=codec_type:stream_disposition=attached_pic', '-of', 'json', *t.ffinput(caminho)))
    streams = info.get('streams', [])
    if not any(s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic') for s in streams):
        return [], ['Arquivo sem vídeo para revisão visual.']
    valor = str(info.get('format', {}).get('duration', '0'))
    duracao = float(valor) if re.fullmatch(r'\d+(?:\.\d+)?', valor) else 0.0
    intervalo = max(duracao / 16, 0.5)
    try:
        t.run_tool('ffmpeg', '-nostdin', '-v', 'error', '-threads', '1', *t.ffinput(caminho),
            '-map', '0:v:0', '-vf', f'fps=1/{intervalo}:start_time=0',
            '-frames:v', '16', '-threads', '1', diretorio / 'quadro-%03d.png', timeout=180)
    except RuntimeError:
        # Some still GIFs have no usable duration for the fps filter.
        pass
    imagens = sorted(diretorio.glob('quadro-*.png'))
    if not imagens:
        output = diretorio / 'quadro-000.png'
        t.run_tool('ffmpeg', '-nostdin', '-v', 'error', *t.ffinput(caminho), '-map', '0:v:0',
                   '-frames:v', '1', '-threads', '1', output, timeout=60)
        imagens = [output] if output.is_file() else []
    return [(f'Quadro {i}', p) for i, p in enumerate(imagens, 1)], []


def _heif(caminho, diretorio):
    info = json.loads(t.run_tool('ffprobe', '-v', 'error', '-show_stream_groups', '-of', 'json', *t.ffinput(caminho)))
    grupos = [g for g in info.get('stream_groups', []) if g.get('type') == 'Tile Grid' and g.get('components')]
    cmd = ['-nostdin', '-v', 'error', '-threads', '1', *t.ffinput(caminho)]
    if grupos:
        grupo = max(grupos, key=lambda g: g['components'][0]['width'] * g['components'][0]['height'])
        canvas = grupo['components'][0]; tiles = canvas['subcomponents']
        width, height = canvas['width'], canvas['height']
        if len(tiles) > 100 or not 0 < width * height <= 80_000_000:
            raise ValueError('Grade de imagem excede os limites de OCR.')
        inputs = ''.join(f"[0:{grupo['streams'][tile['stream_index']]['index']}]" for tile in tiles)
        offsets = '|'.join(f"{tile['tile_horizontal_offset']}_{tile['tile_vertical_offset']}" for tile in tiles)
        graph = inputs + f"xstack=inputs={len(tiles)}:layout={offsets}:fill=white,crop={width}:{height}:{canvas['horizontal_offset']}:{canvas['vertical_offset']}[picture]"
        cmd += ['-filter_complex_threads', '1', '-filter_complex', graph, '-map', '[picture]']
    else:
        cmd += ['-map', '0:v:0']
    output = diretorio / 'heif.png'
    t.run_tool('ffmpeg', *cmd, '-frames:v', '1', '-threads', '1', output, timeout=180)
    return [('Imagem', output)], []


def _zip(caminho, diretorio):
    supported = t.TEXT_EXTENSIONS | t.IMAGE_EXTENSIONS | t.OFFICE_EXTENSIONS | {'.pdf'}
    saida, avisos = [], []
    total = count = 0
    with ZipFile(caminho) as arquivo:
        for i, member in enumerate(arquivo.infolist()):
            if member.is_dir():
                continue
            suffix = PurePosixPath(member.filename).suffix.lower()
            if suffix not in supported or count >= 128 or member.file_size > 32*1024*1024 or total + member.file_size > 256*1024*1024:
                continue
            count += 1
            # Count all selected members, including non-images, as in archive_content.
            if suffix not in t.IMAGE_EXTENSIONS and suffix != '.pdf':
                total += member.file_size
                continue
            try:
                with arquivo.open(member) as stream:
                    data = stream.read(32*1024*1024 + 1)
                total += len(data)
                if len(data) > 32*1024*1024:
                    avisos.append(f'Membro {i}: tamanho excedido.')
                    continue
                name = ' '.join(PurePosixPath(member.filename).name.split())
                if suffix == '.pdf':
                    pdf = diretorio / f'item-{i}.pdf'
                    pdf.write_bytes(data)
                    pasta = diretorio / f'pdf-{i}'
                    pasta.mkdir()
                    pages, warnings = _pdf(pdf, pasta)
                    saida.extend((f'{name} :: {label}', image) for label, image in pages)
                    avisos.extend(f'{name}: {warning}' for warning in warnings)
                    continue
                output = diretorio / f'item-{i}.png'
                from io import BytesIO
                _imagem(BytesIO(data), output)
                name = ' '.join(PurePosixPath(member.filename).name.split())
                saida.append((f'{name} :: membro {i}', output))
            except (OSError, RuntimeError, ValueError, NotImplementedError) as error:
                avisos.append(f'Membro {i}: {error}')
    return saida, avisos


def componentes(caminho: Path, metodo: str, mime: str, diretorio: Path):
    """Retorna (pares rótulo/caminho, avisos). O chamador mantém o diretório vivo."""
    caminho, diretorio = Path(caminho), Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)
    mime = (mime or '').split(';', 1)[0].strip().lower()
    ext = caminho.suffix.lower()
    if metodo == 'zip-conteudo' or ext == '.zip' or mime in t.ZIP_MIMES:
        return _zip(caminho, diretorio)
    if '+ocr' in metodo and (ext == '.pdf' or mime == 'application/pdf'):
        return _pdf(caminho, diretorio)
    # Signature overrides misleading GIF/PNG names and MIME.
    with caminho.open('rb') as stream:
        assinatura = stream.read(12)
    if assinatura.startswith(b'\x89PNG\r\n\x1a\n'):
        ext, mime = '.png', 'image/png'
    elif assinatura.startswith((b'GIF87a', b'GIF89a')):
        ext, mime = '.gif', 'image/gif'
        if caminho.suffix.lower() != '.gif':
            import shutil
            copia = diretorio / 'original.gif'
            shutil.copyfile(caminho, copia)
            caminho = copia
    if assinatura[4:8] == b'ftyp' and assinatura[8:12] in {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'mif1', b'msf1', b'avif', b'avis'}:
        ext, mime = '.heic', 'image/heic'
    if ext in t.HEIF_EXTENSIONS or mime in {'image/heic', 'image/heif', 'image/avif'}:
        return _heif(caminho, diretorio)
    if ext == '.webp' or mime == 'image/webp':
        saida = []
        with Image.open(caminho) as img:
            if img.format != 'WEBP':
                raise ValueError('Arquivo anunciado como WebP tem outro formato.')
            total = img.n_frames; count = min(16, total)
            for index in (i * (total - 1) // max(1, count - 1) for i in range(count)):
                img.seek(index)
                output = diretorio / f'webp-{index:03d}.png'
                frame = img.convert('RGBA'); fundo = Image.new('RGBA', frame.size, 'white')
                Image.alpha_composite(fundo, frame).convert('RGB').save(output)
                saida.append((f'Quadro {index+1}', output))
        return saida, []
    if ext in t.MEDIA_EXTENSIONS or mime.startswith(('audio/', 'video/')) or mime == 'image/gif':
        return _video(caminho, diretorio)
    if ext in t.IMAGE_EXTENSIONS or mime.startswith('image/'):
        with Image.open(caminho) as img:
            img.verify()
        with Image.open(caminho) as img:
            if img.format in {'PNG', 'JPEG'} and img.getexif().get(274, 1) == 1:
                return [('Imagem', caminho)], []
        output = diretorio / 'imagem.png'
        _imagem(caminho, output)
        return [('Imagem', output)], []
    return [], ['Formato sem componente visual reconhecido.']


def combinar(caminho, metodo, partes, original_texto):
    """partes é sequência de (rótulo, texto); preserva conteúdo não visual."""
    partes = [(str(rotulo), texto or '') for rotulo, texto in partes]
    original = original_texto or ''
    if not partes:
        return original
    if metodo == 'zip-conteudo':
        # Replace all visual sections of each name in ordinal order. Old OCR omits
        # empty members, so matching individual old sections is not reliable.
        grupos = {}
        demais = []
        for label, texto in partes:
            match = re.fullmatch(r'(.*) :: membro (\d+)', label)
            if match:
                grupos.setdefault(match.group(1), []).append((int(match.group(2)), texto))
            else:
                demais.append((label, texto))
        for nome, membros in grupos.items():
            marker = f'[{nome}]'
            pattern = re.compile(r'(?ms)^' + re.escape(marker) + r'\n.*?(?=\n\n\[[^\n]+\]\n|\Z)')
            found = list(pattern.finditer(original))
            novas = '\n\n'.join(marker + '\n' + texto for _, texto in sorted(membros) if texto.strip())
            if found:
                first = found[0].start()
                original = pattern.sub('', original)
                original = (original[:first].rstrip() + ('\n\n' if first and novas else '') + novas + ('\n\n' if novas and original[first:].strip() else '') + original[first:].lstrip()).strip()
            elif novas:
                original = (original + '\n\n' + novas).strip()
        partes = demais
        if not partes:
            return original
    if metodo == 'zip-conteudo' or '+ocr' in metodo:
        labels = [rotulo for rotulo, _ in partes]
        if len(labels) != len(set(labels)):
            raise ValueError('Rótulos duplicados não podem ser substituídos com segurança.')
        for label, texto in partes:
            if ' :: Página ' in label and metodo == 'zip-conteudo':
                membro, pagina = label.split(' :: ', 1)
                member_marker = f'[{membro}]'
                # Restrict edits to this member up to the next non-page member.
                member_pattern = re.compile(r'(?ms)^' + re.escape(member_marker) + r'\n.*?(?=\n\n\[(?!Página \d+\])[^\n]+\]\n|\Z)')
                matches = list(member_pattern.finditer(original))
                if len(matches) > 1:
                    raise ValueError(f'Membro ambíguo: {membro}')
                trecho = matches[0].group() if matches else member_marker
                page_marker = f'[{pagina}]'
                page_pattern = re.compile(r'(?ms)^' + re.escape(page_marker) + r'\n.*?(?=\n\n\[Página \d+\]\n|\Z)')
                replacement = page_marker + '\n' + texto
                trecho = page_pattern.sub(lambda _: replacement, trecho, count=1) if page_pattern.search(trecho) else trecho + '\n\n' + replacement
                original = member_pattern.sub(lambda _: trecho, original, count=1) if matches else (original + '\n\n' + trecho).strip()
                continue
            marker = f'[{label}]'
            pattern = re.compile(r'(?m)^' + re.escape(marker) + r'\n.*?(?=\n\n\[[^\n]+\]\n|\Z)', re.S)
            found = list(pattern.finditer(original))
            if len(found) > 1:
                raise ValueError(f'Rótulo ambíguo: {label}')
            replacement = marker + '\n' + texto
            original = pattern.sub(lambda _: replacement, original, count=1) if found else (original + '\n\n' + replacement).strip()
        return original
    if 'quadros' in metodo or 'whisper' in metodo or 'faster-whisper' in metodo or metodo == 'ffprobe':
        vistos = set()
        unicos = []
        for r, x in partes:
            if x.strip() and x not in vistos:
                vistos.add(x)
                unicos.append(f'[{r}]\n{x}')
        visual = '[Texto nos quadros]\n' + '\n\n'.join(unicos) if unicos else ''
        pattern = re.compile(r'(?ms)^\[Texto nos quadros\]\n.*\Z')
        return (pattern.sub(lambda _: visual, original) if pattern.search(original) else (original + '\n\n' + visual)).strip()
    if len(partes) == 1:
        return partes[0][1]
    vistos = set()
    unicos = []
    for r, x in partes:
        if x.strip() and x not in vistos:
            vistos.add(x)
            unicos.append(f'[{r}]\n{x}')
    return '\n\n'.join(unicos)
