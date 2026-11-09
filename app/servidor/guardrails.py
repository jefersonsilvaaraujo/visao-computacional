"""Regras de comportamento da IA (seção 7 do documento de requisitos).

Tudo aqui é determinístico: as respostas que precisam ser garantidas
(RB01, RB04, RB06, RF09, CA03, CA05) não dependem da LLM.
"""

from __future__ import annotations

import re
import unicodedata

from .vocabulario import DESCRICOES, TODOS_ROTULOS

TAMANHO_MAX_PERGUNTA = 300

AVISO_PESSOAS = (
    "Esta funcionalidade não está disponível: a demonstração não identifica pessoas, "
    "não faz reconhecimento facial e não estima atributos pessoais como idade, gênero ou emoções. "
    "Posso responder perguntas sobre os objetos capturados."
)

AVISO_SEGURANCA = (
    "Por segurança, esta demonstração responde apenas perguntas sobre os objetos capturados. "
    "Não é possível alterar as instruções do sistema, executar comandos ou acessar arquivos."
)

DESCRICAO_APRENDIDA = (
    "“{classe}” foi ensinado por visitantes da demonstração; não há descrição pré-definida para esse objeto."
)

AVISO_SEM_OBJETOS = (
    "Não foi possível identificar objetos com confiança suficiente (limiar de {limiar}%). "
    "Tente aproximar o objeto da câmera, centralizá-lo, melhorar a iluminação ou usar um fundo mais neutro."
)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


_PADRAO_PESSOAS = re.compile(
    r"\bpessoas?\b|\brostos?\b|\bfaces?\b|\bfacial\b|\breconhecimento facial\b"
    r"|\bquem (e|eh|sou|esta|seria|era)\b"
    r"|\bidentifi\w* (alguem|uma pessoa|a pessoa|individuo|o visitante|voce mesmo|me)\b"
    r"|\bme (reconhece|identifica|ve)\b|\bmeu nome\b|\bnome d[aeo] (pessoa|visitante|menin|rapaz|moca|homem|mulher)"
    r"|\bidade\b|\bquantos anos\b|\betnia\b|\braca\b|\breligiao\b|\bgenero\b|\bsexo\b|\borientacao sexual\b"
    r"|\bemoc(ao|oes)\b|\bsentimentos?\b|\bfeliz\b|\btriste\b|\bbonit[oa]\b|\bfei[oa]\b|\bgord[oa]\b|\bmagr[oa]\b"
    r"|\bhomem\b|\bmulher\b|\bcrianca\b"
)

_PADRAO_INJECAO = re.compile(
    r"\bignor\w*\b|\besquec\w* (as|suas|todas|o que|tudo)\b|\bdesconsider\w*\b"
    r"|\b(suas|tuas) (instruc\w*|regras|ordens|diretrizes)\b"
    r"|\binstruc(ao|oes) (do sistema|internas?|anteriores|iniciais|originais|ocultas)\b"
    r"|\bregras? (do sistema|internas?|anteriores)\b|\bprompt\b|\bsystem\b|\bsistema interno\b"
    r"|\bmodo (desenvolvedor|dev|admin|deus)\b|\bjailbreak\b|\bdan\b|\bfinja\b|\baja como\b|\bvoce agora e\b"
    r"|\bexecut\w*\b|\bcomandos?\b|\bterminal\b|\bshell\b|\bbash\b|\bcmd\b|\bpowershell\b|\bsudo\b|\brm -"
    r"|\barquivos?\b|\bpastas?\b|\bdiretorio\b|\bsenhas?\b|\bpython\b|\bscript\b|\bimport os\b"
    r"|\bacess\w* (o|a|os|as) (computador|sistema|internet|rede|arquivo|disco)\b"
    r"|https?://|<\s*/?\s*(pergunta|system|script)|```|\{\{|\[inst\]|<\|"
)

