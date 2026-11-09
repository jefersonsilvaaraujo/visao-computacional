"""Reconhecimento em duas etapas e ensino com vários ângulos.

1. O detector YOLO LOCALIZA as regiões com objetos (caixas), inclusive com
   confiança baixa: para objetos fora das 80 classes do COCO (caneta, marca-texto…)
   ele costuma achar a caixa certa, mas com o nome errado.
2. O CLIP transforma cada região em um vetor e:
   a) compara com os exemplos ensinados pelos visitantes (têm prioridade);
   b) senão, compara com os vetores de texto da base de objetos (vocabulario.json)
      e usa o nome mais provável, se a probabilidade passar do limiar;
   c) senão, mantém o nome do YOLO, se a confiança dele passar do limiar (RF04).

Para não rodar o CLIP em todo quadro, cada caixa que quase não se moveu reaproveita
o vetor calculado há pouco tempo (cache por sessão de câmera).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .aprendizado import recortar
from .classes_pt import ID_PESSOA
from .detector import Deteccao, iou_caixas, nms_por_rotulo

YOLO_MUITO_CONFIANTE = 0.80  # acima disso o nome do YOLO é mantido (classes do COCO)
IOU_MESMA_CAIXA = 0.6  # caixa "parada": reaproveita o vetor do CLIP
IOU_MESMO_OBJETO = 0.7  # caixas de nomes diferentes sobre o mesmo objeto: fica a mais confiável
SIM_ENSINO = 0.55  # semelhança mínima com o objeto ensinado para aceitar um novo ângulo
SIM_REPETIDO = 0.97  # ângulos quase idênticos aos já coletados são descartados
DURACAO_ENSINO_S = 8.0
INTERVALO_ENSINO_S = 0.25  # no máximo ~4 ângulos por segundo, para dar tempo de girar o objeto


@dataclass
class _Cache:
    caixa: tuple
    vetor: np.ndarray
    instante: float


@dataclass
class Ensino:
    id: str
    rotulo: str
    referencia: np.ndarray  # vetor médio do exemplo ensinado
    meta: int
    inicio: float = field(default_factory=time.monotonic)
    coletados: list = field(default_factory=list)
    ultimo: float = 0.0


class SessaoReconhecimento:
    """Estado de uma conexão de câmera: cache de vetores e ensino em andamento."""

    def __init__(self) -> None:
        self.cache: list[_Cache] = []
        self.ensino: Ensino | None = None

    def vetores(self, quadro: np.ndarray, deteccoes: list[Deteccao], extrator, intervalo_s: float,
                forcar: bool = False) -> tuple[np.ndarray, int]:
        """Vetores do CLIP para as caixas; reaproveita os de caixas paradas. Retorna (vetores, calculados)."""
        agora = time.monotonic()
        self.cache = [c for c in self.cache if agora - c.instante <= max(intervalo_s, 0.0) + 1.0]
        saida: list[np.ndarray | None] = []
        faltando = []
        for i, d in enumerate(deteccoes):
            achado = None
            if not forcar:
                for c in self.cache:
                    if agora - c.instante <= intervalo_s and iou_caixas(c.caixa, d.caixa) >= IOU_MESMA_CAIXA:
                        achado = c.vetor
                        break
            saida.append(achado)
            if achado is None:
                faltando.append(i)
        if faltando:
            novos = extrator.extrair([recortar(quadro, deteccoes[i].caixa) for i in faltando])
            for i, v in zip(faltando, novos):
                saida[i] = v
                self.cache.append(_Cache(deteccoes[i].caixa, v, agora))
        if not saida:
            return np.zeros((0, 1), np.float32), 0
        return np.stack(saida), len(faltando)

    # ------------------------------------------------------------ ensino em rajada
    def iniciar_ensino(self, id_: str, rotulo: str, vetores_exemplo: np.ndarray, meta: int) -> None:
        ref = vetores_exemplo.mean(axis=0)
        self.ensino = Ensino(id_, rotulo, ref / max(np.linalg.norm(ref), 1e-6), meta)

    def coletar(self, vetores: np.ndarray) -> None:
        """Escolhe, entre as caixas do quadro, a mais parecida com o objeto ensinado."""
        e = self.ensino
        agora = time.monotonic()
        if e is None or len(vetores) == 0 or agora - e.ultimo < INTERVALO_ENSINO_S:
            return
        sims = vetores @ e.referencia
        i = int(sims.argmax())
        if sims[i] < SIM_ENSINO:
            return
        if e.coletados and float((np.stack(e.coletados) @ vetores[i]).max()) >= SIM_REPETIDO:
            return
        e.coletados.append(vetores[i])
        e.ultimo = agora

    def ensino_terminou(self) -> bool:
        e = self.ensino
        return e is not None and (len(e.coletados) >= e.meta or time.monotonic() - e.inicio >= DURACAO_ENSINO_S)

    def estado_ensino(self) -> dict | None:
        e = self.ensino
        if e is None:
            return None
        return {"rotulo": e.rotulo, "coletados": len(e.coletados), "meta": e.meta,
                "restante_s": round(max(0.0, DURACAO_ENSINO_S - (time.monotonic() - e.inicio)), 1)}


def analisar(quadro: np.ndarray, aj, detector, extrator, memoria, sessao: SessaoReconhecimento,
             registrar_ms=None) -> tuple[list[Deteccao], float, dict | None]:
    """Detecta e dá nome aos objetos de um quadro. Retorna (detecções, ms do detector, diagnóstico)."""
    pronto = extrator is not None and extrator.pronto
    usar_clip = aj.reconhecer_com_clip and pronto
    usar_memoria = aj.aprendizado_ativo and memoria.tem_aprovados and pronto
    ensinando = sessao.ensino is not None and pronto
    if not (usar_clip or usar_memoria or ensinando):
        deteccoes, ms = detector.detectar(quadro, aj.confianca_minima, aj.iou_nms, aj.incluir_pessoas)
        return deteccoes, ms, None

    limiar = min(aj.confianca_minima, aj.limiar_candidatos, 0.05 if ensinando else 1.0)
    deteccoes, ms = detector.detectar(quadro, limiar, aj.iou_nms, aj.incluir_pessoas)
    pessoas = [d for d in deteccoes if d.classe_id == ID_PESSOA and d.confianca >= aj.confianca_minima]
    objetos = [d for d in deteccoes if d.classe_id != ID_PESSOA]
    candidatas = objetos[:aj.max_candidatos]
    restantes = [d for d in objetos[aj.max_candidatos:] if d.confianca >= aj.confianca_minima]

    diag = {"ms": 0.0, "recalculados": 0, "semelhanca_max": None, "rotulo_proximo": None}
    finais: list[Deteccao] = []
    if candidatas:
        inicio = time.perf_counter()
        vetores, calculados = sessao.vetores(quadro, candidatas, extrator, aj.intervalo_reconhecimento_ms / 1000,
                                             forcar=ensinando)
        diag["ms"], diag["recalculados"] = round((time.perf_counter() - inicio) * 1000, 1), calculados
        if registrar_ms and calculados:
            registrar_ms(diag["ms"])
        if ensinando:
            sessao.coletar(vetores)
        nomes = extrator.nomear(vetores) if usar_clip else [(None, 0.0)] * len(candidatas)
        buscas = memoria.buscar(vetores) if usar_memoria else [(None, 0.0, None)] * len(candidatas)
        for d, (nome, prob), (rotulo, sim, id_) in zip(candidatas, nomes, buscas):
            d.semelhanca, d.rotulo_proximo = sim, rotulo
            if rotulo is not None and (diag["semelhanca_max"] is None or sim > diag["semelhanca_max"]):
                diag["semelhanca_max"], diag["rotulo_proximo"] = round(sim, 3), rotulo
            if rotulo and sim >= aj.semelhanca_minima:  # exemplo ensinado tem prioridade
                d.classe_original, d.confianca_detector = d.classe, d.confianca
                d.classe, d.confianca, d.origem = rotulo, sim, "aprendido"
                memoria.registrar_reconhecimento(id_)
                finais.append(d)
            elif usar_clip and d.confianca < YOLO_MUITO_CONFIANTE and nome and prob >= aj.confianca_nome:
                # nunca exibe 100%: é uma estimativa do modelo, não uma certeza
                d.classe_detector, d.classe, d.confianca, d.nome_por = d.classe, nome, min(prob, 0.99), "clip"
                finais.append(d)
            elif d.confianca >= aj.confianca_minima:
                finais.append(d)
    finais += restantes + pessoas
    return _sem_sobreposicao(_juntar_partes(nms_por_rotulo(finais, aj.iou_nms))), ms, diag


def _contida(a: tuple, b: tuple) -> float:
    """Fração da caixa menor que está dentro da outra."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    menor = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / menor if menor > 0 else 0.0


