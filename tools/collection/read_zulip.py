import argparse
import json
import sqlite3
from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tools import ROOT
from urllib.parse import parse_qs, urlencode, urlsplit


DIRECTORY = ROOT / "dados" / "zulip"
SOURCE_URL = "https://chat.zulip.org/"
PER_PAGE = 80

CSS = """
:root { color-scheme: light dark; font: 17px/1.55 'Atkinson Hyperlegible Next', system-ui, sans-serif }
body { max-width: 62rem; margin: 3rem auto; padding: 0 1.2rem }
nav, footer { padding: .55rem 0 }
h1 { line-height: 1.1; margin: 1.5rem 0 .6rem; overflow-wrap: anywhere }
a { color: light-dark(#135640, #a0dec3); text-underline-offset: .18em }
ul { list-style: none; padding: 0 }
li { padding: .45rem 0; border-bottom: 1px solid light-dark(#d7ded8, #414944); overflow-wrap: anywhere }
small { color: light-dark(#43564b, #bac9bf) }
input { font: inherit; width: min(22rem, 95%); padding: .35rem }
button { font: inherit; margin: .3rem 0; padding: .35rem .65rem }
article { padding: 1.1rem 0; border-bottom: 1px solid light-dark(#d7ded8, #414944) }
article header { display: flex; flex-wrap: wrap; align-items: baseline; gap: .3rem .8rem }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; margin: .6rem 0 0 }
footer a + a { margin-left: 1.25rem }
"""


def quantidade(total, singular, plural):
    return f"{total:,}".replace(",", ".") + " " + (singular if total == 1 else plural)


def caminho(**campos):
    return escape("/?" + urlencode(campos), quote=True)


def topic_name(topico):
    return escape(topico) if topico else "(no topic)"


def channel_list(pasta):
    inventario = pasta / "canais.json"
    return json.loads(inventario.read_text(encoding="utf-8")) if inventario.is_file() else []


def indice(db, pasta):
    canais = {}
    for canal in channel_list(pasta):
        canais[canal["stream_id"]] = (canal["name"], 0, canal.get("is_archived"))

    fontes = db.execute(
        "SELECT stream_id, channel, count(*), max(id) FROM mensagens GROUP BY stream_id"
    )
    for stream_id, nome, total, _ in fontes:
        nome, _, arquivado = canais.get(stream_id, (nome, 0, False))
        canais[stream_id] = (nome, total, arquivado)

    linhas = []
    for stream_id, (nome, total, arquivado) in sorted(canais.items(), key=lambda canal: canal[1][0].casefold()):
        estado = " · archived" if arquivado else ""
        contagem = quantidade(total, "message", "messages")
        linhas.append(f'<li><a href="{caminho(canal=stream_id)}">{escape(nome)}</a> '
                      f'<small>{contagem}{estado}</small></li>')

    resumo = quantidade(sum(canal[1] for canal in canais.values()), "message", "messages")
    resumo += " in " + quantidade(len(canais), "channel", "channels")
    ultima = db.execute("SELECT found_oldest FROM paginas ORDER BY numero DESC LIMIT 1").fetchone()
    estado = "" if ultima and ultima[0] else " The local collection is incomplete."
    return "Zulip channels", "", f"<p>{resumo} in the local collection.{estado}</p><ul>{''.join(linhas)}</ul>"