# Detalhes visuais que o detector não fornece (RB01 / CA05)
_DETALHES = [
    (r"\bmarcas?\b|\bfabricante\b|\blogo\w*\b|\bgrife\b", "a marca ou o fabricante"),
    (r"\bmodelo\b(?! (de ia|de linguagem|de deteccao|detector|yolo|llm|de inteligencia))", "o modelo específico"),
    (r"\bcor(es)?\b|\bcolorid\w*\b|\btonalidade\b", "a cor"),
    (r"\bescrit\w*\b|\btexto\b|\bletras?\b|\brotulo d\w*\b|\betiqueta\b|\bler o\b|\bleia\b", "textos ou rótulos escritos"),
    (r"\bpreco\b|\bquanto custa\b|\bcusta quanto\b", "o preço"),
    (r"\btamanho\b|\bmedidas?\b|\baltura\b|\blargura\b|\bpesa\b|\bpeso\b|\bcentimetros?\b", "o tamanho ou o peso"),
    (r"\bmateriais?\b|\bfeit[oa] de\b", "o material"),
    (r"\bonde (esta|fica)\b|\bposicao\b|\b(a|na) (esquerda|direita)\b|\bdistancia\b", "a posição exata"),
    (r"\bdentro d\w*\b|\bconteudo\b|\bchei[oa]\b|\bvazi[oa]\b|\bnovo ou\b|\bvelho\b|\bquebrad\w*\b|\bestado de conservacao\b",
     "o conteúdo ou o estado de conservação"),
]
_DETALHES = [(re.compile(p), d) for p, d in _DETALHES]


def classificar_pergunta(pergunta: str) -> tuple[str, str | None]:
    """Retorna (categoria, detalhe). Categorias: vazia, longa, pessoas, injecao, detalhe, livre."""
    if not pergunta or not pergunta.strip():
        return "vazia", None
    if len(pergunta) > TAMANHO_MAX_PERGUNTA:
        return "longa", None
    norm = normalizar(pergunta)
    if _PADRAO_INJECAO.search(norm):
        return "injecao", None
    if _PADRAO_PESSOAS.search(norm):
        return "pessoas", None
    for padrao, descricao in _DETALHES:
        if padrao.search(norm):
            return "detalhe", descricao
    return "livre", None


def nivel_confianca(v: float) -> str:
    if v >= 0.75:
        return "alta"
    if v >= 0.6:
        return "media"
    return "baixa"


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


# --- Rótulos ensinados pelos visitantes ------------------------------------
_PADRAO_ROTULO = re.compile(r"^[a-z0-9à-öø-ÿ][a-z0-9à-öø-ÿ '\-/]{0,38}[a-z0-9à-öø-ÿ]$")
_OFENSIVOS = re.compile(
    r"\b(porra|caralh\w*|merda|put[ao]s?|putaria|fod\w*|fdp|bucet\w*|cu|bosta|viad\w*|corn[oa]|"
    r"arrombad\w*|desgra[cç]\w*|vagabund\w*|otari\w*|babaca|safad\w*|"
    r"nazi\w*|hitler|macaco preto)\b"
)


# Rótulos são curtos e só aceitam letras/números; aqui bastam palavras típicas de comandos.
_INJECAO_ROTULO = re.compile(
    r"\b(ignor\w*|instruc\w*|regras?|prompt|sistema|system|respond\w*|diga|fale|xingu\w*|execut\w*|"
    r"comandos?|esquec\w*|finja|revel\w*|senhas?|script|python|sudo)\b"
)


def validar_rotulo(texto: str) -> tuple[bool, str]:
    """Valida o nome ensinado pelo visitante. Retorna (ok, rótulo normalizado ou mensagem)."""
    rotulo = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if len(rotulo) < 2:
        return False, "Digite o nome do objeto (pelo menos 2 letras)."
    if len(rotulo) > 40:
        return False, "Use um nome curto, com até 40 caracteres."
    if not _PADRAO_ROTULO.match(rotulo):
        return False, "Use apenas letras, números, espaços e hífen."
    norm = normalizar(rotulo)
    if _INJECAO_ROTULO.search(norm):
        return False, "Esse nome não pode ser usado. Digite apenas o nome do objeto."
    if _PADRAO_PESSOAS.search(norm) or norm in {"eu", "voce", "ele", "ela"}:
        return False, "A demonstração não aprende nomes ou características de pessoas, apenas de objetos."
    if _OFENSIVOS.search(norm):
        return False, "Esse nome não pode ser usado na demonstração."
    return True, rotulo


def _descrever_objeto(o: dict) -> str:
    q = int(o["quantidade"])
    n = "objeto" if q == 1 else "objetos"
    origem = o.get("origem", "detector")
    original = o.get("classe_original")
    if origem == "aprendido":
        txt = (f"{q} {n} reconhecido{'s' if q > 1 else ''} como {o['classe']} a partir de exemplos ensinados "
               f"por visitantes (semelhança de {_pct(o['confianca'])}")
        return txt + (f"; o detector original sugeriu {original})" if original else ")")
    if origem == "corrigido":
        txt = f"{q} {n} que o visitante corrigiu para {o['classe']}"
        return txt + (f" (o detector havia sugerido {original} com confiança de {_pct(o['confianca'])})"
                      if original else " (o detector não havia encontrado esse objeto)")
    return f"{q} {n} da classe {o['classe']} (confiança de {_pct(o['confianca'])})"


