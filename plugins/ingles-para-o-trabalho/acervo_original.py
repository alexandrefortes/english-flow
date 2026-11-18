import json
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urlencode
from urllib.request import urlopen


MAX_DOWNLOAD = 32 * 1024 * 1024


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
        data = resposta.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("O arquivo supera o tamanho permitido para uma amostra.")
    return data


def extensao_imagem(dados):
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if dados.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if dados.startswith(b"RIFF") and dados[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("A fonte da Doist não retornou uma imagem PNG, JPEG ou WebP.")


def capture_extension(stream, size):
    if not 16 <= size <= MAX_DOWNLOAD:
        raise ValueError("Tamanho de captura inválido.")
    header = stream.read(24)
    extension = extensao_imagem(header)
    if extension == ".webp":
        if len(header) < 20 or int.from_bytes(header[4:8], "little") + 8 != size:
            raise ValueError("Captura WebP incompleta.")
    elif extension == ".png":
        stream.seek(-12, 2)
        if (len(header) < 24 or header[8:16] != b"\x00\x00\x00\x0dIHDR"
                or stream.read(12) != b"\x00\x00\x00\x00IEND\xaeB`\x82"):
            raise ValueError("Captura PNG incompleta.")
    else:
        stream.seek(-min(size, 64), 2)
        if not stream.read().rstrip(b"\x00").endswith(b"\xff\xd9"):
            raise ValueError("Captura JPEG incompleta.")
    return extension


def verified_image_extension(data):
    return capture_extension(BytesIO(data), len(data))


def baixar_mensagens(canal, topico, ancora, ids):
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
