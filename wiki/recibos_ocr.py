"""Lê uma transcrição visual vinculada aos bytes de um original."""

import json
from pathlib import Path
import re


def precisa_releitura(registro):
    return (registro.get("versao_revisor", 1) == 1
            and "Imagem dividida em recortes sobrepostos" in (registro.get("detalhe") or ""))


def ler_recibo(caminho: Path) -> dict:
    registro = json.loads(caminho.read_text(encoding="utf-8-sig"))
    if not isinstance(registro, dict) or not re.fullmatch(
        r"zulip-anexo-[0-9a-f]{32}|doist-[a-z0-9-]+", caminho.stem
    ) or registro.get("id") != caminho.stem:
        raise ValueError(f"Identificação de revisão inválida: {caminho.name}")
    if not re.fullmatch(r"[a-f0-9]{64}", str(registro.get("sha256"))) or (
        registro.get("metodo") != "revisao-visual-terra" or registro.get("manual") is not True
    ):
        raise ValueError(f"Procedência de revisão inválida: {caminho.name}")
    estado, texto = registro.get("estado"), registro.get("texto")
    if estado not in {"extraido", "parcial", "vazio"}:
        raise ValueError(f"Estado de revisão inválido: {caminho.name}")
    if estado == "vazio" and texto is not None:
        raise ValueError(f"Revisão vazia com texto: {caminho.name}")
    if estado != "vazio" and (not isinstance(texto, str) or not texto.strip()):
        raise ValueError(f"Transcrição inválida: {caminho.name}")
    detalhe = registro.get("detalhe") or ""
    if not isinstance(detalhe, str) or (estado == "parcial" and not detalhe.strip()):
        raise ValueError(f"Nota de revisão inválida: {caminho.name}")
    registro["detalhe"] = detalhe.strip() or "Transcrição visual conferida com o original."
    return registro
