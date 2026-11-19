import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError

from tools.collection.collect_sources import download, image_extension


from tools import DOIST_CATALOG as INVENTORY, ROOT as PROJECT_ROOT
DIRECTORY = PROJECT_ROOT / "dados" / "doist"


def write_file(caminho, dados):
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_bytes(dados)
    temporario.replace(caminho)


def download_with_retry(url):
    for tentativa in range(4):
        try:
            return download(url)
        except HTTPError as erro:
            if tentativa == 3 or erro.code not in {408, 429, 500, 502, 503, 504}:
                raise
            espera = erro.headers.get("Retry-After")
            if espera is None:
                segundos = 2 ** tentativa
            elif espera.isdecimal():
                segundos = int(espera)
            else:
                segundos = (parsedate_to_datetime(espera) - datetime.now(timezone.utc)).total_seconds()
        except (URLError, TimeoutError):
            if tentativa == 3:
                raise
            segundos = 2 ** tentativa
        time.sleep(max(0, segundos))


def valido(registro, item):
    if registro.get("estado") != "baixado" or registro.get("url_original") != item["url_original"]:
        return False
    caminho = DIRECTORY / registro["arquivo"]
    try:
        dados = caminho.read_bytes()
        return (len(dados) == registro["bytes"]
                and hashlib.sha256(dados).hexdigest() == registro["sha256"]
                and image_extension(dados) == caminho.suffix)
    except (OSError, ValueError):
        return False


def index_page(inventario, coleta):
    itens = inventario["itens"]
    elegiveis = [item for item in itens if item["estado"] == "elegível"]
    baixados = sum(valido(coleta.get(item["id"], {}), item) for item in elegiveis)
    falhas = sum(coleta.get(item["id"], {}).get("estado") == "erro" for item in elegiveis)
    paginas = {p["url"]: p for p in inventario["publicacoes"]}
    linhas = [
        '<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Doist | English Flow</title>',
        '<style>body{font:1rem/1.5 system-ui,sans-serif;color:#242424;background:#faf9f7;'
        'max-width:70rem;margin:auto;padding:1.25rem}h1,h2,h3{line-height:1.15}a{color:#8b2828}'
        'li+li{margin-top:.55rem}details{margin-top:1.4rem}summary{cursor:pointer}</style>',
        '<h1>Doist</h1>',
        f'<p>{baixados} of {len(elegiveis)} eligible images available in this directory. '
        f'{falhas} downloads returned an error.</p>',
        f'<p>{escape(inventario["escopo"])}</p>',
        f'<p>{escape(inventario["cobertura"])}</p>',
        '<p><a href="../../plugins/english-flow/doist-catalog.json">Source catalog (JSON)</a>' +
        (' · <a href="coleta.json">Download log</a>' if (DIRECTORY / "coleta.json").is_file() else '') + '</p>',
        '<h2>Verified examples</h2>',
    ]
    for publicacao in dict.fromkeys(item["publicacao"] for item in elegiveis):
        pagina = paginas[publicacao]
        linhas.append(f'<h3><a href="{escape(publicacao)}">{escape(pagina["titulo"])}</a></h3><ul>')
        for item in elegiveis:
            if item["publicacao"] != publicacao:
                continue
            registro = coleta.get(item["id"], {})
            if valido(registro, item):
                estado = f'<a href="{escape(registro["arquivo"])}">Open local image</a>'
            else:
                estado = escape(registro.get("erro", "Local image pending"))
            republicacao = item.get("republicacao_integral")
            link_republicacao = f' · <a href="{escape(republicacao)}">Republished text</a>' if republicacao else ''
            linhas.append(
                f'<li><strong>{escape(item["titulo"])}</strong> · {escape(item["equipe"])} · '
                f'{escape(item["secao"])}<br>{escape(item["evidencia"])}<br>{estado} · '
                f'<a href="{escape(item["url_original"])}">Captura original</a> · '
                f'<a href="{escape(item["url_secao"])}">Seção na publicação</a>{link_republicacao}</li>'
            )
        linhas.append('</ul>')
    linhas.append(f'<details><summary>{len(itens) - len(elegiveis)} itens sem download</summary><ul>')
    for item in itens:
        if item["estado"] != "elegível":
            linhas.append(f'<li><a href="{escape(item["url_original"])}">{escape(item["titulo"])}</a> '
                          f'· {escape(item["estado"])} · {escape(item["evidencia"])}</li>')
    linhas.append(f'</ul></details><details><summary>{len(paginas)} publications and references reviewed</summary><ul>')
    for url, p in paginas.items():
        motivo = f' · {escape(p["nota"])}' if p.get("nota") else ''
        linhas.append(f'<li><a href="{escape(url)}">{escape(p["titulo"])}</a> · {escape(p["estado"])}{motivo}</li>')
    linhas.append('</ul></details></html>')
    write_file(DIRECTORY / "index.html", "\n".join(linhas).encode("utf-8"))
    return baixados, len(elegiveis)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download the Doist images in the source catalog.')
    parser.add_argument("--limit", type=int, help="Maximum number of new downloads.")
    parser.add_argument("--verify", action="store_true", help="Verify local files offline.")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("Use zero or a positive value for --limit.")

    DIRECTORY.mkdir(parents=True, exist_ok=True)
    inventario = json.loads(INVENTORY.read_text(encoding="utf-8"))
    estado = DIRECTORY / "coleta.json"
    coleta = json.loads(estado.read_text(encoding="utf-8")) if estado.exists() else {}
    tentados = 0
    erros = 0
    for item in inventario["itens"]:
        if item["estado"] != "elegível":
            continue
        id_item = item["id"]
        registro = coleta.get(id_item, {})
        if valido(registro, item):
            continue
        if args.verify:
            if registro.get("estado") == "baixado":
                print(f"Missing or invalid file: {registro['arquivo']}")
                erros += 1
            continue
        if args.limit is not None and tentados >= args.limit:
            break
        tentados += 1
        registro = {"url_original": item["url_original"], "data_utc": datetime.now(timezone.utc).isoformat()}
        try:
            dados = download_with_retry(item["url_original"])
            caminho = Path("capturas") / (id_item + image_extension(dados))
            (DIRECTORY / caminho.parent).mkdir(exist_ok=True)
            write_file(DIRECTORY / caminho, dados)
            registro.update(estado="baixado", arquivo=caminho.as_posix(), bytes=len(dados),
                            sha256=hashlib.sha256(dados).hexdigest())
        except (OSError, ValueError) as erro:
            registro.update(estado="erro", erro=str(erro))
            erros += 1
        coleta[id_item] = registro
        write_file(estado, (json.dumps(coleta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"{id_item}: {registro['estado']}", flush=True)
    baixados, total = index_page(inventario, coleta)
    print(f'Verified {baixados} of {total} images. Attempted {tentados} new downloads.')
    return int(erros > 0)


if __name__ == "__main__":
    raise SystemExit(main())
