"""Servidor da demonstração: detecção via WebSocket, orquestração da LLM e interface web."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import AsyncIterator

import cv2
import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import config, guardrails
from .aprendizado import Extrator, Memoria, recortar
from .classes_pt import ID_PESSOA, ROTULOS_PT
from .detector import Deteccao, Detector, nms_por_rotulo
from .estabilizador import Estabilizador
from .llm import PREFIXO_JSON, PROMPT_SISTEMA, ServicoLLM
from .metricas import configurar_logs, limpar_logs, metricas

VERSAO = "1.1.0"
DIR_STATIC = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("servidor")

detector: Detector | None = None
extrator: Extrator | None = None
memoria = Memoria(config.DIR_DADOS)
llm: ServicoLLM | None = None
MAX_CANDIDATOS = 6  # recortes comparados com a memória a cada quadro


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    global detector, extrator, llm
    configurar_logs(config.DIR_LOGS)
    log.info("Iniciando servidor v%s", VERSAO)
    threads = config.threads_detector()
    detector = await asyncio.to_thread(Detector, config.MODELO_DETECTOR, threads)
    extrator = await asyncio.to_thread(Extrator, config.MODELO_EXTRATOR, threads)
    llm = ServicoLLM()
    llm.iniciar()
    yield
    await llm.encerrar()
    log.info("Servidor encerrado")


app = FastAPI(title="Visão Computacional com IA Local", version=VERSAO, lifespan=ciclo_de_vida,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resposta: Response = await call_next(request)
    resposta.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "connect-src 'self' ws: wss:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
    )
    resposta.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path == "/" or request.url.path.startswith("/static"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


# ----------------------------------------------------------------- utilidades
def exigir_pin(x_monitor_pin: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_monitor_pin.encode(), config.MONITOR_PIN.encode()):
        raise HTTPException(status_code=401, detail="PIN do monitor inválido.")


def linha(evento: dict) -> bytes:
    return (json.dumps(evento, ensure_ascii=False) + "\n").encode("utf-8")


# ----------------------------------------------------------------- modelos
class ObjetoCaptura(BaseModel):
    classe: str
    confianca: float = Field(ge=0, le=1)
    quantidade: int = Field(ge=1, le=50)
    origem: Literal["detector", "aprendido", "corrigido"] = "detector"
    classe_original: str | None = None

    @field_validator("classe")
    @classmethod
    def classe_conhecida(cls, v: str) -> str:
        # Aceita as classes do detector e os rótulos já validados e guardados na memória.
        if v not in ROTULOS_PT and v not in memoria.rotulos():
            raise ValueError("classe desconhecida")
        return v

    @field_validator("classe_original")
    @classmethod
    def original_conhecida(cls, v: str | None) -> str | None:
        return v if v in ROTULOS_PT else None

    def para_contrato(self) -> dict:
        d = {"classe": self.classe, "confianca": self.confianca, "quantidade": self.quantidade}
        if self.origem != "detector":
            d["origem"] = self.origem
            d["classe_original"] = self.classe_original
        return d


class Captura(BaseModel):
    captura_id: str | None = Field(default=None, max_length=40, pattern=r"^[a-z0-9\-]*$")
    objetos: list[ObjetoCaptura] = Field(default_factory=list, max_length=20)
    conflitos: list[list[str]] = Field(default_factory=list, max_length=10)
    confianca_minima: float | None = Field(default=None, ge=0, le=1)

    @field_validator("conflitos")
    @classmethod
    def conflitos_validos(cls, v: list[list[str]]) -> list[list[str]]:
        return [par[:2] for par in v if len(par) >= 2 and all(c in ROTULOS_PT for c in par[:2])]

    def contrato(self) -> dict:
        """Estrutura intermediária da seção 8 do documento de requisitos."""
        return {
            "captura_id": self.captura_id or "",
            "objetos": [o.para_contrato() for o in self.objetos],
            "sem_objetos": len(self.objetos) == 0,
            "conflitos": self.conflitos,
            "confianca_minima": self.confianca_minima
            if self.confianca_minima is not None
            else config.ajustes.atual.confianca_minima,
        }


class ParPergunta(BaseModel):
    pergunta: str = Field(max_length=guardrails.TAMANHO_MAX_PERGUNTA)
    resposta: str = Field(max_length=1200)


class PedidoPergunta(BaseModel):
    captura: Captura
    pergunta: str = Field(max_length=2000)
    historico: list[ParPergunta] = Field(default_factory=list, max_length=6)


# ----------------------------------------------------------------- páginas
app.mount("/static", StaticFiles(directory=DIR_STATIC), name="static")


@app.get("/", include_in_schema=False)
async def pagina_inicial():
    return FileResponse(DIR_STATIC / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(DIR_STATIC / "icone.svg", media_type="image/svg+xml")


# ----------------------------------------------------------------- estado (RF01)
@app.get("/api/status")
async def status():
    aj = config.ajustes.atual
    return {
        "versao": VERSAO,
        "detector": {
            "pronto": bool(detector and detector.pronto),
            "dispositivo": detector.dispositivo if detector else "—",
            "threads": config.threads_detector(),
            "threads_llm": config.threads_llm(),
            "erro": detector.erro if detector else "Carregando...",
        },
        "llm": {
            "estado": llm.estado if llm else "verificando",
            "pronta": bool(llm and llm.pronta),
            "mensagem": llm.mensagem if llm else "Inicializando...",
            "progresso": llm.progresso if llm else None,
            "modelo": config.LLM_MODELO,
            "dispositivo": llm.dispositivo if llm else "—",
        },
        "ajustes": {"fps_max_deteccao": aj.fps_max_deteccao, "confianca_minima": aj.confianca_minima},
        "aprendizado": {
            "ativo": aj.aprendizado_ativo and bool(extrator and extrator.pronto),
            "exigir_aprovacao": aj.exigir_aprovacao,
            "rotulos": sorted(memoria.rotulos()),
            **memoria.resumo(),
        },
    }


@app.get("/api/rotulos")
async def rotulos_conhecidos():
    """Sugestões para o campo de correção: classes do detector + rótulos aprendidos."""
    return {"rotulos": sorted({r for r in ROTULOS_PT if r != "pessoa"} | memoria.rotulos())}


@app.post("/api/reiniciar-componentes")
async def reiniciar_componentes():
    """RF13: tenta recuperar detector e LLM sem reiniciar a aplicação."""
    if detector and not detector.pronto:
        await asyncio.to_thread(detector.carregar)
    if llm:
        llm.verificar_agora()
    return await status()


# ----------------------------------------------------------------- monitor (RF17)
@app.post("/api/monitor/entrar", dependencies=[Depends(exigir_pin)])
async def monitor_entrar():
    return {"ok": True}


@app.get("/api/ajustes", dependencies=[Depends(exigir_pin)])
async def obter_ajustes():
    return asdict(config.ajustes.atual)


@app.post("/api/ajustes", dependencies=[Depends(exigir_pin)])
async def salvar_ajustes(novos: dict):
    atual = config.ajustes.atualizar(novos)
    log.info("Ajustes atualizados pelo monitor")
    return asdict(atual)


@app.post("/api/ajustes/restaurar", dependencies=[Depends(exigir_pin)])
async def restaurar_ajustes():
    return asdict(config.ajustes.restaurar_padrao())


@app.get("/api/metricas", dependencies=[Depends(exigir_pin)])
async def obter_metricas():
    return metricas.resumo()


@app.get("/api/metricas/exportar", dependencies=[Depends(exigir_pin)])
async def exportar_metricas():
    corpo = {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "versao": VERSAO,
        "detector": detector.dispositivo if detector else "—",
        "llm": {"modelo": config.LLM_MODELO, "dispositivo": llm.dispositivo if llm else "—"},
        "ajustes": asdict(config.ajustes.atual),
        "resumo": metricas.resumo(),
        "amostras": metricas.amostras(),
    }
    nome = time.strftime("metricas-%Y%m%d-%H%M%S.json")
    return JSONResponse(corpo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.post("/api/metricas/limpar", dependencies=[Depends(exigir_pin)])
async def zerar_metricas():
    metricas.limpar()
    return {"ok": True}


@app.post("/api/logs/limpar", dependencies=[Depends(exigir_pin)])
async def apagar_logs():
    n = limpar_logs(config.DIR_LOGS)
    log.info("Logs técnicos limpos pelo monitor")
    return {"ok": True, "arquivos": n}


# ----------------------------------------------------------------- detecção (RF02-RF05)
@app.websocket("/ws/deteccao")
async def ws_deteccao(ws: WebSocket):
    await ws.accept()
    estab = Estabilizador()
    instantes: deque = deque(maxlen=30)
    ultimo_registro_fps = 0.0
    ultimo_quadro = 0.0
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text"):
                try:
                    comando = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                if comando.get("acao") == "limpar":
                    estab.limpar()
                    await ws.send_json({"tipo": "limpo"})
                continue
            dados = msg.get("bytes")
            if not dados or len(dados) > 3_000_000:
                continue
            aj = config.ajustes.atual
            estab.configurar(aj.janela_quadros, aj.proporcao_estavel)
            if not detector or not detector.pronto:
                await ws.send_json({"tipo": "erro", "mensagem": "Detector indisponível: "
                                    + ((detector.erro if detector else None) or "carregando")})
                await asyncio.sleep(1)
                continue
            # Enquanto a LLM escreve na CPU, a detecção desacelera para não disputar os
            # núcleos com ela (o vídeo continua fluido: quem o exibe é o navegador).
            economia = bool(llm and llm.disputa_cpu)
            if economia:
                espera = ultimo_quadro + 1.0 / aj.fps_durante_llm - time.perf_counter()
                if espera > 0:
                    await asyncio.sleep(espera)
            ultimo_quadro = time.perf_counter()
            quadro = cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_COLOR)
            if quadro is None:
                await ws.send_json({"tipo": "erro", "mensagem": "Quadro inválido recebido da câmera."})
                continue
            try:
                deteccoes, ms, diag = await asyncio.to_thread(analisar_quadro, quadro, aj)
            except Exception as exc:
                log.error("Falha na inferência: %s", exc)
                await ws.send_json({"tipo": "erro", "mensagem": "Falha na inferência do detector."})
                continue
            del quadro  # RNF05: o quadro não é armazenado
            agora = time.perf_counter()
            instantes.append(agora)
            fps = (len(instantes) - 1) / (instantes[-1] - instantes[0]) if len(instantes) > 1 else 0.0
            metricas.registrar("inferencia_ms", ms)
            if agora - ultimo_registro_fps >= 1.0 and len(instantes) > 5:
                metricas.registrar("fps_deteccao", fps)
                ultimo_registro_fps = agora
            resumo = estab.adicionar(deteccoes)
            await ws.send_json({
                "tipo": "deteccao",
                "deteccoes": [d.como_dict() for d in deteccoes],
                "estavel": resumo,
                "inferencia_ms": round(ms, 1),
                "fps": round(fps, 1),
                "fps_max": aj.fps_max_deteccao,
                "confianca_minima": aj.confianca_minima,
                "dispositivo": detector.dispositivo,
                "aprendizado": diag,
                "economia": economia,
            })
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover
        log.error("Conexão de detecção encerrada com erro: %s", exc)


def analisar_quadro(quadro: np.ndarray, aj: config.Ajustes) -> tuple[list[Deteccao], float, dict | None]:
    """Detector YOLO + (opcional) comparação com os exemplos ensinados pelos visitantes."""
    usar_memoria = aj.aprendizado_ativo and memoria.tem_aprovados and extrator is not None and extrator.pronto
    if not usar_memoria:
        deteccoes, ms = detector.detectar(quadro, aj.confianca_minima, aj.iou_nms, aj.incluir_pessoas)
        return deteccoes, ms, None

    # Com exemplos aprendidos, caixas de baixa confiança também viram candidatas:
    # um objeto que o detector não conhece costuma aparecer com confiança baixa.
    limiar = min(aj.confianca_minima, aj.limiar_candidatos)
    deteccoes, ms = detector.detectar(quadro, limiar, aj.iou_nms, aj.incluir_pessoas)
    candidatas = [d for d in deteccoes if d.classe_id != ID_PESSOA][:MAX_CANDIDATOS]
    diag = {"semelhanca_max": None, "rotulo_proximo": None, "ms": 0.0}
    if candidatas:
        inicio = time.perf_counter()
        vetores = extrator.extrair([recortar(quadro, d.caixa) for d in candidatas])
        diag["ms"] = round((time.perf_counter() - inicio) * 1000, 1)
        metricas.registrar("aprendizado_ms", diag["ms"])
        for d, (rotulo, sim, id_) in zip(candidatas, memoria.buscar(vetores)):
            d.semelhanca, d.rotulo_proximo = sim, rotulo
            if diag["semelhanca_max"] is None or sim > diag["semelhanca_max"]:
                diag["semelhanca_max"], diag["rotulo_proximo"] = round(sim, 3), rotulo
            if rotulo and sim >= aj.semelhanca_minima:
                d.classe_original, d.confianca_detector = d.classe, d.confianca
                d.classe, d.confianca, d.origem = rotulo, sim, "aprendido"
                memoria.registrar_reconhecimento(id_)
    deteccoes = [d for d in deteccoes if d.origem == "aprendido" or d.confianca >= aj.confianca_minima]
    return nms_por_rotulo(deteccoes, aj.iou_nms), ms, diag


# ----------------------------------------------------------------- captura (RF06)
@app.post("/api/captura")
async def capturar(captura: Captura):
    captura.captura_id = "sessao-" + secrets.token_hex(3)  # identificador efêmero
    captura.confianca_minima = config.ajustes.atual.confianca_minima
    return captura.contrato()


# ----------------------------------------------------------------- LLM (RF07-RF10, RF18)
def _mensagens(contrato: dict, conteudo_usuario: str, historico: list[ParPergunta] | None = None) -> list[dict]:
    dados_llm = {
        "captura_id": contrato["captura_id"],
        "objetos": [
            {**o, "confianca_percentual": f"{round(o['confianca'] * 100)}%",
             "nivel_confianca": guardrails.nivel_confianca(o["confianca"])}
            for o in contrato["objetos"]
        ],
        "sem_objetos": contrato["sem_objetos"],
    }
    if contrato.get("conflitos"):
        dados_llm["classes_conflitantes"] = contrato["conflitos"]
    sistema = (
        PROMPT_SISTEMA
        + PREFIXO_JSON
        + json.dumps(dados_llm, ensure_ascii=False)
    )
    msgs = [{"role": "system", "content": sistema}]
    for par in (historico or [])[-3:]:
        msgs.append({"role": "user", "content": f"<pergunta>{par.pergunta}</pergunta>"})
        msgs.append({"role": "assistant", "content": par.resposta})
    msgs.append({"role": "user", "content": conteudo_usuario})
    return msgs


async def _gerar_com_llm(mensagens: list[dict], contrato: dict, max_palavras: int,
                         fallback: str, pergunta: str = "") -> AsyncIterator[bytes]:
    aj = config.ajustes.atual
    texto = ""
    try:
        async for parte in llm.gerar(mensagens, max_tokens=int(max_palavras * 2.2) + 20,
                                     temperatura=aj.temperatura_llm):
            if "token" in parte:
                texto += parte["token"]
                yield linha({"tipo": "token", "texto": parte["token"]})
            else:
                metricas.registrar("llm_total_ms", parte["tempo_total_ms"])
                metricas.registrar("llm_primeiro_token_ms", parte["tempo_primeiro_token_ms"])
                if parte["cortada"]:
                    yield linha({"tipo": "token", "texto": "…"})
                aviso = None
                extras = guardrails.classes_nao_capturadas(texto, contrato, pergunta)
                if extras:
                    presentes = ", ".join(o["classe"] for o in contrato["objetos"]) or "nenhuma"
                    aviso = (f"Atenção: a resposta citou {', '.join(extras)}, que não faz parte da captura. "
                             f"Considere apenas as classes detectadas: {presentes}.")
                log.info("LLM respondeu em %d ms (primeiro token %d ms)",
                         parte["tempo_total_ms"], parte["tempo_primeiro_token_ms"])
                yield linha({"tipo": "fim", "fonte": "llm", "aviso": aviso,
                             "tempo_total_ms": parte["tempo_total_ms"],
                             "tempo_primeiro_token_ms": parte["tempo_primeiro_token_ms"]})
    except Exception as exc:
        log.error("Falha na geração da LLM: %s", exc)
        llm.verificar_agora()
        yield linha({"tipo": "substituir", "texto": fallback})
        yield linha({"tipo": "fim", "fonte": "predefinida",
                     "aviso": "A IA local falhou durante a resposta; exibindo descrição pré-definida."})


def _resposta_fixa(texto: str, fonte: str = "regra", aviso: str | None = None) -> StreamingResponse:
    async def fluxo():
        yield linha({"tipo": "texto", "texto": texto})
        yield linha({"tipo": "fim", "fonte": fonte, "aviso": aviso})
    return StreamingResponse(fluxo(), media_type="application/x-ndjson")


AVISO_LLM_OFF = "IA local indisponível no momento: exibindo descrição pré-definida, sem geração de texto."


@app.post("/api/explicar")
async def explicar(captura: Captura):
    contrato = captura.contrato()
    aj = config.ajustes.atual
    observacao = guardrails.texto_observacao(contrato)

    async def fluxo():
        yield linha({"tipo": "observacao", "texto": observacao})
        if contrato["sem_objetos"]:
            yield linha({"tipo": "fim", "fonte": "regra", "aviso": None})
            return
        predefinida = guardrails.descricao_predefinida(contrato)
        if not llm or not llm.pronta:
            yield linha({"tipo": "texto", "texto": predefinida})
            yield linha({"tipo": "fim", "fonte": "predefinida", "aviso": AVISO_LLM_OFF})
            return
        orcamento = max(25, aj.max_palavras - guardrails.contar_palavras(observacao))
        classes = ", ".join(dict.fromkeys(o["classe"] for o in contrato["objetos"]))
        pedido = (
            f"Classes detectadas: {classes}.\n"
            f"Escreva de 1 a 3 frases curtas, com no máximo {orcamento} palavras no total, explicando "
            "para que esses tipos de objeto costumam servir (conhecimento geral). Não descreva a cena, não cite "
            "outros objetos e não mencione cor, marca, tamanho, material ou posição. Não repita as porcentagens. "
            "Comece diretamente pelo conteúdo, sem saudação e sem a expressão 'Em geral'."
        )
        async for b in _gerar_com_llm(_mensagens(contrato, pedido), contrato, orcamento, predefinida):
            yield b

    return StreamingResponse(fluxo(), media_type="application/x-ndjson")


@app.post("/api/perguntar")
async def perguntar(pedido: PedidoPergunta):
    contrato = pedido.captura.contrato()
    aj = config.ajustes.atual
    categoria, detalhe = guardrails.classificar_pergunta(pedido.pergunta)
    log.info("Pergunta recebida (categoria=%s)", categoria)  # o texto da pergunta não é registrado

    if categoria == "vazia":
        return _resposta_fixa("Digite uma pergunta ou escolha uma das sugestões.")
    if categoria == "longa":
        return _resposta_fixa(f"A pergunta é muito longa. Use até {guardrails.TAMANHO_MAX_PERGUNTA} caracteres.")
    if categoria == "injecao":
        return _resposta_fixa(guardrails.AVISO_SEGURANCA)
    if categoria == "pessoas":
        return _resposta_fixa(guardrails.AVISO_PESSOAS)
    if categoria == "detalhe":
        return _resposta_fixa(guardrails.resposta_detalhe(contrato, detalhe))
    if contrato["sem_objetos"]:
        return _resposta_fixa(
            "Nenhum objeto foi identificado com confiança suficiente nesta captura, então não tenho elementos "
            "para responder. Ajuste a posição do objeto ou a iluminação e clique em Capturar cena novamente."
        )
    observacao = guardrails.texto_observacao(contrato)
    predefinida = observacao + " " + guardrails.descricao_predefinida(contrato)
    if not llm or not llm.pronta:
        return _resposta_fixa(predefinida, fonte="predefinida", aviso=AVISO_LLM_OFF)

    conteudo = (
        f"<pergunta>{pedido.pergunta.strip()}</pergunta>\n\n"
        f"Responda à pergunta acima em no máximo {aj.max_palavras} palavras, usando apenas o JSON de detecções "
        "e conhecimento geral sobre as classes detectadas. Se mencionar o que foi visto, cite só as classes do "
        "JSON. Se não houver elementos para responder, diga isso."
    )
    msgs = _mensagens(contrato, conteudo, pedido.historico)
    return StreamingResponse(_gerar_com_llm(msgs, contrato, aj.max_palavras, predefinida, pedido.pergunta),
                             media_type="application/x-ndjson")


# ----------------------------------------------------------------- aprendizado por exemplos (RF19)
class PedidoCorrecao(BaseModel):
    imagem: str = Field(max_length=4_000_000)  # JPEG em base64 (fica só na memória)
    rotulo: str = Field(max_length=80)
    caixa: list[float] | None = Field(default=None, min_length=4, max_length=4)
    classe_original: str | None = None


def _decodificar_imagem(dados: str) -> np.ndarray:
    if "," in dados[:100]:
        dados = dados.split(",", 1)[1]  # remove o prefixo "data:image/jpeg;base64,"
    try:
        bruto = base64.b64decode(dados, validate=False)
    except Exception:
        raise HTTPException(400, "Imagem inválida.")
    quadro = cv2.imdecode(np.frombuffer(bruto, np.uint8), cv2.IMREAD_COLOR)
    if quadro is None:
        raise HTTPException(400, "Imagem inválida.")
    return quadro


@app.post("/api/aprendizado")
async def ensinar(pedido: PedidoCorrecao):
    """O visitante informa o nome correto de um objeto capturado."""
    aj = config.ajustes.atual
    if not aj.aprendizado_ativo:
        raise HTTPException(403, "O aprendizado por correções está desativado pelo monitor.")
    if not extrator or not extrator.pronto or not detector or not detector.pronto:
        raise HTTPException(503, "O módulo de aprendizado não está disponível no momento.")
    ok, rotulo = guardrails.validar_rotulo(pedido.rotulo)
    if not ok:
        raise HTTPException(422, rotulo)
    if pedido.classe_original == "pessoa":
        raise HTTPException(422, "A demonstração não aprende nada sobre pessoas, apenas sobre objetos.")
    original = pedido.classe_original if pedido.classe_original in ROTULOS_PT else None

    quadro = _decodificar_imagem(pedido.imagem)
    confianca_original = None
    caixa = pedido.caixa
    if caixa is None:
        # Objeto não detectado: procura a região mais provável com um limiar bem baixo.
        cands, _ = await asyncio.to_thread(detector.detectar, quadro, 0.05, aj.iou_nms, False)
        if not cands:
            raise HTTPException(422, "Não encontrei nenhum objeto na imagem para aprender. "
                                     "Aproxime o objeto da câmera, use um fundo liso e tente novamente.")
        caixa, confianca_original = list(cands[0].caixa), cands[0].confianca
        original = cands[0].classe
    x1, y1, x2, y2 = [min(max(float(v), 0.0), 1.0) for v in caixa]
    if x2 - x1 < 0.02 or y2 - y1 < 0.02:
        raise HTTPException(422, "A região do objeto é pequena demais para aprender.")

    vetores = await asyncio.to_thread(extrator.extrair_com_aumentos, quadro, (x1, y1, x2, y2))
    del quadro  # RNF05: a imagem é descartada; só os vetores numéricos são guardados
    pendente = aj.exigir_aprovacao
    novo = rotulo not in memoria.rotulos()
    exemplo = memoria.adicionar(rotulo, original, vetores, aprovado=not pendente)
    log.info("Correção registrada (%s, %s)", "rótulo novo" if novo else "rótulo existente",
             "pendente" if pendente else "aprovada")
    if pendente:
        msg = (f"Obrigado! A correção “{rotulo}” foi registrada e será usada depois que o monitor aprovar.")
    else:
        msg = (f"Obrigado! A IA guardou este exemplo de “{rotulo}”. "
               "Tire o objeto da frente da câmera e mostre de novo para ver se ela reconhece.")
    return {"ok": True, "id": exemplo.id, "rotulo": rotulo, "pendente": pendente, "mensagem": msg,
            "classe_original": original, "confianca_original": confianca_original,
            "caixa": [x1, y1, x2, y2], **memoria.resumo()}


@app.get("/api/aprendizado", dependencies=[Depends(exigir_pin)])
async def listar_aprendizado():
    return {"exemplos": memoria.listar(), **memoria.resumo()}


@app.post("/api/aprendizado/{id_}/aprovar", dependencies=[Depends(exigir_pin)])
async def aprovar_correcao(id_: str):
    if not memoria.aprovar(id_):
        raise HTTPException(404, "Correção não encontrada.")
    return {"ok": True}


@app.delete("/api/aprendizado/{id_}", dependencies=[Depends(exigir_pin)])
async def remover_correcao(id_: str):
    if not memoria.remover(id_):
        raise HTTPException(404, "Correção não encontrada.")
    log.info("Correção removida pelo monitor")
    return {"ok": True}


@app.post("/api/aprendizado/esquecer", dependencies=[Depends(exigir_pin)])
async def esquecer_aprendizado():
    memoria.esquecer_tudo()
    log.info("Aprendizado apagado pelo monitor")
    return {"ok": True}


@app.get("/api/aprendizado/exportar", dependencies=[Depends(exigir_pin)])
async def exportar_aprendizado():
    nome = time.strftime("aprendizado-%Y%m%d-%H%M%S.json")
    return JSONResponse(memoria.exportar(), headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.post("/api/aprendizado/importar", dependencies=[Depends(exigir_pin)])
async def importar_aprendizado(dados: dict):
    try:
        n = memoria.importar(dados, guardrails.validar_rotulo)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        raise HTTPException(422, "Arquivo de aprendizado inválido.")
    log.info("Aprendizado importado: %d correções", n)
    return {"ok": True, "importados": n, **memoria.resumo()}
