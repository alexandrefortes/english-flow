"""Baixa a coleta pública da Doist e do Zulip para dados/."""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


PASTA = Path(__file__).resolve().parent


DOIST = (
    (
        "doist-pedir-atualizacao",
        "https://async.twist.com/when-to-take-real-time-meetings-async/#moving-work-forward",
        "https://storage.ghost.io/c/3d/0b/3d0b3605-e62c-48fe-982e-7efe1e14e187/"
        "content/images/2023/05/blog_meetings-to-twist_02_resize-1.png",
    ),
    (
        "doist-dar-feedback",
        "https://www.todoist.com/inspiration/remote-team-communication-tools#google-docs",
        "https://images.ctfassets.net/dm4oa8qtogq0/1b65773968da334a4bcf34c948e2752c4b678927/"
        "0720fec9da6d59440655a8a6badba02b/Providing_feedback_on_a_draft_of_this_blog_post_in_Google_Docs",
    ),
    (
        "doist-combinar-prazo",
        "https://www.todoist.com/inspiration/remote-team-communication-tools#todoist",
        "https://images.ctfassets.net/dm4oa8qtogq0/0ccfffeb3af5cf9ce76f132fc6aba57996bf5749/"
        "b3c1ef2df4ebbfdc393a67dc07d000eb/Discussing_the_featured_image_for_this_blog_post_in_Todoist_comments",
    ),
)

ZULIP = (
    (
        "zulip-dar-feedback",
        "https://chat.zulip.org/#narrow/channel/137-feedback/topic/design.20feedback/near/1950672",
        137,
        "design feedback",
        1950672,
        (1949967, 1950081, 1950259, 1950672, 1951464, 1952131),
    ),
    (
        "zulip-combinar-proximos-passos",
        "https://chat.zulip.org/#narrow/channel/378-api-design/topic/"
        "events.20for.20deactivated.20channels.20and.20groups/near/2499678",
        378,
        "events for deactivated channels and groups",
        2485189,
        (2484306, 2485188, 2499641, 2499643, 2499678, 2499908),
    ),
)


def baixar(url):
    with urlopen(url, timeout=30) as resposta:
        return resposta.read()


def extensao_imagem(dados):
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if dados.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if dados.startswith(b"RIFF") and dados[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("A fonte da Doist não retornou uma imagem PNG, JPEG ou WebP.")


def baixar_mensagens(canal, topico, ancora, ids):
    # Endpoint de leitura anônima para canais que o Zulip publica na web.
    filtro = [
        {"operator": "channels", "operand": "web-public"},
        {"operator": "channel", "operand": canal},
        {"operator": "topic", "operand": topico},
    ]
    consulta = urlencode({
        "anchor": ancora,
        "num_before": 7,
        "num_after": 7,
        "apply_markdown": "false",
        "narrow": json.dumps(filtro),
    })
    resposta = json.loads(baixar(f"https://chat.zulip.org/json/messages?{consulta}"))
    if resposta.get("result") != "success":
        raise ValueError(f"Zulip ({topico}): {resposta.get('msg', 'falha na consulta')}")

    por_id = {mensagem["id"]: mensagem for mensagem in resposta["messages"]}
    ausentes = set(ids) - por_id.keys()
    if ausentes:
        raise ValueError(f"Mensagens ausentes no Zulip ({topico}): {sorted(ausentes)}")

    mensagens = []
    for id_mensagem in ids:
        mensagem = por_id[id_mensagem]
        data = datetime.fromtimestamp(mensagem["timestamp"], timezone.utc)
        mensagens.append({
            "id": id_mensagem,
            "autor": mensagem["sender_full_name"],
            "data_utc": data.isoformat(),
            "texto": mensagem["content"],
        })
    return mensagens


def baixar_amostra():
    destino = PASTA / "dados"
    arquivos = {}
    fontes = ["# Conversas para estudo", "", "## Doist"]
    for nome, fonte, url in DOIST:
        imagem = baixar(url)
        arquivo = nome + extensao_imagem(imagem)
        arquivos[arquivo] = imagem
        fontes.append(f"- [{arquivo}]({arquivo}) · [Fonte original]({fonte})")

    fontes.extend(["", "## Zulip"])
    for nome, fonte, canal, topico, ancora, ids in ZULIP:
        mensagens = baixar_mensagens(canal, topico, ancora, ids)
        conversa = {"fonte": fonte, "topico": topico, "mensagens": mensagens}
        arquivos[f"{nome}.json"] = (json.dumps(conversa, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        blocos = [f"{topico}\nFonte: {fonte}"]
        for mensagem in mensagens:
            blocos.append(f"{mensagem['autor']} ({mensagem['data_utc']})\n{mensagem['texto']}")
        arquivos[f"{nome}.txt"] = ("\n\n".join(blocos) + "\n").encode("utf-8")
        fontes.append(f"- [{nome}.txt]({nome}.txt) · [{nome}.json]({nome}.json) · [Conversa original]({fonte})")

    arquivos["fontes.md"] = ("\n".join(fontes) + "\n").encode("utf-8")
    destino.mkdir(exist_ok=True)
    for nome, conteudo in arquivos.items():
        (destino / nome).write_bytes(conteudo)
    print(f"{len(arquivos)} arquivos salvos em {destino}")


def executar(script):
    print(f"\nExecutando {script}", flush=True)
    codigo = subprocess.run([sys.executable, "-B", "-u", str(PASTA / script)]).returncode
    if codigo in (130, -2, 0xC000013A, -1073741510):
        raise KeyboardInterrupt
    if codigo:
        print(f"{script} terminou com código {codigo}.", file=sys.stderr)
    return codigo


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--amostra", action="store_true", help="baixa somente os cinco exemplos da amostra original")
    args = cli.parse_args(argv)
    if args.amostra:
        baixar_amostra()
        return 0

    print(f"Destino da coleta: {PASTA / 'dados'}", flush=True)
    doist = executar("baixar_doist.py")
    zulip = executar("baixar_zulip.py")
    # Código 3 do Zulip indica JSONL exportado, com ressalvas no relatório de cobertura.
    anexos = executar("inventariar_anexos_zulip.py") if zulip in (0, 3) else 0
    if zulip == 3:
        print(f"Veja as ressalvas do Zulip em {PASTA / 'dados' / 'zulip' / 'coleta.json'}",
              file=sys.stderr)
    if doist or zulip not in (0, 3) or anexos:
        print("Há etapas pendentes. Rode o mesmo comando para retomar.", file=sys.stderr)
        return 1
    if zulip == 3:
        return 3

    print(f"Veja os arquivos e o leitor em {PASTA / 'README.md'}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nColeta interrompida. Rode o mesmo comando para retomar.", file=sys.stderr)
        sys.exit(130)
