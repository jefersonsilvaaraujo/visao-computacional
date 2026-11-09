"""Detector de objetos YOLO (pesos pré-treinados exportados para ONNX).

A inferência roda com ONNX Runtime, sem dependência de internet (RF12).
Por padrão usa a CPU, deixando a GPU livre para a LLM (RNF04).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from .classes_pt import ID_PESSOA, ROTULOS_PT

log = logging.getLogger("detector")


@dataclass
class Deteccao:
    classe_id: int
    classe: str  # rótulo em português (RF15)
    confianca: float
    caixa: tuple[float, float, float, float]  # x1, y1, x2, y2 normalizados (0..1)
    origem: str = "detector"  # "detector" ou "aprendido" (exemplos ensinados por visitantes)
    classe_original: str | None = None  # rótulo do detector antes da correção aprendida
    confianca_detector: float | None = None
    semelhanca: float | None = None  # similaridade com o exemplo aprendido mais próximo
    rotulo_proximo: str | None = None
    nome_por: str = "yolo"  # quem deu o nome: "yolo" ou "clip" (base de objetos)
    classe_detector: str | None = None  # nome sugerido pelo YOLO quando o CLIP renomeou

    def como_dict(self) -> dict:
        d = {
            "classe": self.classe,
            "confianca": round(self.confianca, 3),
            "caixa": [round(v, 4) for v in self.caixa],
            "origem": self.origem,
            "nome_por": self.nome_por,
        }
        if self.origem == "aprendido":
            d["classe_original"] = self.classe_original
            d["confianca_detector"] = round(self.confianca_detector or 0, 3)
        return d


class Detector:
    def __init__(self, caminho_modelo: str, threads: int = 2):
        self.caminho_modelo = caminho_modelo
        self.erro: str | None = None
        self.sessao: ort.InferenceSession | None = None
        self.dispositivo = "indisponível"
        self._lock = threading.Lock()
        self._threads = threads
        self.carregar()

    def carregar(self) -> None:
        try:
            if not os.path.exists(self.caminho_modelo):
                raise FileNotFoundError(f"Pesos do detector não encontrados em {self.caminho_modelo}")
            from .config import opcoes_onnx

            opcoes = opcoes_onnx(self._threads)
            disponiveis = ort.get_available_providers()
            provedores = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in disponiveis]
            self.sessao = ort.InferenceSession(self.caminho_modelo, sess_options=opcoes, providers=provedores)
            entrada = self.sessao.get_inputs()[0]
            self.nome_entrada = entrada.name
            self.tamanho = int(entrada.shape[2]) if isinstance(entrada.shape[2], int) else 640
            usado = self.sessao.get_providers()[0]
            self.dispositivo = "GPU (CUDA)" if usado.startswith("CUDA") else "CPU"
            # Aquecimento: primeira inferência costuma ser mais lenta.
            self.detectar(np.zeros((480, 640, 3), dtype=np.uint8), 0.5, 0.45, True)
            self.erro = None
            log.info("Detector carregado (%s, %d threads, entrada %dx%d)", self.dispositivo, self._threads,
                     self.tamanho, self.tamanho)
        except Exception as exc:  # pragma: no cover - depende do ambiente
            self.sessao = None
            self.erro = str(exc)
            self.dispositivo = "indisponível"
            log.error("Falha ao carregar o detector: %s", exc)

    @property
    def pronto(self) -> bool:
        return self.sessao is not None

    def _preparar(self, quadro_bgr: np.ndarray):
        h, w = quadro_bgr.shape[:2]
        escala = min(self.tamanho / h, self.tamanho / w)
        nw, nh = int(round(w * escala)), int(round(h * escala))
        redim = cv2.resize(quadro_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        tela = np.full((self.tamanho, self.tamanho, 3), 114, dtype=np.uint8)
        dx, dy = (self.tamanho - nw) // 2, (self.tamanho - nh) // 2
        tela[dy : dy + nh, dx : dx + nw] = redim
        tensor = cv2.cvtColor(tela, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None])
        return tensor, escala, dx, dy, w, h

    def detectar(
        self, quadro_bgr: np.ndarray, confianca_minima: float, iou: float, incluir_pessoas: bool
    ) -> tuple[list[Deteccao], float]:
        """Retorna (detecções acima do limiar, tempo de inferência em ms)."""
        if self.sessao is None:
            raise RuntimeError(self.erro or "Detector indisponível")
        tensor, escala, dx, dy, w, h = self._preparar(quadro_bgr)
        inicio = time.perf_counter()
        with self._lock:
            saida = self.sessao.run(None, {self.nome_entrada: tensor})[0]
        duracao_ms = (time.perf_counter() - inicio) * 1000

        # Saída YOLOv8/YOLO11: (1, 4 + n_classes, n_ancoras)
        pred = saida[0].T
        pontuacoes = pred[:, 4:]
        ids = pontuacoes.argmax(axis=1)
        confs = pontuacoes[np.arange(len(ids)), ids]
        mascara = confs >= confianca_minima
        if not incluir_pessoas:
            mascara &= ids != ID_PESSOA
        if not mascara.any():
            return [], duracao_ms
        pred, ids, confs = pred[mascara], ids[mascara], confs[mascara]

        cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
        x1 = (cx - bw / 2 - dx) / escala
        y1 = (cy - bh / 2 - dy) / escala
        caixas_xywh = np.stack([x1, y1, bw / escala, bh / escala], axis=1)

        resultado: list[Deteccao] = []
        # NMS por classe: evita caixas duplicadas do mesmo objeto (RF05).
        for cid in np.unique(ids):
            sel = np.where(ids == cid)[0]
            manter = cv2.dnn.NMSBoxes(
                caixas_xywh[sel].tolist(), confs[sel].astype(float).tolist(), confianca_minima, iou
            )
            for k in np.array(manter).flatten():
                i = sel[int(k)]
                bx, by, bw_, bh_ = caixas_xywh[i]
                caixa = (
                    float(np.clip(bx / w, 0, 1)),
                    float(np.clip(by / h, 0, 1)),
                    float(np.clip((bx + bw_) / w, 0, 1)),
                    float(np.clip((by + bh_) / h, 0, 1)),
                )
                resultado.append(Deteccao(int(cid), ROTULOS_PT[int(cid)], float(confs[i]), caixa))
        resultado.sort(key=lambda d: d.confianca, reverse=True)
        return resultado, duracao_ms


def iou_caixas(a: tuple, b: tuple) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    uniao = area_a + area_b - inter
    return inter / uniao if uniao > 0 else 0.0


def nms_por_rotulo(deteccoes: list[Deteccao], iou: float) -> list[Deteccao]:
    """Remove duplicatas depois que rótulos aprendidos substituem os do detector.

    - caixas com o mesmo rótulo e muito sobrepostas viram uma só;
    - uma caixa aprendida "vence" caixas do detector sobre a mesma região."""
    ordem = sorted(deteccoes, key=lambda d: (d.origem == "aprendido", d.confianca), reverse=True)
    mantidas: list[Deteccao] = []
    for d in ordem:
        duplicada = False
        for m in mantidas:
            sobrep = iou_caixas(d.caixa, m.caixa)
            if (m.classe == d.classe and sobrep >= iou) or (m.origem == "aprendido" and d.origem != "aprendido" and sobrep >= 0.6):
                duplicada = True
                break
        if not duplicada:
            mantidas.append(d)
    return sorted(mantidas, key=lambda d: d.confianca, reverse=True)
