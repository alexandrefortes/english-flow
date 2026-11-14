"""Baixa os exemplos públicos de comunicação de trabalho inventariados para a Doist."""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError

from baixar_conversas import baixar, extensao_imagem


RAIZ = Path(__file__).resolve().parent
INVENTARIO = RAIZ / "fontes" / "doist.json"
PASTA = RAIZ / "dados" / "doist"


def gravar(caminho, dados):
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_bytes(dados)
    temporario.replace(caminho)


def baixar_com_retentativa(url):
    for tentativa in range(4):
        try:
            return baixar(url)
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
    caminho = PASTA / registro["arquivo"]
    try:
        dados = caminho.read_bytes()
        return (len(dados) == registro["bytes"]
                and hashlib.sha256(dados).hexdigest() == registro["sha256"]
                and extensao_imagem(dados) == caminho.suffix)
    except (OSError, ValueError):
        return False


def indexar(inventario, coleta):
    itens = inventario["itens"]
    elegiveis = [item for item in itens if item["estado"] == "elegível"]
    baixados = sum(valido(coleta.get(item["id"], {}), item) for item in elegiveis)
    falhas = sum(coleta.get(item["id"], {}).get("estado") == "erro" for item in elegiveis)
    paginas = {p["url"]: p for p in inventario["publicacoes"]}
    linhas = [
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>Doist | Inglês para o Trabalho</title>',
        '<style>body{font:1rem/1.5 system-ui,sans-serif;color:#242424;background:#faf9f7;'
        'max-width:70rem;margin:auto;padding:1.25rem}h1,h2,h3{line-height:1.15}a{color:#8b2828}'
        'li+li{margin-top:.55rem}details{margin-top:1.4rem}summary{cursor:pointer}</style>',
        '<h1>Doist</h1>',
        f'<p>{baixados} de {len(elegiveis)} capturas elegíveis disponíveis nesta pasta. '
        f'{falhas} downloads com erro registrado.</p>',
        f'<p>{escape(inventario["escopo"])}</p>',
        f'<p>{escape(inventario["cobertura"])}</p>',
        '<p><a href="../../fontes/doist.json">Inventário JSON</a>' +
        (' · <a href="coleta.json">Registro do download</a>' if (PASTA / "coleta.json").is_file() else '') + '</p>',
        '<h2>Exemplos confirmados</h2>',
    ]
    for publicacao in dict.fromkeys(item["publicacao"] for item in elegiveis):
        pagina = paginas[publicacao]
        linhas.append(f'<h3><a href="{escape(publicacao)}">{escape(pagina["titulo"])}</a></h3><ul>')
        for item in elegiveis:
            if item["publicacao"] != publicacao:
                continue
            registro = coleta.get(item["id"], {})
            if valido(registro, item):
                estado = f'<a href="{escape(registro["arquivo"])}">Abrir captura local</a>'
            else:
                estado = escape(registro.get("erro", "Captura local pendente"))
            republicacao = item.get("republicacao_integral")
            link_republicacao = f' · <a href="{escape(republicacao)}">Texto integral republicado</a>' if republicacao else ''
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
    linhas.append(f'</ul></details><details><summary>{len(paginas)} publicações e referências examinadas</summary><ul>')
    for url, p in paginas.items():
        motivo = f' · {escape(p["nota"])}' if p.get("nota") else ''
        linhas.append(f'<li><a href="{escape(url)}">{escape(p["titulo"])}</a> · {escape(p["estado"])}{motivo}</li>')
    linhas.append('</ul></details></html>')
    gravar(PASTA / "index.html", "\n".join(linhas).encode("utf-8"))
    return baixados, len(elegiveis)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, help="Máximo de novos downloads nesta execução")
    parser.add_argument("--verificar", action="store_true", help="Confere os arquivos locais sem usar a rede")
    args = parser.parse_args(argv)
    if args.limite is not None and args.limite < 0:
        parser.error("--limite deve ser zero ou positivo")

    PASTA.mkdir(parents=True, exist_ok=True)
    inventario = json.loads(INVENTARIO.read_text(encoding="utf-8"))
    estado = PASTA / "coleta.json"
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
        if args.verificar:
            if registro.get("estado") == "baixado":
                print(f"Arquivo ausente ou inválido: {registro['arquivo']}")
                erros += 1
            continue
        if args.limite is not None and tentados >= args.limite:
            break
        tentados += 1
        registro = {"url_original": item["url_original"], "data_utc": datetime.now(timezone.utc).isoformat()}
        try:
            dados = baixar_com_retentativa(item["url_original"])
            caminho = Path("capturas") / (id_item + extensao_imagem(dados))
            (PASTA / caminho.parent).mkdir(exist_ok=True)
            gravar(PASTA / caminho, dados)
            registro.update(estado="baixado", arquivo=caminho.as_posix(), bytes=len(dados),
                            sha256=hashlib.sha256(dados).hexdigest())
        except (OSError, ValueError) as erro:
            registro.update(estado="erro", erro=str(erro))
            erros += 1
        coleta[id_item] = registro
        gravar(estado, (json.dumps(coleta, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"{id_item}: {registro['estado']}", flush=True)
    baixados, total = indexar(inventario, coleta)
    print(f"{baixados}/{total} capturas verificadas, {tentados} novos downloads tentados.")
    return int(erros > 0)


if __name__ == "__main__":
    raise SystemExit(main())
