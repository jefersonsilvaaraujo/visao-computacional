"""Configurações da aplicação.

Valores fixos vêm de variáveis de ambiente (docker-compose / .env).
Valores ajustáveis pelo responsável técnico ficam em `Ajustes` e são
persistidos em /app/dados/ajustes.json (volume local, sem dados de visitantes).
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
LLM_MODELO = os.getenv("LLM_MODELO", "llama3.2:3b")
MONITOR_PIN = os.getenv("MONITOR_PIN", "2026")
MODELO_DETECTOR = os.getenv("MODELO_DETECTOR", "/app/modelos/detector.onnx")
MODELO_EXTRATOR = os.getenv("MODELO_EXTRATOR", "/app/modelos/clip_visual.onnx")
DIR_DADOS = Path(os.getenv("DIR_DADOS", "/app/dados"))
DIR_LOGS = Path(os.getenv("DIR_LOGS", "/app/logs"))
BAIXAR_MODELO_AUTOMATICAMENTE = os.getenv("BAIXAR_MODELO_AUTOMATICAMENTE", "1") == "1"
THREADS_DETECTOR = int(os.getenv("THREADS_DETECTOR", "0"))  # 0 = automático


def threads_detector() -> int:
    """Núcleos de CPU do detector. Por padrão usa só uma parte da CPU, para não
    disputar todos os núcleos com a LLM quando ela também roda na CPU."""
    if THREADS_DETECTOR > 0:
        return THREADS_DETECTOR
    return max(1, min(4, (os.cpu_count() or 4) // 3))


LLM_THREADS = int(os.getenv("LLM_THREADS", "0"))  # 0 = automático


def nucleos_fisicos() -> int:
    """Núcleos físicos (sem hyperthreading), lidos de /proc/cpuinfo quando possível."""
    try:
        texto = Path("/proc/cpuinfo").read_text()
        por_soquete = [int(l.split(":")[1]) for l in texto.splitlines() if l.startswith("cpu cores")]
        soquetes = {l.split(":")[1].strip() for l in texto.splitlines() if l.startswith("physical id")}
        if por_soquete:
            return max(1, por_soquete[0] * max(1, len(soquetes)))
    except (OSError, ValueError):
        pass
    return os.cpu_count() or 4


def threads_llm() -> int:
    """Núcleos da LLM quando ela roda na CPU: os que o detector deixa livres,
    sem passar do número de núcleos físicos (medido: evita disputa e acelera)."""
    if LLM_THREADS > 0:
        return LLM_THREADS
    livres = (os.cpu_count() or 4) - threads_detector()
    return max(2, min(nucleos_fisicos(), livres))


def opcoes_onnx(threads: int):
    import onnxruntime as ort

    opcoes = ort.SessionOptions()
    opcoes.intra_op_num_threads = threads
    opcoes.inter_op_num_threads = 1
    # Sem "espera ativa": por padrão o ONNX Runtime mantém as threads girando
    # (ocupando CPU) entre inferências, o que atrasa muito a LLM na CPU.
    opcoes.add_session_config_entry("session.intra_op.allow_spinning", "0")
    opcoes.add_session_config_entry("session.inter_op.allow_spinning", "0")
    opcoes.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return opcoes


@dataclass
class Ajustes:
    versao_esquema: int = 2  # 2 = reconhecimento com CLIP (limiares diferentes da versão 1)
    confianca_minima: float = 0.50  # RF04: confiança mínima quando o nome vem do detector YOLO
    janela_quadros: int = 8  # RF05: quantos quadros consolidar
    proporcao_estavel: float = 0.5  # fração da janela em que o objeto precisa aparecer
    iou_nms: float = 0.45
    fps_max_deteccao: int = 12  # inferência intermitente (risco: GPU/CPU sobrecarregada)
    incluir_pessoas: bool = False  # por padrão a classe "pessoa" é ignorada (privacidade)
    max_palavras: int = 80  # RF07
    temperatura_llm: float = 0.2
    # Reconhecimento em duas etapas: o YOLO localiza, o CLIP dá o nome (base vocabulario.json)
    reconhecer_com_clip: bool = True
    confianca_nome: float = 0.35  # probabilidade mínima do CLIP para usar o nome da base
    limiar_candidatos: float = 0.05  # confiança mínima de uma caixa do YOLO para o CLIP analisar
    max_candidatos: int = 4  # caixas analisadas pelo CLIP por quadro
    intervalo_reconhecimento_ms: int = 500  # reaproveita o nome de uma caixa parada por este tempo
    # Aprendizado por exemplos (correções dos visitantes)
    aprendizado_ativo: bool = True
    exigir_aprovacao: bool = False  # se True, correções só valem após aprovação do monitor
    semelhanca_minima: float = 0.75  # similaridade do cosseno (CLIP) para usar o rótulo aprendido
    quadros_ensino: int = 12  # vetores coletados no ensino com vários ângulos
    # Enquanto a LLM escreve na CPU, a detecção desacelera para não disputar os núcleos.
    fps_durante_llm: int = 2

    def validar(self) -> "Ajustes":
        self.confianca_minima = min(max(float(self.confianca_minima), 0.05), 0.95)
        self.janela_quadros = min(max(int(self.janela_quadros), 1), 30)
        self.proporcao_estavel = min(max(float(self.proporcao_estavel), 0.1), 1.0)
        self.iou_nms = min(max(float(self.iou_nms), 0.1), 0.9)
        self.fps_max_deteccao = min(max(int(self.fps_max_deteccao), 1), 30)
        self.incluir_pessoas = bool(self.incluir_pessoas)
        self.max_palavras = min(max(int(self.max_palavras), 30), 150)
        self.temperatura_llm = min(max(float(self.temperatura_llm), 0.0), 1.0)
        self.aprendizado_ativo = bool(self.aprendizado_ativo)
        self.exigir_aprovacao = bool(self.exigir_aprovacao)
        self.semelhanca_minima = min(max(float(self.semelhanca_minima), 0.3), 0.99)
        self.versao_esquema = 2
        self.reconhecer_com_clip = bool(self.reconhecer_com_clip)
        self.confianca_nome = min(max(float(self.confianca_nome), 0.05), 0.95)
        self.limiar_candidatos = min(max(float(self.limiar_candidatos), 0.03), 0.9)
        self.max_candidatos = min(max(int(self.max_candidatos), 1), 8)
        self.intervalo_reconhecimento_ms = min(max(int(self.intervalo_reconhecimento_ms), 0), 3000)
        self.quadros_ensino = min(max(int(self.quadros_ensino), 0), 30)
        self.fps_durante_llm = min(max(int(self.fps_durante_llm), 1), 30)
        return self


class GerenciadorAjustes:
    def __init__(self, arquivo: Path):
        self._arquivo = arquivo
        self._lock = threading.Lock()
        self.atual = self._carregar()

    def _carregar(self) -> Ajustes:
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
            if dados.get("versao_esquema", 1) < 2:
                # Limiares calibrados para o extrator antigo (MobileNetV3) não valem para o CLIP.
                for chave in ("semelhanca_minima", "limiar_candidatos"):
                    dados.pop(chave, None)
            nomes = {f.name for f in fields(Ajustes)}
            return Ajustes(**{k: v for k, v in dados.items() if k in nomes}).validar()
        except Exception:
            return Ajustes()

    def atualizar(self, novos: dict) -> Ajustes:
        with self._lock:
            nomes = {f.name for f in fields(Ajustes)}
            base = asdict(self.atual)
            base.update({k: v for k, v in novos.items() if k in nomes})
            self.atual = Ajustes(**base).validar()
            try:
                self._arquivo.parent.mkdir(parents=True, exist_ok=True)
                self._arquivo.write_text(json.dumps(asdict(self.atual), indent=2), encoding="utf-8")
            except OSError:
                pass
            return self.atual

    def restaurar_padrao(self) -> Ajustes:
        return self.atualizar(asdict(Ajustes()))


ajustes = GerenciadorAjustes(DIR_DADOS / "ajustes.json")