def channel_page(db, pasta, stream_id, filtros):
    nome = next((canal["name"] for canal in channel_list(pasta) if canal["stream_id"] == stream_id), None)
    if nome is None:
        linha = db.execute(
            "SELECT channel FROM mensagens WHERE stream_id = ? ORDER BY id DESC LIMIT 1",
            (stream_id,),
        ).fetchone()
        if linha is None:
            raise LookupError("The local collection does not contain this channel.")
        nome = linha[0]

    trilha = '<a href="/">Channels</a>'
    if "topico" in filtros:
        trilha += f' › <a href="{caminho(canal=stream_id)}">{escape(nome)}</a>'
        topico = filtros["topico"][0]
        antes = int(filtros.get("antes", [str(2**63 - 1)])[0])
        corpo = topic_page(db, stream_id, topico, antes)
        return topico or "(no topic)", trilha, corpo

    termo = filtros.get("q", [""])[0]
    linhas = []
    for topico, total in db.execute(
        "SELECT topic, count(*) FROM mensagens WHERE stream_id = ? GROUP BY topic ORDER BY max(id) DESC",
        (stream_id,),
    ):
        if termo.casefold() in topico.casefold():
            linhas.append(f'<li><a href="{caminho(canal=stream_id, topico=topico)}">'
                          f'{topic_name(topico)}</a> <small>{quantidade(total, "message", "messages")}</small></li>')

    pesquisa = (
        '<form method="get" action="/">'
        f'<input type="hidden" name="canal" value="{stream_id}">'
        f'<label>Filter topics <input name="q" value="{escape(termo, quote=True)}"></label> '
        '<button>Filter</button></form>'
    )
    resultado = f"<ul>{''.join(linhas)}</ul>" if linhas else "<p>No topics found.</p>"
    return nome, trilha, pesquisa + resultado


def topic_page(db, stream_id, topico, antes):
    mensagens = db.execute(
        "SELECT id, sender_full_name, datetime_utc, content, url FROM mensagens "
        "WHERE stream_id = ? AND topic = ? AND id < ? ORDER BY id DESC LIMIT ?",
        (stream_id, topico, antes, PER_PAGE + 1),
    ).fetchall()
    corpo = []
    for id_mensagem, autor, data, texto, url in reversed(mensagens[:PER_PAGE]):
        original = f'<a href="{escape(url, quote=True)}">#{id_mensagem} on Zulip</a>' if url.startswith(SOURCE_URL) else ""
        corpo.append(f'<article><header><strong>{escape(autor)}</strong> '
                     f'<small>{escape(data)}</small> <small>{original}</small></header>'
                     f'<pre>{escape(texto)}</pre></article>')

    links = []
    if len(mensagens) > PER_PAGE:
        ancora = mensagens[PER_PAGE - 1][0]
        links.append(f'<a href="{caminho(canal=stream_id, topico=topico, antes=ancora)}">Older messages</a>')
    if antes != 2**63 - 1:
        links.append(f'<a href="{caminho(canal=stream_id, topico=topico)}">Newer messages</a>')
    if not corpo:
        corpo.append("<p>No messages found.</p>")
    return "".join(corpo) + f"<footer>{' '.join(links)}</footer>"


class CollectionReader(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/":
            self.send_error(404)
            return
        filtros = parse_qs(url.query, keep_blank_values=True)
        try:
            with closing(sqlite3.connect(self.server.banco, uri=True)) as db:
                if "canal" in filtros:
                    stream_id = int(filtros["canal"][0])
                    titulo, trilha, corpo = channel_page(db, self.server.pasta, stream_id, filtros)
                else:
                    titulo, trilha, corpo = indice(db, self.server.pasta)
        except (ValueError, OverflowError):
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        titulo = escape(titulo)
        pagina = (f'<!doctype html><html lang="en"><meta charset="utf-8">'
                  f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                  f'<title>{titulo}</title><style>{CSS}</style>'
                  f'<nav aria-label="Navigation">{trilha}</nav><main><h1>{titulo}</h1>{corpo}</main></html>')
        dados = pagina.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


def main():
    cli = argparse.ArgumentParser(description='Read the local Zulip collection by channel and topic.')
    cli.add_argument("--port", type=int, default=8765)
    cli.add_argument("--data", type=Path, default=DIRECTORY)
    argumentos = cli.parse_args()
    pasta = argumentos.dados.resolve()
    banco = pasta / "coleta.sqlite3"
    if not banco.is_file():
        cli.error(f'Collection missing at {banco}. Run python -m tools.collection.download_zulip first.')
    with ThreadingHTTPServer(("127.0.0.1", argumentos.porta), CollectionReader) as servidor:
        servidor.pasta = pasta
        servidor.banco = banco.as_uri() + "?mode=ro"
        print(f'Open http://127.0.0.1:{servidor.server_port}/ in your browser. Press Ctrl+C to stop.', flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    main()