def texto_observacao(captura: dict) -> str:
    """Frase determinística com o que a câmera observou (RB02, RB03, RF09)."""
    objetos = captura.get("objetos", [])
    limiar = round(float(captura.get("confianca_minima", 0.5)) * 100)
    if captura.get("sem_objetos") or not objetos:
        return AVISO_SEM_OBJETOS.format(limiar=limiar)
    partes = [_descrever_objeto(o) for o in objetos]
    if len(partes) == 1:
        lista = partes[0]
    else:
        lista = ", ".join(partes[:-1]) + " e " + partes[-1]
    total = sum(int(o["quantidade"]) for o in objetos)
    verbo = "foi identificado" if total == 1 else "foram identificados"
    frase = f"Na captura, {verbo} {lista}."

    alertas = []
    baixas = [o["classe"] for o in objetos if o["confianca"] < 0.6 and o.get("origem", "detector") == "detector"]
    if baixas:
        alertas.append(
            f"A confiança para {', '.join(baixas)} é moderada; o resultado pode estar incorreto."
        )
    for a, b in captura.get("conflitos", []):
        alertas.append(
            f"As classes {a} e {b} foram atribuídas à mesma região da imagem, o que indica dúvida do detector entre elas."
        )
    if alertas:
        frase += " " + " ".join(alertas)
    return frase


def resposta_detalhe(captura: dict, detalhe: str) -> str:
    base = (
        f"Não consigo determinar {detalhe}. O detector fornece apenas a classe do objeto, "
        "a quantidade e uma estimativa de confiança; ele não informa marca, cor, textos, tamanho ou posição exata."
    )
    objetos = captura.get("objetos", [])
    if objetos:
        base += " Classes presentes na captura: " + ", ".join(o["classe"] for o in objetos) + "."
    return base


def descricao_predefinida(captura: dict) -> str:
    """Texto usado quando a LLM está indisponível (RF18)."""
    objetos = captura.get("objetos", [])
    vistos, frases = set(), []
    for o in objetos:
        if o["classe"] not in vistos:
            vistos.add(o["classe"])
            frases.append(DESCRICOES.get(o["classe"], DESCRICAO_APRENDIDA.format(classe=o["classe"])))
    return " ".join(f for f in frases if f)


# --- Verificação da resposta da LLM (RF10) -----------------------------------
# Nomes de objetos que também são palavras comuns do português ("dado que…",
# "caixa de diálogo", "chave do problema") ficam fora da verificação.
_AMBIGUOS = {"pessoa", "dado", "caixa", "pasta", "chave", "bala", "lata", "meia", "anel", "flor", "pente",
             "prato", "pote", "moeda", "pilha", "clipe", "cola", "sacola", "banco", "mesa", "bola", "vaso",
             "folha de papel", "chapéu", "sapato", "laranja", "limão", "brinquedo", "relógio", "mouse"}
_ROTULOS_VERIFICAVEIS: list[tuple[str, re.Pattern]] = []
for _rotulo in sorted(TODOS_ROTULOS):
    if _rotulo in _AMBIGUOS:
        continue
    for _parte in _rotulo.split("/"):
        _n = normalizar(_parte)
        _ROTULOS_VERIFICAVEIS.append((_rotulo, re.compile(rf"\b{re.escape(_n)}s?\b")))

_NEGACAO = re.compile(r"\b(nao|nenhum\w*|sem|nem|ausencia)\b[^.]{0,60}$")


def classes_nao_capturadas(resposta: str, captura: dict, pergunta: str = "") -> list[str]:
    """Rótulos de classes citados na resposta que não fazem parte da captura.

    Classes citadas pelo próprio visitante na pergunta são ignoradas
    (ex.: "Tem um celular na cena?" → a resposta precisa citar "celular")."""
    presentes = {o["classe"] for o in captura.get("objetos", [])}
    norm = normalizar(resposta)
    norm_pergunta = normalizar(pergunta)
    citadas = []
    for rotulo, padrao in _ROTULOS_VERIFICAVEIS:
        if rotulo in presentes or rotulo in citadas or padrao.search(norm_pergunta):
            continue
        for m in padrao.finditer(norm):
            antes = norm[max(0, m.start() - 40) : m.start()]
            if not _NEGACAO.search(antes):
                citadas.append(rotulo)
                break
    return citadas


def contar_palavras(texto: str) -> int:
    return len(re.findall(r"\S+", texto))
