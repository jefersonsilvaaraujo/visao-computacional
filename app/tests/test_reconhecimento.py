"""Reconhecimento em duas etapas (YOLO localiza, CLIP dá o nome) e ensino com vários ângulos."""
from types import SimpleNamespace

import numpy as np

from servidor.aprendizado import Memoria
from servidor.config import Ajustes
from servidor.detector import Deteccao
from servidor.reconhecimento import SessaoReconhecimento, analisar
from servidor.vocabulario import ROTULOS

QUADRO = np.zeros((480, 640, 3), np.uint8)


def _unit(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


class DetectorFalso:
    def __init__(self, deteccoes):
        self.deteccoes = deteccoes

    def detectar(self, quadro, limiar, iou, incluir_pessoas):
        return [Deteccao(d.classe_id, d.classe, d.confianca, d.caixa) for d in self.deteccoes
                if d.confianca >= limiar], 5.0


class ClipFalso:
    """Devolve, para cada caixa, um vetor fixo associado à posição dela."""
    pronto = True

    def __init__(self, vetores_por_x, nomes_por_x):
        self.v, self.n, self.chamadas = vetores_por_x, nomes_por_x, 0

    def extrair(self, recortes):
        self.chamadas += len(recortes)
        return np.stack([self.v[r.shape[1]] for r in recortes])

    def nomear(self, vetores):
        saida = []
        for v in vetores:
            x = next(k for k, vv in self.v.items() if np.allclose(vv, v))
            saida.append(self.n[x])
        return saida


def _caixa(x0, largura):  # caixa cujo recorte tem largura (em pixels) única, para o ClipFalso
    return (x0 / 640, 0.2, (x0 + largura) / 640, 0.6)


def test_clip_renomeia_objeto_fora_do_coco(tmp_path):
    # YOLO acha a caixa da caneta, mas com o nome errado e confiança baixa
    det = DetectorFalso([Deteccao(34, "taco de beisebol", 0.22, _caixa(100, 40))])
    largura = 42  # recorte com 5% de margem
    clip = ClipFalso({largura: _unit(1)}, {largura: ("caneta", 0.71)})
    r, _, diag = analisar(QUADRO, Ajustes(), det, clip, Memoria(tmp_path), SessaoReconhecimento())
    assert [(d.classe, round(d.confianca, 2), d.nome_por) for d in r] == [("caneta", 0.71, "clip")]
    assert "caneta" in ROTULOS


def test_nome_pouco_provavel_e_yolo_fraco_sao_descartados(tmp_path):
    det = DetectorFalso([Deteccao(34, "taco de beisebol", 0.22, _caixa(100, 40))])
    clip = ClipFalso({42: _unit(1)}, {42: ("caneta", 0.2)})
    r, _, _ = analisar(QUADRO, Ajustes(), det, clip, Memoria(tmp_path), SessaoReconhecimento())
    assert r == []


def test_yolo_muito_confiante_mantem_nome(tmp_path):
    det = DetectorFalso([Deteccao(39, "garrafa", 0.93, _caixa(100, 40))])
    clip = ClipFalso({42: _unit(1)}, {42: ("garrafa térmica", 0.6)})
    r, _, _ = analisar(QUADRO, Ajustes(), det, clip, Memoria(tmp_path), SessaoReconhecimento())
    assert [(d.classe, d.nome_por) for d in r] == [("garrafa", "yolo")]


def test_exemplo_ensinado_tem_prioridade(tmp_path):
    mem = Memoria(tmp_path)
    mem.adicionar("marca-texto", "taco de beisebol", _unit(1)[None], aprovado=True)
    det = DetectorFalso([Deteccao(34, "taco de beisebol", 0.3, _caixa(100, 40))])
    clip = ClipFalso({42: _unit(1)}, {42: ("caneta", 0.8)})
    r, _, diag = analisar(QUADRO, Ajustes(), det, clip, mem, SessaoReconhecimento())
    assert [(d.classe, d.origem, d.classe_original) for d in r] == [("marca-texto", "aprendido", "taco de beisebol")]
    assert diag["rotulo_proximo"] == "marca-texto"


def test_cache_evita_recalcular_caixa_parada(tmp_path):
    det = DetectorFalso([Deteccao(34, "x", 0.3, _caixa(100, 40))])
    clip = ClipFalso({42: _unit(1)}, {42: ("caneta", 0.8)})
    sessao, aj = SessaoReconhecimento(), Ajustes()
    for _ in range(5):
        analisar(QUADRO, aj, det, clip, Memoria(tmp_path), sessao)
    assert clip.chamadas == 1


def test_clip_desligado_volta_ao_yolo(tmp_path):
    det = DetectorFalso([Deteccao(34, "taco de beisebol", 0.55, _caixa(100, 40))])
    clip = ClipFalso({42: _unit(1)}, {42: ("caneta", 0.9)})
    aj = Ajustes(reconhecer_com_clip=False)
    r, _, diag = analisar(QUADRO, aj, det, clip, Memoria(tmp_path), SessaoReconhecimento())
    assert [d.classe for d in r] == ["taco de beisebol"] and diag is None


def test_ensino_coleta_angulos_diferentes_e_ignora_repetidos(monkeypatch):
    import servidor.reconhecimento as rec
    relogio = [0.0]

    def avancar():
        relogio[0] += 1.0
        return relogio[0]
    monkeypatch.setattr(rec.time, "monotonic", avancar)
    monkeypatch.setattr(rec, "DURACAO_ENSINO_S", 1e9)
    s = SessaoReconhecimento()
    ref = _unit(1)
    s.iniciar_ensino("e1", "caneta", np.stack([ref]), meta=3)
    parecido = ref + 0.6 * _unit(2); parecido /= np.linalg.norm(parecido)
    outro = _unit(3)
    s.coletar(np.stack([outro, parecido]))  # escolhe o parecido com o objeto ensinado
    s.coletar(np.stack([parecido]))  # repetido: ignorado
    s.coletar(np.stack([outro]))  # objeto diferente: ignorado
    assert len(s.ensino.coletados) == 1 and not s.ensino_terminou()
    for k in range(4, 6):
        v = ref + 0.7 * _unit(k); s.coletar(np.stack([v / np.linalg.norm(v)]))
    assert s.ensino_terminou() and s.estado_ensino()["coletados"] == 3


def test_memoria_acrescenta_angulos(tmp_path):
    m = Memoria(tmp_path)
    e = m.adicionar("caneta", None, np.stack([_unit(1)]), aprovado=True)
    assert m.adicionar_vetores(e.id, np.stack([_unit(2), _unit(3)])) == 3
    assert m.buscar(_unit(3)[None])[0][0] == "caneta"
    assert len(Memoria(tmp_path).vetores_de(e.id)) == 3  # persistido


def test_ajustes_antigos_sao_migrados(tmp_path):
    import json
    from servidor.config import GerenciadorAjustes
    arq = tmp_path / "ajustes.json"
    arq.write_text(json.dumps({"semelhanca_minima": 0.7, "limiar_candidatos": 0.15, "confianca_minima": 0.6}))
    a = GerenciadorAjustes(arq).atual
    assert a.semelhanca_minima == 0.75 and a.limiar_candidatos == 0.05 and a.confianca_minima == 0.6


def test_partes_do_mesmo_objeto_aprendido_viram_uma_caixa():
    from servidor.reconhecimento import _juntar_partes
    tampa = Deteccao(0, "marca-texto", 0.87, (0.40, 0.50, 0.50, 0.60)); tampa.origem = "aprendido"
    corpo = Deteccao(0, "marca-texto", 0.80, (0.20, 0.30, 0.42, 0.52)); corpo.origem = "aprendido"
    longe = Deteccao(0, "marca-texto", 0.78, (0.80, 0.10, 0.90, 0.20)); longe.origem = "aprendido"
    r = _juntar_partes([tampa, corpo, longe])
    assert len(r) == 2 and r[0].caixa == (0.20, 0.30, 0.50, 0.60)
    # corpo (nome do CLIP) e tampa (aprendida) separados por uma fresta pequena
    corpo = Deteccao(0, "marca-texto", 0.98, (0.47, 0.23, 0.58, 0.654)); corpo.nome_por = "clip"
    tampa = Deteccao(0, "marca-texto", 0.94, (0.40, 0.659, 0.54, 0.85)); tampa.origem = "aprendido"
    assert len(_juntar_partes([corpo, tampa])) == 1
    # dois livros lado a lado (detector) continuam separados
    a, b = Deteccao(73, "livro", 0.9, (0.1, 0.1, 0.3, 0.5)), Deteccao(73, "livro", 0.8, (0.3, 0.1, 0.5, 0.5))
    assert len(_juntar_partes([a, b])) == 2


def test_ensino_respeita_intervalo_entre_angulos(monkeypatch):
    import servidor.reconhecimento as rec
    relogio = [100.0]
    monkeypatch.setattr(rec.time, "monotonic", lambda: relogio[0])
    s = SessaoReconhecimento()
    ref = _unit(1)
    s.iniciar_ensino("e1", "caneta", np.stack([ref]), meta=5)
    for k in range(4):  # 4 quadros quase ao mesmo tempo: só o primeiro conta
        v = ref + 0.7 * _unit(10 + k); s.coletar(np.stack([v / np.linalg.norm(v)]))
    assert len(s.ensino.coletados) == 1
    relogio[0] += 0.3
    v = ref + 0.7 * _unit(20); s.coletar(np.stack([v / np.linalg.norm(v)]))
    assert len(s.ensino.coletados) == 2