def _vizinhas(a: tuple, b: tuple, folga: float = 0.03) -> bool:
    """Caixas que se tocam ou estão a menos de 3% da largura/altura da tela uma da outra."""
    return not (a[2] + folga < b[0] or b[2] + folga < a[0] or a[3] + folga < b[1] or b[3] + folga < a[1])


def _juntar_partes(deteccoes: list[Deteccao]) -> list[Deteccao]:
    """Pedaços do mesmo objeto (ex.: tampa e corpo de um marca-texto) com o mesmo nome viram uma caixa só:
    quando uma está quase toda dentro da outra, ou quando estão vizinhas e o nome veio do CLIP ou de
    um exemplo aprendido (caixas do YOLO, como dois livros lado a lado, continuam separadas)."""
    resultado: list[Deteccao] = []
    for d in sorted(deteccoes, key=lambda d: d.confianca, reverse=True):
        for m in resultado:
            if m.classe != d.classe:
                continue
            nomeados = {m.origem, d.origem} & {"aprendido"} or {m.nome_por, d.nome_por} & {"clip"}
            if _contida(m.caixa, d.caixa) >= 0.5 or (nomeados and _vizinhas(m.caixa, d.caixa)):
                m.caixa = (min(m.caixa[0], d.caixa[0]), min(m.caixa[1], d.caixa[1]),
                           max(m.caixa[2], d.caixa[2]), max(m.caixa[3], d.caixa[3]))
                break
        else:
            resultado.append(d)
    return resultado


def _sem_sobreposicao(deteccoes: list[Deteccao]) -> list[Deteccao]:
    """Duas caixas com nomes diferentes sobre o mesmo objeto: fica a de maior confiança."""
    mantidas: list[Deteccao] = []
    for d in sorted(deteccoes, key=lambda d: (d.origem == "aprendido", d.confianca), reverse=True):
        if all(iou_caixas(d.caixa, m.caixa) < IOU_MESMO_OBJETO for m in mantidas):
            mantidas.append(d)
    return sorted(mantidas, key=lambda d: d.confianca, reverse=True)
