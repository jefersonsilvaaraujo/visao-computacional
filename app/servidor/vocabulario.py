"""Base de objetos que o sistema sabe nomear (app/vocabulario.json).

Cada objeto tem um rótulo em português (exibido), termos em inglês (usados pelo
CLIP no build para gerar os vetores de texto) e uma descrição curta (usada
quando a IA de linguagem está indisponível, RF18).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .classes_pt import CLASSES_COCO

_CANDIDATOS = [
    Path(os.getenv("DIR_MODELOS", "/app/modelos")) / "vocabulario.json",  # cópia gerada no build
    Path(__file__).resolve().parent.parent / "vocabulario.json",  # fonte (testes / desenvolvimento)
]


def _carregar() -> list[dict]:
    for caminho in _CANDIDATOS:
        if caminho.exists():
            return json.loads(caminho.read_text(encoding="utf-8"))["objetos"]
    raise FileNotFoundError("vocabulario.json não encontrado")


OBJETOS: list[dict] = _carregar()
ROTULOS: list[str] = [o["rotulo"] for o in OBJETOS]  # mesma ordem dos vetores de texto do CLIP
DESCRICOES: dict[str, str] = {o["rotulo"]: o["descricao"] for o in OBJETOS}
# Classes do detector YOLO (inclui "pessoa", que não está na base do CLIP).
for _en, _pt, _desc in CLASSES_COCO:
    DESCRICOES.setdefault(_pt, _desc)
TODOS_ROTULOS: set[str] = set(DESCRICOES)
