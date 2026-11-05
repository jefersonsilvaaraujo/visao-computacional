"""Aprendizado por exemplos (correções feitas pelos visitantes).

Como funciona (é um classificador k-vizinhos mais próximos, k-NN):
1. Quando o visitante corrige um rótulo, o recorte do objeto passa por uma rede
   pré-treinada (MobileNetV3) que o transforma em um vetor de 1280 números
   ("embedding"). São gerados alguns vetores com pequenas variações do recorte
   (espelhado, mais perto, mais claro…) para tolerar mudanças de posição e luz.
2. Só esses vetores e o rótulo são guardados. A imagem é descartada (RNF05).
3. Nas próximas demonstrações, cada objeto encontrado pelo detector também vira
   um vetor. Se ele for parecido o bastante (similaridade do cosseno) com um
   exemplo guardado, o rótulo aprendido substitui o rótulo do detector.

O detector YOLO não é re-treinado: o modelo original continua o mesmo.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from .classes_pt import ROTULOS_PT

log = logging.getLogger("aprendizado")

NOME_EXTRATOR = "mobilenet_v3_large-imagenet1k_v2-1280"
TAMANHO = 224
_MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DESVIO = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Variações do recorte usadas ao aprender um exemplo.
AUMENTOS = [
    {},
    {"espelhar": True},
    {"escala": 0.9},
    {"escala": 1.2},
    {"desloc": 0.06},
    {"desloc": -0.06},
    {"brilho": 0.75},
    {"brilho": 1.25},
]
MAX_EXEMPLOS = 400  # correções guardadas (cada uma com len(AUMENTOS) vetores)


def recortar(quadro: np.ndarray, caixa, escala: float = 1.05, desloc: float = 0.0,
             brilho: float = 1.0, espelhar: bool = False) -> np.ndarray:
    """Recorta a caixa normalizada (x1, y1, x2, y2 em 0..1) do quadro BGR."""
    h, w = quadro.shape[:2]
    x1, y1, x2, y2 = caixa[0] * w, caixa[1] * h, caixa[2] * w, caixa[3] * h
    bw, bh = max(2.0, (x2 - x1) * escala), max(2.0, (y2 - y1) * escala)
    cx, cy = (x1 + x2) / 2 + desloc * (x2 - x1), (y1 + y2) / 2
    a, b = int(max(0, cx - bw / 2)), int(max(0, cy - bh / 2))
    c, d = int(min(w, cx + bw / 2)), int(min(h, cy + bh / 2))
    r = quadro[b:max(d, b + 2), a:max(c, a + 2)]
    if brilho != 1.0:
        r = np.clip(r.astype(np.float32) * brilho, 0, 255).astype(np.uint8)
    if espelhar:
        r = r[:, ::-1]
    return r


class Extrator:
    """Transforma recortes de imagem em vetores normalizados (embeddings)."""

    def __init__(self, caminho: str, threads: int = 2):
        self.erro: str | None = None
        self.sessao = None
        try:
            if not os.path.exists(caminho):
                raise FileNotFoundError(f"Extrator não encontrado em {caminho}")
            from .config import opcoes_onnx

            opcoes = opcoes_onnx(threads)
            self.sessao = ort.InferenceSession(caminho, sess_options=opcoes, providers=["CPUExecutionProvider"])
            self.entrada = self.sessao.get_inputs()[0].name
            self.extrair([np.zeros((64, 64, 3), np.uint8)])  # aquecimento
            log.info("Extrator de características carregado (%s)", NOME_EXTRATOR)
        except Exception as exc:  # pragma: no cover - depende do ambiente
            self.sessao = None
            self.erro = str(exc)
            log.error("Falha ao carregar o extrator: %s", exc)

    @property
    def pronto(self) -> bool:
        return self.sessao is not None

    def extrair(self, recortes: list[np.ndarray]) -> np.ndarray:
        lote = []
        for r in recortes:
            img = cv2.resize(r, (TAMANHO, TAMANHO), interpolation=cv2.INTER_AREA)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            lote.append(((img - _MEDIA) / _DESVIO).transpose(2, 0, 1))
        vetores = self.sessao.run(None, {self.entrada: np.stack(lote).astype(np.float32)})[0]
        normas = np.linalg.norm(vetores, axis=1, keepdims=True)
        return (vetores / np.maximum(normas, 1e-6)).astype(np.float32)

    def extrair_com_aumentos(self, quadro: np.ndarray, caixa) -> np.ndarray:
        return self.extrair([recortar(quadro, caixa, **a) for a in AUMENTOS])


@dataclass
class Exemplo:
    id: str
    rotulo: str
    classe_original: str | None
    criado_em: str
    aprovado: bool
    vezes_reconhecido: int = 0


class Memoria:
    """Exemplos aprendidos, persistidos em /app/dados (volume local)."""

    def __init__(self, diretorio: Path):
        self._dir = diretorio
        self._lock = threading.Lock()
        self.exemplos: dict[str, Exemplo] = {}
        self._vetores: dict[str, np.ndarray] = {}
        self._matriz = np.zeros((0, 1280), np.float32)
        self._donos: list[str] = []
        self._carregar()

    # ------------------------------------------------------------ persistência
    @property
    def _arq_json(self) -> Path:
        return self._dir / "aprendizado.json"

    @property
    def _arq_npz(self) -> Path:
        return self._dir / "aprendizado.npz"

    def _carregar(self) -> None:
        try:
            meta = json.loads(self._arq_json.read_text(encoding="utf-8"))
            if meta.get("extrator") != NOME_EXTRATOR:
                log.warning("Aprendizado salvo com outro extrator; ignorado.")
                return
            vetores = np.load(self._arq_npz)
            for e in meta.get("exemplos", []):
                if e["id"] in vetores.files:
                    self.exemplos[e["id"]] = Exemplo(**e)
                    self._vetores[e["id"]] = vetores[e["id"]].astype(np.float32)
            self._reconstruir()
            log.info("Aprendizado carregado: %d correções", len(self.exemplos))
        except FileNotFoundError:
            pass
        except Exception as exc:
            log.error("Não foi possível ler o aprendizado salvo: %s", exc)

    def _salvar(self) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp_npz = self._dir / "aprendizado.tmp.npz"
            np.savez(tmp_npz, **{k: v.astype(np.float16) for k, v in self._vetores.items()})
            os.replace(tmp_npz, self._arq_npz)
            tmp_json = self._dir / "aprendizado.tmp.json"
            tmp_json.write_text(json.dumps({"extrator": NOME_EXTRATOR,
                                            "exemplos": [asdict(e) for e in self.exemplos.values()]},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp_json, self._arq_json)
        except OSError as exc:
            log.error("Não foi possível salvar o aprendizado: %s", exc)

    def _reconstruir(self) -> None:
        ids = [i for i, e in self.exemplos.items() if e.aprovado]
        if ids:
            matriz = np.concatenate([self._vetores[i] for i in ids]).astype(np.float32)
            donos = [i for i in ids for _ in range(len(self._vetores[i]))]
        else:
            matriz, donos = np.zeros((0, 1280), np.float32), []
        self._matriz, self._donos = matriz, donos  # troca atômica para as threads de detecção

    # ------------------------------------------------------------ operações
    def adicionar(self, rotulo: str, classe_original: str | None, vetores: np.ndarray, aprovado: bool) -> Exemplo:
        with self._lock:
            if len(self.exemplos) >= MAX_EXEMPLOS:  # descarta a correção mais antiga
                antigo = next(iter(self.exemplos))
                self.exemplos.pop(antigo)
                self._vetores.pop(antigo, None)
            e = Exemplo(id="e" + secrets.token_hex(5), rotulo=rotulo, classe_original=classe_original,
                        criado_em=time.strftime("%Y-%m-%d %H:%M"), aprovado=aprovado)
            self.exemplos[e.id] = e
            self._vetores[e.id] = vetores.astype(np.float32)
            self._reconstruir()
            self._salvar()
            return e

    def aprovar(self, id_: str) -> bool:
        with self._lock:
            if id_ not in self.exemplos:
                return False
            self.exemplos[id_].aprovado = True
            self._reconstruir()
            self._salvar()
            return True

    def remover(self, id_: str) -> bool:
        with self._lock:
            if self.exemplos.pop(id_, None) is None:
                return False
            self._vetores.pop(id_, None)
            self._reconstruir()
            self._salvar()
            return True

    def remover_rotulo(self, rotulo: str) -> int:
        with self._lock:
            ids = [i for i, e in self.exemplos.items() if e.rotulo == rotulo]
            for i in ids:
                self.exemplos.pop(i)
                self._vetores.pop(i, None)
            self._reconstruir()
            self._salvar()
            return len(ids)

    def esquecer_tudo(self) -> None:
        with self._lock:
            self.exemplos.clear()
            self._vetores.clear()
            self._reconstruir()
            self._salvar()

    def buscar(self, consultas: np.ndarray) -> list[tuple[str | None, float, str | None]]:
        """Para cada vetor, retorna (rótulo mais próximo, similaridade, id do exemplo)."""
        matriz, donos = self._matriz, self._donos
        if len(donos) == 0 or len(consultas) == 0:
            return [(None, 0.0, None)] * len(consultas)
        sims = consultas @ matriz.T
        melhores = sims.argmax(axis=1)
        saida = []
        for q, j in enumerate(melhores):
            dono = donos[j]
            e = self.exemplos.get(dono)
            saida.append((e.rotulo if e else None, float(sims[q, j]), dono))
        return saida

    def registrar_reconhecimento(self, id_: str) -> None:
        e = self.exemplos.get(id_)
        if e:
            e.vezes_reconhecido += 1  # contador em memória; salvo na próxima alteração

    # ------------------------------------------------------------ consultas
    @property
    def tem_aprovados(self) -> bool:
        return len(self._donos) > 0

    def rotulos(self) -> set[str]:
        return {e.rotulo for e in self.exemplos.values()}

    def resumo(self) -> dict:
        aprovados = [e for e in self.exemplos.values() if e.aprovado]
        return {
            "objetos": len({e.rotulo for e in aprovados}),
            "correcoes": len(aprovados),
            "pendentes": sum(1 for e in self.exemplos.values() if not e.aprovado),
        }

    def listar(self) -> list[dict]:
        return [asdict(e) for e in sorted(self.exemplos.values(), key=lambda e: e.criado_em, reverse=True)]

    # ------------------------------------------------------------ exportar/importar
    def exportar(self) -> dict:
        with self._lock:
            return {
                "formato": "visao-computacional-aprendizado/1",
                "extrator": NOME_EXTRATOR,
                "exemplos": [
                    {**asdict(e), "vetores": base64.b64encode(self._vetores[e.id].astype(np.float16).tobytes()).decode()}
                    for e in self.exemplos.values()
                ],
            }

    def importar(self, dados: dict, validar_rotulo) -> int:
        if dados.get("extrator") != NOME_EXTRATOR:
            raise ValueError("Arquivo gerado com outro extrator de características.")
        n = 0
        with self._lock:
            for item in dados.get("exemplos", [])[:MAX_EXEMPLOS]:
                ok, rotulo = validar_rotulo(str(item.get("rotulo", "")))
                if not ok:
                    continue
                vet = np.frombuffer(base64.b64decode(item["vetores"]), dtype=np.float16).astype(np.float32)
                if vet.size == 0 or vet.size % 1280:
                    continue
                vet = vet.reshape(-1, 1280)
                vet /= np.maximum(np.linalg.norm(vet, axis=1, keepdims=True), 1e-6)
                id_ = "e" + secrets.token_hex(5)
                original = item.get("classe_original")
                original = original if original in ROTULOS_PT else None
                self.exemplos[id_] = Exemplo(id=id_, rotulo=rotulo, classe_original=original,
                                             criado_em=str(item.get("criado_em", ""))[:16],
                                             aprovado=bool(item.get("aprovado", True)))
                self._vetores[id_] = vet
                n += 1
            self._reconstruir()
            self._salvar()
        return n
