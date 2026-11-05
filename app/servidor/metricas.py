"""Métricas técnicas (RF17, CA10) e logs mínimos (RNF09).

Nenhum conteúdo de visitante (imagens, perguntas ou respostas) é registrado.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

SERIES = {
    "fps_deteccao": "FPS da detecção",
    "inferencia_ms": "Duração da inferência do detector (ms)",
    "aprendizado_ms": "Comparação com exemplos aprendidos (ms)",
    "llm_primeiro_token_ms": "LLM: tempo até a primeira palavra (ms)",
    "llm_total_ms": "LLM: tempo total da resposta (ms)",
}


class Metricas:
    def __init__(self, tamanho: int = 2000):
        self._lock = threading.Lock()
        self._dados = {k: deque(maxlen=tamanho) for k in SERIES}
        self.inicio = time.time()

    def registrar(self, serie: str, valor: float) -> None:
        with self._lock:
            self._dados[serie].append((time.time(), float(valor)))

    def limpar(self) -> None:
        with self._lock:
            for d in self._dados.values():
                d.clear()
            self.inicio = time.time()

    def resumo(self) -> dict:
        with self._lock:
            saida = {}
            for k, d in self._dados.items():
                valores = sorted(v for _, v in d)
                n = len(valores)
                if n == 0:
                    saida[k] = {"descricao": SERIES[k], "n": 0}
                    continue
                saida[k] = {
                    "descricao": SERIES[k],
                    "n": n,
                    "media": round(sum(valores) / n, 1),
                    "minimo": round(valores[0], 1),
                    "maximo": round(valores[-1], 1),
                    "p95": round(valores[min(n - 1, int(n * 0.95))], 1),
                    "ultimo": round(d[-1][1], 1),
                }
            return {"desde": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.inicio)), "series": saida}

    def amostras(self) -> dict:
        with self._lock:
            return {k: [(round(t, 3), round(v, 2)) for t, v in d] for k, d in self._dados.items()}


metricas = Metricas()


def configurar_logs(diretorio: Path) -> Path | None:
    formato = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(formato)
    raiz.addHandler(console)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # evita registrar cada verificação de estado
    try:
        diretorio.mkdir(parents=True, exist_ok=True)
        arquivo = diretorio / "tecnico.log"
        h = RotatingFileHandler(arquivo, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        h.setFormatter(formato)
        raiz.addHandler(h)
        return arquivo
    except OSError:
        return None


def limpar_logs(diretorio: Path) -> int:
    removidos = 0
    for f in diretorio.glob("tecnico.log*"):
        try:
            if f.name == "tecnico.log":
                f.write_text("", encoding="utf-8")
            else:
                f.unlink()
            removidos += 1
        except OSError:
            pass
    return removidos
