import argparse
from array import array
import codecs
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from dataclasses import dataclass
from hashlib import file_digest
from html.parser import HTMLParser
from importlib.util import find_spec
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock
import time
from urllib.parse import unquote, urlsplit
import wave
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


from tools import ROOT
ATTACHMENTS = ROOT / "dados" / "zulip" / "anexos"
XML_LIMIT = 16 * 1024 * 1024
TEXT_LIMIT = 2_000_000
READABLE = "leitura-texto-original"
PDF_LOCK = Lock()
TEXT_EXTENSIONS = set(
    ".txt .md .rst .csv .tsv .json .log .yml .yaml .xml .css .js .ts .py .sh .bash .c .cpp .h .java "
    ".diff .patch .toml .ini .cfg .conf .sql .svg .html .htm .vtt .srt .jsonl .tex".split()
)
IMAGE_EXTENSIONS = set(".png .jpg .jpeg .webp .bmp .tif .tiff .ppm .pgm .pbm .jp2".split())
MEDIA_EXTENSIONS = set(
    ".gif .mp4 .mov .m4v .mkv .webm .avi .ogv .ogg .opus .mp3 .m4a .wav .aac .flac .mpeg .mpg "
    ".3gp .apng".split()
)
OFFICE_EXTENSIONS = set(".docx .docm .xlsx .xlsm .pptx .pptm .odt .ods .odp".split())
HEIF_EXTENSIONS = {".heic", ".heif", ".avif"}
ZIP_MIMES = {"application/zip", "application/x-zip-compressed"}
TEXT_MIME = set(
    "application/json application/xml application/yaml application/x-yaml application/javascript "
    "application/x-sh application/x-httpd-php application/xhtml+xml image/svg+xml".split()
)
MEDIA_FORMATS = (
    "matroska,webm,mov,mp4,m4a,3gp,3g2,mj2,gif,ogg,mp3,wav,flac,aac,avi,mpeg,mpegts,"
    "asf,m4v,flv,apng,image2,webp_pipe"
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS transcricoes (
    id TEXT PRIMARY KEY,
    sha256 TEXT,
    estado TEXT,
    texto TEXT,
    metodo TEXT,
    detalhe TEXT
);
"""
UPSERT = """
INSERT INTO transcricoes(id,sha256,estado,texto,metodo,detalhe) VALUES (?,?,?,?,?,?)
ON CONFLICT(id) DO UPDATE SET sha256=excluded.sha256, estado=excluded.estado,
    texto=excluded.texto, metodo=excluded.metodo, detalhe=excluded.detalhe
"""


@dataclass(frozen=True)
class Attachment:
    id: str
    sha256: str
    arquivo: str
    mime: str
    size: int
    url: str | None = None


@dataclass(frozen=True)
class Extraction:
    estado: str
    texto: str | None
    metodo: str
    detalhe: str | None = None


def extracted(text, method, detail=None, *, state="extraido"):
    if not text.strip():
        return Extraction("vazio", None, method, detail)
    if len(text) > TEXT_LIMIT:
        detail = join_details(detail, f"Texto limitado a {TEXT_LIMIT} caracteres.")
        state = "parcial"
    return Extraction(state, text[:TEXT_LIMIT], method, detail)


def join_details(*details):
    return " ".join(detail for detail in details if detail) or None


class ToolMissing(RuntimeError):
    pass


def run_tool(command, *args, timeout=90):
    executable = shutil.which(command)
    if executable is None:
        raise ToolMissing(f"{command} não está no PATH.")
    result = subprocess.run(
        [executable, *map(str, args)], capture_output=True, stdin=subprocess.DEVNULL,
        timeout=timeout, env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    if result.returncode:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{command} ({result.returncode}): {error[-400:]}")
    return result.stdout.decode("utf-8", errors="replace")


def ocr_image(path):
    return run_tool("tesseract", path, "stdout", "-l", "eng", "--psm", "11", timeout=60).strip()


def pdf_pages(path, directory):
    if find_spec("pymupdf") is not None:
        import pymupdf

        with PDF_LOCK, pymupdf.open(path) as document:
            if document.needs_pass:
                return Extraction("indisponivel", None, "pymupdf", "PDF protegido por senha.")
            pages = [page.get_text(sort=True) for page in document]

            def render(number, output):
                page = document[number - 1]
                scale = min(2.0, 2200 / max(1, page.rect.width, page.rect.height))
                page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(output)

            return finish_pdf(pages, "pymupdf", directory, render)

    text = run_tool("pdftotext", "-enc", "UTF-8", "-layout", path, "-")
    pages = text.split("\f")
    if len(pages) > 1 and not pages[-1].strip():
        pages.pop()
    if not any(page.strip() for page in pages):
        info = run_tool("pdfinfo", path)
        match = re.search(r"^Pages:\s*(\d+)", info, re.M)
        if match:
            pages = [""] * int(match[1])
    def render(number, output):
        run_tool("pdftoppm", "-f", number, "-l", number, "-r", "145", "-png",
                 "-singlefile", path, output.with_suffix(""))

    return finish_pdf(pages, "pdftotext", directory, render)


def finish_pdf(pages, method, directory, render):
    pending = [number for number, page in enumerate(pages, 1) if not page.strip()]
    if not pending:
        return extracted("\n\n".join(pages), method)
    details = []
    ocr_count = 0
    output = directory / "pagina.png"
    for number in pending[:20]:
        try:
            render(number, output)
            pages[number - 1] = ocr_image(output)
            ocr_count += 1
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            details.append(f"Página {number}: {error}")
            if isinstance(error, ToolMissing):
                break
    unseen = len(pending) - ocr_count
    if unseen:
        details.append(f"{unseen} de {len(pending)} páginas sem camada de texto ficaram sem OCR.")
    joined = "\n\n".join(f"[Página {number}]\n{page}"
                         for number, page in enumerate(pages, 1) if page.strip())
    if not joined and details:
        return Extraction("indisponivel", None, method + "+ocr", " ".join(details))
    return extracted(joined, method + "+ocr", " ".join(details) or None,
                     state="parcial" if unseen else "extraido")


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "head"}:
            self.hidden.append(tag)
        elif not self.hidden and tag in {"p", "li", "br", "tr", "h1", "h2", "h3", "div", "pre"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        elif not self.hidden and tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def decode_text(data, *, truncated=False):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return codecs.getincrementaldecoder("utf-16")(errors="replace").decode(data, final=not truncated)
    if b"\0" in data[:4096]:
        raise ValueError("Expected text but received binary data.")
    try:
        return codecs.getincrementaldecoder("utf-8-sig")().decode(data, final=not truncated)
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def extract_text(path, mime):
    with path.open("rb") as stream:
        data = stream.read(4 * TEXT_LIMIT + 1)
    truncated = len(data) > 4 * TEXT_LIMIT
    text = decode_text(data[:4 * TEXT_LIMIT], truncated=truncated)
    method = READABLE
    if path.suffix.lower() in {".html", ".htm"} or mime in {"text/html", "application/xhtml+xml"}:
        parser = PageText()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
        method = "html-texto-visivel"
    if path.suffix.lower() == ".svg" or mime == "image/svg+xml":
        tree = xml_tree(data)
        text = "\n".join("".join(node.itertext()) for node in tree.iter()
                         if local_name(node) in {"text", "title", "desc"})
        method = "svg-elementos-de-texto"
    return extracted(text, method, "Leitura parcial por tamanho." if truncated else None,
                     state="parcial" if truncated else "extraido")


def xml_tree(data):
    text = data.decode("utf-8-sig")
    if "\0" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise ValueError("Unsupported XML encoding or declaration.")
    return ET.fromstring(text)


def local_name(node):
    return node.tag.rsplit("}", 1)[-1]


def document_xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > XML_LIMIT:
        raise ValueError(f'XML part exceeds the read limit: {name}.')
    with archive.open(info) as stream:
        data = stream.read(XML_LIMIT + 1)
    if len(data) > XML_LIMIT:
        raise ValueError(f'XML part exceeds the read limit: {name}.')
    return xml_tree(data)


def paragraphs(tree, block_names, text_names):
    separators = {"tab": "\t", "br": "\n", "cr": "\n"}
    return "\n".join(
        "".join((child.text or "") if local_name(child) in text_names else separators.get(local_name(child), "")
                for child in block.iter())
        for block in tree.iter() if local_name(block) in block_names
    )


def sheet_text(archive, names):
    strings = []
    if "xl/sharedStrings.xml" in names:
        for item in document_xml(archive, "xl/sharedStrings.xml"):
            strings.append("".join(node.text or "" for node in item.iter() if local_name(node) == "t"))
    sheets = sorted(name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
    for name in sheets:
        yield "[" + PurePosixPath(name).stem + "]"
        for row in document_xml(archive, name).iter():
            if local_name(row) != "row":
                continue
            cells = []
            for cell in row:
                values = [node.text or "" for node in cell.iter() if local_name(node) in {"t", "v"}]
                value = "".join(values)
                if cell.get("t") == "s" and value.isdecimal():
                    index = int(value)
                    value = strings[index] if index < len(strings) else ""
                cells.append(value)
            if any(cells):
                yield "\t".join(cells)


def extract_office(path):
    output = []
    length = 0
    method = "office-xml"
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        if "word/document.xml" in names:
            selected = ["word/document.xml", "word/footnotes.xml", "word/endnotes.xml"]
            parts = (paragraphs(document_xml(archive, name), {"p"}, {"t"})
                     for name in selected if name in names)
        elif "xl/workbook.xml" in names:
            parts = sheet_text(archive, names)
        elif "ppt/presentation.xml" in names:
            slides = sorted(
                (name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"(\d+)\.xml$", name)[1]),
            )
            parts = (paragraphs(document_xml(archive, name), {"p"}, {"t"}) for name in slides)
        elif "content.xml" in names and path.suffix.lower() in {".odt", ".odp", ".ods"}:
            method = "opendocument-xml"
            tree = document_xml(archive, "content.xml")
            parts = ("".join(node.itertext()) for node in tree.iter() if local_name(node) in {"p", "h"})
        else:
            return Extraction("indisponivel", None, method, "Estrutura do documento desconhecida.")
        for part in parts:
            output.append(part)
            length += len(part) + 1
            if length > TEXT_LIMIT:
                break
    return extracted("\n".join(output), method)


class Speech:
    def __init__(self, model, device):
        self.model_path = model
        self.device = device
        self.lock = Lock()
        self.model = None

    def recognise(self, audio, directory):
        if self.model_path is None:
            raise ToolMissing("Modelo de fala local indisponível. Informe --model.")
        with self.lock:
            if self.model_path.is_file():
                run_tool("whisper", audio, "--model", self.model_path, "--device", self.device,
                         "--fp16", "True" if self.device == "cuda" else "False",
                         "--threads", "4", "--beam_size", "1", "--best_of", "1",
                         "--output_format", "txt", "--output_dir", directory, "--verbose", "False",
                         timeout=1800)
                output = directory / (audio.stem + ".txt")
                return output.read_text(encoding="utf-8").strip(), "whisper-local"
            if find_spec("faster_whisper") is None:
                raise ToolMissing("faster-whisper indisponível neste Python.")
            if self.model is None:
                from faster_whisper import WhisperModel

                self.model = WhisperModel(str(self.model_path), device=self.device,
                                          compute_type="float16" if self.device == "cuda" else "int8",
                                          local_files_only=True, cpu_threads=4)
            segments, _ = self.model.transcribe(str(audio), beam_size=1, vad_filter=True)
            return "\n".join(segment.text.strip() for segment in segments), "faster-whisper-local"


def ffinput(path):
    return ("-protocol_whitelist", "file,pipe", "-format_whitelist", MEDIA_FORMATS, "-i", path)


def has_audible_samples(audio):
    with wave.open(str(audio), "rb") as stream:
        while chunk := stream.readframes(32000):
            samples = array("h", chunk)
            if sys.byteorder != "little":
                samples.byteswap()
            if any(abs(sample) >= 64 for sample in samples):
                return True
    return False


def video_text(path, directory, duration):
    interval = max(duration / 16, 0.5)
    run_tool(
        "ffmpeg", "-nostdin", "-v", "error", "-threads", "1", *ffinput(path),
        "-map", "0:v:0", "-vf", f"fps=1/{interval}:start_time=0,scale='min(1600,iw)':-2",
        "-frames:v", "16", "-threads", "1", directory / "quadro-%03d.png", timeout=180,
    )
    images = sorted(directory.glob("quadro-*.png"))
    if not images:
        fallback = directory / "quadro-000.png"
        run_tool("ffmpeg", "-nostdin", "-v", "error", *ffinput(path),
                 "-map", "0:v:0", "-frames:v", "1", "-threads", "1", fallback, timeout=60)
        images = [fallback] if fallback.is_file() else []
    return ocr_frames(images), len(images)


def ocr_frames(images):
    scenes = []
    seen = set()
    for image in images:
        text = ocr_image(image)
        normalized = " ".join(text.casefold().split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            scenes.append(text)
    return "\n\n".join(scenes)


def extract_webp(path, directory, speech):
    if find_spec("PIL") is None:
        return extract_media(path, directory, speech)
    from PIL import Image

    images = []
    try:
        with Image.open(path) as webp:
            if webp.format != "WEBP":
                raise ValueError("The file format differs from its WebP label.")
            total = webp.n_frames
            count = min(16, total)
            frames = [index * (total - 1) // max(1, count - 1) for index in range(count)]
            for index in frames:
                webp.seek(index)
                frame = webp.convert("RGBA")
                background = Image.new("RGBA", frame.size, "white")
                frame = Image.alpha_composite(background, frame).convert("RGB")
                output = directory / f"webp-{index:03d}.png"
                frame.save(output)
                images.append(output)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        fallback = extract_media(path, directory, speech)
        return Extraction(fallback.estado, fallback.texto, fallback.metodo,
                          join_details(f"Conversão WebP no Pillow falhou: {error}.", fallback.detalhe))
    return extracted(ocr_frames(images), "pillow+tesseract-webp",
                     f"OCR de {count} de {total} quadros. WebP sem faixa de áudio.")


def extract_heif(path, directory):
    info = json.loads(run_tool("ffprobe", "-v", "error", "-show_stream_groups", "-of", "json", *ffinput(path)))
    groups = [group for group in info.get("stream_groups", [])
              if group.get("type") == "Tile Grid" and group.get("components")]
    output = directory / "heif.png"
    command = ["-nostdin", "-v", "error", "-threads", "1", *ffinput(path)]
    if groups:
        group = max(groups, key=lambda item: item["components"][0]["width"] * item["components"][0]["height"])
        canvas = group["components"][0]
        width, height = canvas["width"], canvas["height"]
        tiles = canvas["subcomponents"]
        if len(tiles) > 100 or not 0 < width * height <= 80_000_000:
            return Extraction("indisponivel", None, "ffmpeg-heif", "Grade de imagem excede os limites de OCR.")
        inputs = "".join(f"[0:{group['streams'][tile['stream_index']]['index']}]" for tile in tiles)
        offsets = "|".join(f"{tile['tile_horizontal_offset']}_{tile['tile_vertical_offset']}" for tile in tiles)
        graph = (inputs + f"xstack=inputs={len(tiles)}:layout={offsets}:fill=white,"
                 f"crop={width}:{height}:{canvas['horizontal_offset']}:{canvas['vertical_offset']}[picture]")
        command += ["-filter_complex_threads", "1", "-filter_complex", graph, "-map", "[picture]"]
    else:
        command += ["-map", "0:v:0"]
    run_tool("ffmpeg", *command, "-frames:v", "1", "-threads", "1", output, timeout=180)
    detail = f"Imagem reconstruída a partir de {len(tiles)} blocos." if groups else None
    return extracted(ocr_image(output), "ffmpeg+tesseract-heif", detail)


def archive_content(path, directory):
    supported = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | OFFICE_EXTENSIONS | {".pdf"}
    parts = []
    total_size = 0
    skipped = 0
    read_count = 0
    with ZipFile(path) as archive:
        for index, member in enumerate(archive.infolist()):
            if member.is_dir():
                continue
            suffix = PurePosixPath(member.filename).suffix.lower()
            if (suffix not in supported or read_count >= 128 or member.file_size > 32 * 1024 * 1024 or
                    total_size + member.file_size > 256 * 1024 * 1024):
                skipped += 1
                continue
            read_count += 1
            extracted_file = directory / f"item-{index}{suffix}"
            try:
                with archive.open(member) as stream:
                    data = stream.read(32 * 1024 * 1024 + 1)
                total_size += len(data)
                if len(data) > 32 * 1024 * 1024:
                    skipped += 1
                    continue
                extracted_file.write_bytes(data)
                if suffix in IMAGE_EXTENSIONS:
                    content = extracted(ocr_image(extracted_file), "tesseract")
                elif suffix in OFFICE_EXTENSIONS:
                    content = extract_office(extracted_file)
                elif suffix == ".pdf":
                    content = pdf_pages(extracted_file, directory)
                else:
                    content = extract_text(extracted_file, "")
            except (OSError, RuntimeError, ValueError, BadZipFile, ET.ParseError, subprocess.TimeoutExpired):
                skipped += 1
                continue
            finally:
                extracted_file.unlink(missing_ok=True)
            if content.estado not in {"extraido", "vazio"}:
                skipped += 1
            if content.texto:
                name = " ".join(PurePosixPath(member.filename).name.split())
                parts.append(f"[{name}]\n{content.texto}")
    detail = f"{read_count} membros processados. {skipped} ficaram sem extração completa."
    if not parts and skipped:
        return Extraction("indisponivel", None, "zip-conteudo", detail)
    return extracted("\n\n".join(parts), "zip-conteudo", detail, state="parcial" if skipped else "extraido")


def extract_media(path, directory, speech):
    info = json.loads(run_tool(
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type:stream_disposition=attached_pic",
        "-of", "json", *ffinput(path),
    ))
    streams = info.get("streams", [])
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    has_video = any(stream.get("codec_type") == "video" and
                    not stream.get("disposition", {}).get("attached_pic") for stream in streams)
    duration_text = str(info.get("format", {}).get("duration", "0"))
    duration = float(duration_text) if re.fullmatch(r"\d+(?:\.\d+)?", duration_text) else 0.0
    parts, methods, details = [], [], []
    partial = False
    speech_text = ""
    if has_audio and speech.model_path is not None:
        try:
            audio = directory / "fala.wav"
            run_tool("ffmpeg", "-nostdin", "-v", "error", *ffinput(path), "-map", "0:a:0",
                     "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", audio, timeout=180)
            if has_audible_samples(audio):
                speech_text, method = speech.recognise(audio, directory)
                methods.append(method)
                if speech_text:
                    parts.append("[Fala transcrita automaticamente]\n" + speech_text)
                else:
                    details.append("A transcrição automática não produziu fala.")
            else:
                details.append("Faixa de áudio silenciosa ou sem amostras acima do limiar.")
        except (OSError, RuntimeError, ValueError, EOFError, wave.Error, subprocess.TimeoutExpired) as error:
            partial = True
            details.append(f"Fala indisponível. {error}")
    elif has_audio:
        partial = True
        details.append("Faixa de áudio presente. Informe --model para transcrever a fala.")
    else:
        details.append("Arquivo sem faixa de áudio.")
    if has_video:
        try:
            text, sampled = video_text(path, directory, duration)
            methods.append("tesseract-quadros")
            details.append(f"OCR de {sampled} quadros amostrados.")
            if text:
                parts.append("[Texto nos quadros]\n" + text)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            partial = True
            details.append(f"OCR de quadros indisponível. {error}")
    method = "+".join(methods) or "ffprobe"
    detail = " ".join(details) or None
    if parts:
        state = "parcial" if partial else "transcrito" if speech_text else "extraido"
        return extracted("\n\n".join(parts), method, detail, state=state)
    if partial:
        return Extraction("indisponivel", None, method, detail)
    return Extraction("vazio" if has_audio else "sem_audio", None, method, detail)


def verified_file(directory, attachment):
    relative = Path(attachment.arquivo)
    if relative.is_absolute():
        raise ValueError("Use a relative attachment path.")
    path = (directory / relative).resolve(strict=True)
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("The attachment path is outside the collection.")
    if attachment.size is not None and path.stat().st_size != attachment.size:
        raise ValueError("The local file size differs from the record.")
    with path.open("rb") as stream:
        sha256 = file_digest(stream, "sha256").hexdigest()
    if sha256 != attachment.sha256:
        raise ValueError("The local SHA-256 differs from the record.")
    return path


def extract_attachment(directory, attachment, speech):
    try:
        path = verified_file(directory, attachment)
        mime = (attachment.mime or "").split(";", 1)[0].strip().lower()
        extension = path.suffix.lower()
        if attachment.url and extension in {".bin", ".zip", ".txt"}:
            name = unquote(urlsplit(attachment.url).path.rsplit("/", 1)[-1])
            original_extension = PurePosixPath(name).suffix.lower()
            if extension == ".bin" or original_extension in OFFICE_EXTENSIONS:
                extension = original_extension or extension
        if extension == ".gif" or mime == "image/gif" or mime.startswith(("audio/", "video/")):
            with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                return extract_media(path, Path(temporary), speech)
        if extension == ".webp" or mime == "image/webp":
            with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                return extract_webp(path, Path(temporary), speech)
        if extension in HEIF_EXTENSIONS or mime in {"image/heic", "image/heif", "image/avif"}:
            with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                return extract_heif(path, Path(temporary))
        if extension in IMAGE_EXTENSIONS or mime in {"image/png", "image/jpeg", "image/webp", "image/tiff", "image/bmp"}:
            return extracted(ocr_image(path), "tesseract-imagem")
        if extension in MEDIA_EXTENSIONS:
            with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                return extract_media(path, Path(temporary), speech)
        if extension == ".pdf" or mime == "application/pdf":
            with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                return pdf_pages(path, Path(temporary))
        if extension in OFFICE_EXTENSIONS:
            return extract_office(path)
        if extension == ".zip" or mime in ZIP_MIMES:
            with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                return archive_content(path, Path(temporary))
        if extension == ".rtf" and find_spec("striprtf") is not None:
            from striprtf.striprtf import rtf_to_text

            with path.open("rb") as stream:
                data = stream.read(XML_LIMIT + 1)
            if len(data) > XML_LIMIT:
                return Extraction("indisponivel", None, "striprtf", "RTF excede o limite de extração.")
            return extracted(rtf_to_text(data.decode("cp1252", errors="replace")), "striprtf")
        if extension in TEXT_EXTENSIONS or mime.startswith("text/") or mime in TEXT_MIME:
            return extract_text(path, mime)
        if mime in {"", "application/octet-stream"}:
            with path.open("rb") as handle:
                signature = handle.read(12)
            if signature[4:8] == b"ftyp" and signature[8:] in {b"isom", b"mp42", b"mp41", b"avc1", b"qt  ", b"M4A "}:
                with TemporaryDirectory(prefix="zulip-ocr-") as temporary:
                    return extract_media(path, Path(temporary), speech)
        return Extraction("indisponivel", None, "classificacao", f"Formato sem extrator: {mime or extension or 'desconhecido'}.")
    except ToolMissing as error:
        return Extraction("indisponivel", None, "dependencia", str(error))
    except (OSError, ValueError, RuntimeError, BadZipFile, ET.ParseError, subprocess.TimeoutExpired,
            KeyError, NotImplementedError) as error:
        return Extraction("erro", None, "validacao-ou-extracao", str(error))


def ready(directory, output, attempted, redo, limit):
    state = directory / "estado.sqlite3"
    if not state.is_file():
        return []
    with closing(sqlite3.connect(state.as_uri() + "?mode=ro", uri=True, timeout=5)) as source:
        if not source.execute("SELECT 1 FROM sqlite_master WHERE name='arquivos'").fetchone():
            return []
        rows = source.execute(
            "SELECT id,sha256,arquivo,mime,bytes,url FROM arquivos WHERE estado='baixado' "
            "AND id IS NOT NULL AND sha256 IS NOT NULL AND arquivo IS NOT NULL ORDER BY rowid"
        ).fetchall()
    cache = {row[0]: row[1:] for row in output.execute("SELECT id,sha256,estado,metodo FROM transcricoes")}
    selected = []
    for item in rows:
        attachment = Attachment(*item)
        previous_sha, previous_state, previous_method = cache.get(attachment.id, (None, None, None))
        different = previous_sha != attachment.sha256 or previous_method == "leitura-texto"
        retry = redo and previous_state in {"erro", "indisponivel", "parcial"}
        if (different or retry) and (attachment.id, attachment.sha256) not in attempted:
            selected.append(attachment)
            if len(selected) >= limit:
                break
    return selected


def process(directory, model, device, workers, limit, follow, wait, redo):
    destination = directory / "transcricoes.sqlite3"
    speech = Speech(model, device)
    counts = Counter()
    attempted = set()
    with closing(sqlite3.connect(destination, timeout=15)) as output, ThreadPoolExecutor(max_workers=workers) as pool:
        output.execute("PRAGMA journal_mode=WAL")
        output.execute(SCHEMA)
        output.commit()
        while limit is None or sum(counts.values()) < limit:
            batch_size = workers * 4
            if limit is not None:
                batch_size = min(batch_size, limit - sum(counts.values()))
            try:
                batch = ready(directory, output, attempted, redo, batch_size)
            except sqlite3.OperationalError as error:
                if not follow or not any(reason in str(error).lower() for reason in ("locked", "no such table")):
                    raise
                batch = []
            if not batch:
                if not follow:
                    break
                time.sleep(wait)
                continue
            pending = {pool.submit(extract_attachment, directory, item, speech): item for item in batch}
            for task in as_completed(pending):
                attachment = pending[task]
                result = task.result()
                with output:
                    output.execute(UPSERT, (
                        attachment.id, attachment.sha256, result.estado, result.texto, result.metodo,
                        result.detalhe[:2000] if result.detalhe else None,
                    ))
                counts[result.estado] += 1
                attempted.add((attachment.id, attachment.sha256))
            print(f'Processed {sum(counts.values())} items in this batch: {dict(sorted(counts.items()))}',
                  flush=True)
    return counts


def main():
    parser = argparse.ArgumentParser(description='Extract text from the local attachment files.')
    parser.add_argument("--attachments", type=Path, default=ATTACHMENTS, help="Directory with estado.sqlite3 and the original files.")
    parser.add_argument("--limit", type=int, help="Maximum items to process in this run.")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--watch", action="store_true", help="Wait for new downloads until Ctrl+C or the limit.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between checks in watch mode.")
    parser.add_argument("--model", type=Path, help="Local CTranslate2 model or Whisper .pt checkpoint.")
    parser.add_argument("--no-asr", action="store_true", help="Disable automatic speech recognition.")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--retry-errors", action="store_true", help="Retry failed, unavailable, and partial items.")
    args = parser.parse_args()
    if args.workers < 1 or (args.limit is not None and args.limit < 1) or args.interval <= 0:
        parser.error("Use positive values for the workers, limit, and interval.")
    if args.model and args.no_asr:
        parser.error("Set --model or --no-asr.")
    directory = args.attachments.expanduser().resolve()
    if not directory.is_dir():
        parser.error(f'Attachment directory missing: {directory}')
    model = args.model
    if model is None and not args.no_asr:
        installed = Path.home() / ".cache" / "whisper" / "small.pt"
        if installed.is_file() and shutil.which("whisper"):
            model = installed
    if model is not None:
        model = model.expanduser().resolve()
        if not ((model.is_file() and model.suffix.lower() == ".pt") or
                (model.is_dir() and all((model / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")))):
            parser.error("Supply an existing .pt file or a local directory with model.bin, config.json, and tokenizer.json.")
    try:
        counts = process(directory, model, args.device, args.workers, args.limit,
                         args.watch, args.interval, args.retry_errors)
    except KeyboardInterrupt:
        return 130
    print(f'Results from this run: {dict(sorted(counts.items()))}', flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
