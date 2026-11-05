"""Agregação temporal das detecções (RF05).

Mantém uma janela com os últimos N quadros e só considera "estável" a classe
que aparece em uma fração mínima desses quadros. Usa histerese para evitar que
um objeto entre e saia da lista a cada quadro.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from statistics import median

from .detector import Deteccao, iou_caixas

IOU_CONFLITO = 0.6  # caixas de classes diferentes sobre a mesma região


@dataclass
class _Quadro:
    contagem: Counter
    conf_max: dict[str, float]
    conflitos: set[tuple[str, str]]
    meta: dict[str, Deteccao]  # detecção de maior confiança de cada classe no quadro


@dataclass
class Estabilizador:
    janela: int = 8
    proporcao: float = 0.5
    _quadros: deque = field(default_factory=deque)
    _estaveis: set[str] = field(default_factory=set)

    def configurar(self, janela: int, proporcao: float) -> None:
        self.janela, self.proporcao = janela, proporcao
        while len(self._quadros) > self.janela:
            self._quadros.popleft()

    def limpar(self) -> None:
        self._quadros.clear()
        self._estaveis.clear()

    def adicionar(self, deteccoes: list[Deteccao]) -> dict:
        contagem: Counter = Counter(d.classe for d in deteccoes)
        conf_max: dict[str, float] = {}
        meta: dict[str, Deteccao] = {}
        for d in deteccoes:
            conf_max[d.classe] = max(conf_max.get(d.classe, 0.0), d.confianca)
            if d.classe not in meta or d.confianca > meta[d.classe].confianca:
                meta[d.classe] = d
        conflitos: set[tuple[str, str]] = set()
        for i, a in enumerate(deteccoes):
            for b in deteccoes[i + 1 :]:
                if (a.classe != b.classe and a.origem == b.origem == "detector"
                    and iou_caixas(a.caixa, b.caixa) >= IOU_CONFLITO):
                    conflitos.add(tuple(sorted((a.classe, b.classe))))
        self._quadros.append(_Quadro(contagem, conf_max, conflitos, meta))
        while len(self._quadros) > self.janela:
            self._quadros.popleft()
        return self.resumo()

    def resumo(self) -> dict:
        n = len(self._quadros)
        if n == 0:
            return {"objetos": [], "conflitos": [], "quadros_na_janela": 0}
        presencas: Counter = Counter()
        for q in self._quadros:
            presencas.update(q.contagem.keys())

        limiar_entrada = self.proporcao
        limiar_saida = self.proporcao * 0.6  # histerese
        novos_estaveis = set()
        for classe, vezes in presencas.items():
            frac = vezes / max(n, min(self.janela, 3))
            limiar = limiar_saida if classe in self._estaveis else limiar_entrada
            if frac >= limiar:
                novos_estaveis.add(classe)
        self._estaveis = novos_estaveis

        objetos = []
        for classe in self._estaveis:
            quadros_com = [q for q in self._quadros if classe in q.contagem]
            quantidade = max(1, round(median(q.contagem[classe] for q in quadros_com)))
            confianca = sum(q.conf_max[classe] for q in quadros_com) / len(quadros_com)
            dets = [q.meta[classe] for q in quadros_com]
            aprendidos = [d for d in dets if d.origem == "aprendido"]
            obj = {
                "classe": classe,
                "confianca": round(confianca, 2),
                "quantidade": int(quantidade),
                "frequencia": round(len(quadros_com) / n, 2),
                "origem": "aprendido" if len(aprendidos) * 2 >= len(dets) else "detector",
                "caixa": [round(v, 4) for v in dets[-1].caixa],  # última posição vista
            }
            if obj["origem"] == "aprendido":
                originais = Counter(d.classe_original for d in aprendidos if d.classe_original)
                obj["classe_original"] = originais.most_common(1)[0][0] if originais else None
            objetos.append(obj)
        objetos.sort(key=lambda o: o["confianca"], reverse=True)

        contagem_conflitos: Counter = Counter()
        for q in self._quadros:
            contagem_conflitos.update(q.conflitos)
        conflitos = [
            list(par)
            for par, vezes in contagem_conflitos.items()
            if vezes / n >= 0.3 and par[0] in self._estaveis and par[1] in self._estaveis
        ]
        return {"objetos": objetos, "conflitos": conflitos, "quadros_na_janela": n}
