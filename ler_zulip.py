"""Abre a coleta local por canal e tópico, com a biblioteca padrão do Python."""

import argparse
import json
import sqlite3
from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


PASTA = Path(__file__).resolve().parent / "dados" / "zulip"
ORIGEM = "https://chat.zulip.org/"
POR_PAGINA = 80

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


def nome_topico(topico):
    return escape(topico) if topico else "(sem tópico)"


def inventario_canais(pasta):
    inventario = pasta / "canais.json"
    return json.loads(inventario.read_text(encoding="utf-8")) if inventario.is_file() else []


def indice(db, pasta):
    canais = {}
    for canal in inventario_canais(pasta):
        canais[canal["stream_id"]] = (canal["name"], 0, canal.get("is_archived"))

    fontes = db.execute(
        "SELECT stream_id, channel, count(*), max(id) FROM mensagens GROUP BY stream_id"
    )
    for stream_id, nome, total, _ in fontes:
        nome, _, arquivado = canais.get(stream_id, (nome, 0, False))
        canais[stream_id] = (nome, total, arquivado)

    linhas = []
    for stream_id, (nome, total, arquivado) in sorted(canais.items(), key=lambda canal: canal[1][0].casefold()):
        estado = " · arquivado" if arquivado else ""
        contagem = quantidade(total, "mensagem", "mensagens")
        linhas.append(f'<li><a href="{caminho(canal=stream_id)}">{escape(nome)}</a> '
                      f'<small>{contagem}{estado}</small></li>')

    resumo = quantidade(sum(canal[1] for canal in canais.values()), "mensagem", "mensagens")
    resumo += " em " + quantidade(len(canais), "canal", "canais")
    ultima = db.execute("SELECT found_oldest FROM paginas ORDER BY numero DESC LIMIT 1").fetchone()
    estado = "" if ultima and ultima[0] else " A coleta local ainda é parcial."
    return "Canais do Zulip", "", f"<p>{resumo} na coleção local.{estado}</p><ul>{''.join(linhas)}</ul>"


def no_canal(db, pasta, stream_id, filtros):
    nome = next((canal["name"] for canal in inventario_canais(pasta) if canal["stream_id"] == stream_id), None)
    if nome is None:
        linha = db.execute(
            "SELECT channel FROM mensagens WHERE stream_id = ? ORDER BY id DESC LIMIT 1",
            (stream_id,),
        ).fetchone()
        if linha is None:
            raise LookupError("Canal ausente na coleção local.")
        nome = linha[0]

    trilha = '<a href="/">Canais</a>'
    if "topico" in filtros:
        trilha += f' › <a href="{caminho(canal=stream_id)}">{escape(nome)}</a>'
        topico = filtros["topico"][0]
        antes = int(filtros.get("antes", [str(2**63 - 1)])[0])
        corpo = no_topico(db, stream_id, topico, antes)
        return topico or "(sem tópico)", trilha, corpo

    termo = filtros.get("q", [""])[0]
    linhas = []
    for topico, total in db.execute(
        "SELECT topic, count(*) FROM mensagens WHERE stream_id = ? GROUP BY topic ORDER BY max(id) DESC",
        (stream_id,),
    ):
        if termo.casefold() in topico.casefold():
            linhas.append(f'<li><a href="{caminho(canal=stream_id, topico=topico)}">'
                          f'{nome_topico(topico)}</a> <small>{quantidade(total, "mensagem", "mensagens")}</small></li>')

    pesquisa = (
        '<form method="get" action="/">'
        f'<input type="hidden" name="canal" value="{stream_id}">'
        f'<label>Filtrar tópicos <input name="q" value="{escape(termo, quote=True)}"></label> '
        '<button>Filtrar</button></form>'
    )
    resultado = f"<ul>{''.join(linhas)}</ul>" if linhas else "<p>Nenhum tópico encontrado.</p>"
    return nome, trilha, pesquisa + resultado


def no_topico(db, stream_id, topico, antes):
    mensagens = db.execute(
        "SELECT id, sender_full_name, datetime_utc, content, url FROM mensagens "
        "WHERE stream_id = ? AND topic = ? AND id < ? ORDER BY id DESC LIMIT ?",
        (stream_id, topico, antes, POR_PAGINA + 1),
    ).fetchall()
    corpo = []
    for id_mensagem, autor, data, texto, url in reversed(mensagens[:POR_PAGINA]):
        original = f'<a href="{escape(url, quote=True)}">#{id_mensagem} no Zulip</a>' if url.startswith(ORIGEM) else ""
        corpo.append(f'<article><header><strong>{escape(autor)}</strong> '
                     f'<small>{escape(data)}</small> <small>{original}</small></header>'
                     f'<pre>{escape(texto)}</pre></article>')

    links = []
    if len(mensagens) > POR_PAGINA:
        ancora = mensagens[POR_PAGINA - 1][0]
        links.append(f'<a href="{caminho(canal=stream_id, topico=topico, antes=ancora)}">Mais antigas</a>')
    if antes != 2**63 - 1:
        links.append(f'<a href="{caminho(canal=stream_id, topico=topico)}">Mais recentes</a>')
    if not corpo:
        corpo.append("<p>Nenhuma mensagem encontrada.</p>")
    return "".join(corpo) + f"<footer>{' '.join(links)}</footer>"


class Leitor(BaseHTTPRequestHandler):
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
                    titulo, trilha, corpo = no_canal(db, self.server.pasta, stream_id, filtros)
                else:
                    titulo, trilha, corpo = indice(db, self.server.pasta)
        except (ValueError, OverflowError):
            self.send_error(400)
            return
        except LookupError:
            self.send_error(404)
            return
        titulo = escape(titulo)
        pagina = (f'<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
                  f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                  f'<title>{titulo}</title><style>{CSS}</style>'
                  f'<nav aria-label="Navegação">{trilha}</nav><main><h1>{titulo}</h1>{corpo}</main></html>')
        dados = pagina.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--porta", type=int, default=8765)
    cli.add_argument("--dados", type=Path, default=PASTA)
    argumentos = cli.parse_args()
    pasta = argumentos.dados.resolve()
    banco = pasta / "coleta.sqlite3"
    if not banco.is_file():
        cli.error(f"Coleta ausente em {banco}. Execute baixar_zulip.py primeiro.")
    with ThreadingHTTPServer(("127.0.0.1", argumentos.porta), Leitor) as servidor:
        servidor.pasta = pasta
        servidor.banco = banco.as_uri() + "?mode=ro"
        print(f"Abra http://127.0.0.1:{servidor.server_port}/ no navegador. Ctrl+C encerra.", flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    main()
