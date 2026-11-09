/* Visão Computacional com IA Local — interface do navegador.
 *
 * A câmera é aberta pelo navegador (funciona com Docker em Windows, macOS e Linux).
 * Os quadros vão por WebSocket ao servidor local, que roda o detector e devolve
 * as caixas. Nada é gravado: os quadros existem só na memória enquanto são analisados.
 */
"use strict";

const $ = (id) => document.getElementById(id);

const estado = {
  stream: null,
  cameraId: localStorageGet("cameraId"),
  espelhar: localStorageGet("espelhar") !== "0",
  pausado: false,
  erroCamera: null,
  tentativaCamera: null,
  ws: null,
  wsConectado: false,
  aguardandoResposta: false,
  ultimoEnvio: 0,
  fpsMax: 12,
  confiancaMinima: 0.5,
  deteccoes: [],
  instanteDeteccoes: 0,
  estavel: { objetos: [], conflitos: [] },
  instanteEstavel: null,
  captura: null,
  instanteCaptura: null,
  historico: [],
  gerando: false,
  abortar: null,
  statusServidor: null,
  pin: null,
  // Aprendizado por correções (RF19). Quadros ficam só na memória da página.
  blobEmVoo: null,
  blobDeteccoes: null,
  quadroCapturado: null,
  deteccoesCapturadas: [],
  caixasCapturadas: {},
  aprendizado: { ativo: false, objetos: 0, correcoes: 0, pendentes: 0 },
  corrigindo: false,
  ensino: null, // ensino com vários ângulos em andamento
  ensinoTimeout: null,
  diag: { fpsVideo: 0, fpsDeteccao: 0, inferenciaMs: 0, ultimaLlmMs: null, primeiroTokenMs: null, dispositivo: "—", aprendizado: null },
};

function localStorageGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ignorado */ } }
const pct = (v) => `${Math.round(v * 100)}%`;
const hora = (d) => d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/* ------------------------------------------------------------------ estados (RF01) */
function definirPilula(id, nivel, texto) {
  const el = $(id);
  el.dataset.nivel = nivel;
  el.querySelector("small").textContent = texto;
}

const alertas = new Map();
function definirAlerta(chave, texto) {
  if (texto) alertas.set(chave, texto); else alertas.delete(chave);
  const el = $("alerta");
  if (alertas.size === 0) { el.hidden = true; return; }
  $("alerta-texto").textContent = [...alertas.values()].join("  •  ");
  el.hidden = false;
}

async function atualizarStatus() {
  try {
    const r = await fetch("/api/status", { cache: "no-store" });
    const s = await r.json();
    estado.statusServidor = s;
    estado.fpsMax = s.ajustes.fps_max_deteccao;
    estado.confiancaMinima = s.ajustes.confianca_minima;
    const antes = JSON.stringify(estado.aprendizado);
    estado.aprendizado = s.aprendizado;
    if (antes !== JSON.stringify(s.aprendizado)) { atualizarContadorAprendizado(); if (estado.captura && !estado.corrigindo) renderizarLista(); }
    definirAlerta("servidor", null);

    if (s.detector.pronto && estado.wsConectado) {
      definirPilula("estado-detector", "ok", `pronto · ${s.detector.dispositivo}`);
      definirAlerta("detector", null);
    } else if (!s.detector.pronto) {
      definirPilula("estado-detector", "erro", "com falha");
      definirAlerta("detector", `Detector indisponível: ${s.detector.erro || "carregando"}.`);
    } else {
      definirPilula("estado-detector", "atencao", "conectando…");
    }

    const l = s.llm;
    if (l.estado === "pronta") {
      definirPilula("estado-llm", "ok", `pronta · ${l.dispositivo}`);
      definirAlerta("llm", null);
    } else if (l.estado === "baixando") {
      const p = l.progresso != null ? ` ${Math.round(l.progresso * 100)}%` : "";
      definirPilula("estado-llm", "atencao", `baixando modelo${p}`);
      definirAlerta("llm", null);
    } else if (l.estado === "carregando" || l.estado === "verificando") {
      definirPilula("estado-llm", "atencao", "carregando…");
      definirAlerta("llm", null);
    } else {
      definirPilula("estado-llm", "erro", "indisponível");
      definirAlerta("llm", `${l.mensagem} Respostas usarão descrições pré-definidas.`);
    }
  } catch {
    definirPilula("estado-detector", "erro", "sem servidor");
    definirPilula("estado-llm", "erro", "sem servidor");
    definirAlerta("servidor", "Não foi possível falar com o servidor local. Verifique se os containers estão em execução (script 2-iniciar).");
  }
}

/* ------------------------------------------------------------------ câmera (RF02, RF14) */
function mensagemErroCamera(e) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
    return "Este navegador não liberou a câmera. Abra a aplicação pelo endereço http://localhost:8080 em um navegador atualizado (Chrome, Edge ou Firefox).";
  switch (e && e.name) {
    case "NotAllowedError": return "Permissão da câmera negada. Clique no ícone de câmera na barra de endereço, permita o acesso e clique em Tentar novamente.";
    case "NotFoundError": case "OverconstrainedError": return "Nenhuma câmera encontrada. Conecte uma webcam e clique em Tentar novamente.";
    case "NotReadableError": return "A câmera está em uso por outro programa (Teams, Zoom, Meet…). Feche-o e clique em Tentar novamente.";
    default: return `Falha ao abrir a câmera${e && e.message ? ": " + e.message : ""}.`;
  }
}

function pararCamera() {
  if (estado.stream) estado.stream.getTracks().forEach((t) => t.stop());
  estado.stream = null;
  $("video").srcObject = null;
}

async function iniciarCamera() {
  clearTimeout(estado.tentativaCamera);
  pararCamera();
  if (estado.pausado) return;
  definirPilula("estado-camera", "atencao", "abrindo…");
  const video = { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30 } };
  if (estado.cameraId) video.deviceId = { exact: estado.cameraId };
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("sem suporte");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video, audio: false });
    } catch (e) {
      if (estado.cameraId && (e.name === "OverconstrainedError" || e.name === "NotFoundError")) {
        estado.cameraId = null; // câmera escolhida sumiu: volta para a padrão
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      } else throw e;
    }
    if (estado.pausado) { stream.getTracks().forEach((t) => t.stop()); return; }
    estado.stream = stream;
    const trilha = stream.getVideoTracks()[0];
    trilha.addEventListener("ended", () => falhaCamera(new Error("a câmera foi desconectada")));
    const v = $("video");
    v.srcObject = stream;
    await v.play().catch(() => {});
    estado.erroCamera = null;
    definirAlerta("camera", null);
    $("palco-msg").hidden = true;
    definirPilula("estado-camera", "ok", "ativa");
    listarCameras();
  } catch (e) {
    falhaCamera(e);
  }
}

function falhaCamera(e) {
  pararCamera();
  estado.erroCamera = mensagemErroCamera(e);
  definirPilula("estado-camera", "erro", "com falha");
  definirAlerta("camera", estado.erroCamera);
  $("palco-msg").textContent = estado.erroCamera;
  $("palco-msg").hidden = false;
  // RNF03: tenta recuperar a câmera automaticamente.
  if (!estado.pausado && e && e.name !== "NotAllowedError") {
    clearTimeout(estado.tentativaCamera);
    estado.tentativaCamera = setTimeout(iniciarCamera, 4000);
  }
}

async function listarCameras() {
  try {
    const dispositivos = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
    const sel = $("sel-camera");
    const atual = estado.stream && estado.stream.getVideoTracks()[0].getSettings().deviceId;
    sel.innerHTML = "";
    dispositivos.forEach((d, i) => {
      const o = document.createElement("option");
      o.value = d.deviceId;
      o.textContent = d.label || `Câmera ${i + 1}`;
      if (d.deviceId === atual) o.selected = true;
      sel.appendChild(o);
    });
  } catch { /* ignorado */ }
}

function alternarPausa() {
  estado.pausado = !estado.pausado;
  const b = $("pausar");
  if (estado.pausado) {
    clearTimeout(estado.tentativaCamera);
    pararCamera(); // libera a câmera (CA01)
    b.textContent = "▶ Retomar demonstração";
    definirPilula("estado-camera", "neutro", "pausada");
    definirAlerta("camera", null);
    $("palco-msg").textContent = "Demonstração pausada. A câmera foi liberada.";
    $("palco-msg").hidden = false;
    estado.deteccoes = [];
  } else {
    b.textContent = "⏸ Pausar demonstração";
    $("palco-msg").textContent = "Iniciando a câmera…";
    iniciarCamera();
  }
}

/* ------------------------------------------------------------------ detecção via WebSocket */
const telaEnvio = document.createElement("canvas");

function conectarWs() {
  const protocolo = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocolo}://${location.host}/ws/deteccao`);
  estado.ws = ws;
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { estado.wsConectado = true; estado.aguardandoResposta = false; atualizarStatus(); };
  ws.onclose = () => {
    estado.wsConectado = false;
    estado.aguardandoResposta = false;
    definirPilula("estado-detector", "atencao", "reconectando…");
    setTimeout(conectarWs, 2000);
  };
  ws.onerror = () => {};
  ws.onmessage = (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch { return; }
    if (m.tipo === "deteccao") {
      estado.aguardandoResposta = false;
      estado.deteccoes = m.deteccoes;
      estado.blobDeteccoes = estado.blobEmVoo; // quadro exato que gerou estas caixas
      estado.diag.aprendizado = m.aprendizado;
      estado.diag.economia = m.economia;
      estado.instanteDeteccoes = performance.now();
      estado.estavel = m.estavel;
      estado.instanteEstavel = new Date();
      estado.fpsMax = m.fps_max;
      estado.confiancaMinima = m.confianca_minima;
      estado.diag.fpsDeteccao = m.fps;
      estado.diag.inferenciaMs = m.inferencia_ms;
      estado.diag.dispositivo = m.dispositivo;
      // Com a cena congelada, só a linha "Ao vivo agora" muda (a lista e os botões ficam estáveis).
      if (estado.captura) atualizarAoVivo(); else renderizarLista();
      if (m.ensino) atualizarEnsino(m.ensino);
    } else if (m.tipo === "ensino") {
      if (m.fim) finalizarEnsino(m);
      else atualizarEnsino(m);
    } else if (m.tipo === "erro") {
      estado.aguardandoResposta = false;
      definirPilula("estado-detector", "erro", "com falha");
      definirAlerta("detector", m.mensagem);
    }
  };
}

function enviarQuadro() {
  const v = $("video");
  const ws = estado.ws;
  if (estado.pausado || !estado.stream || !ws || ws.readyState !== WebSocket.OPEN) return;
  if (v.readyState < 2 || !v.videoWidth) return;
  const agora = performance.now();
  if (estado.aguardandoResposta) {
    if (agora - estado.ultimoEnvio < 3000) return; // evita travar se uma resposta se perder
  }
  if (agora - estado.ultimoEnvio < 1000 / estado.fpsMax) return;
  estado.ultimoEnvio = agora;
  estado.aguardandoResposta = true;
  const escala = Math.min(1, 640 / v.videoWidth);
  telaEnvio.width = Math.round(v.videoWidth * escala);
  telaEnvio.height = Math.round(v.videoHeight * escala);
  telaEnvio.getContext("2d").drawImage(v, 0, 0, telaEnvio.width, telaEnvio.height);
  telaEnvio.toBlob((blob) => {
    if (blob && ws.readyState === WebSocket.OPEN) { estado.blobEmVoo = blob; ws.send(blob); }
    else estado.aguardandoResposta = false;
  }, "image/jpeg", 0.75);
}

/* ------------------------------------------------------------------ desenho das caixas (RF03) */
function retanguloVideo(largura, altura, v) {
  const vw = v.videoWidth || 640, vh = v.videoHeight || 480;
  const e = Math.min(largura / vw, altura / vh);
  const w = vw * e, h = vh * e;
  return { x: (largura - w) / 2, y: (altura - h) / 2, w, h };
}

function desenharCaixas(ctx, deteccoes, r, espelhar, escalaFonte = 1) {
  ctx.lineWidth = Math.max(2, 3 * escalaFonte);
  ctx.font = `600 ${Math.round(16 * escalaFonte)}px Segoe UI, system-ui, sans-serif`;
  ctx.textBaseline = "top";
  for (const d of deteccoes) {
    let [x1, y1, x2, y2] = d.caixa;
    if (espelhar) [x1, x2] = [1 - x2, 1 - x1];
    const x = r.x + x1 * r.w, y = r.y + y1 * r.h, w = (x2 - x1) * r.w, h = (y2 - y1) * r.h;
    const aprendido = d.origem === "aprendido";
    const cor = aprendido ? "#a855f7" : d.confianca < 0.6 ? "#f5a524" : "#2f7cf6";
    ctx.strokeStyle = cor;
    ctx.strokeRect(x, y, w, h);
    const rotulo = aprendido ? `${d.classe} · aprendido ${pct(d.confianca)}` : `${d.classe} ${pct(d.confianca)}`;
    const tw = ctx.measureText(rotulo).width + 12 * escalaFonte;
    const th = 24 * escalaFonte;
    const ty = y - th >= r.y ? y - th : y;
    ctx.fillStyle = cor;
    ctx.fillRect(x, ty, tw, th);
    ctx.fillStyle = "#fff";
    ctx.fillText(rotulo, x + 6 * escalaFonte, ty + 4 * escalaFonte);
  }
}

let quadrosVideo = 0, inicioContagem = performance.now();
function laco() {
  const c = $("sobreposicao"), v = $("video");
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth * dpr, h = c.clientHeight * dpr;
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  const recente = performance.now() - estado.instanteDeteccoes < 1500;
  if (estado.stream && recente) desenharCaixas(ctx, estado.deteccoes, retanguloVideo(w, h, v), estado.espelhar, dpr);
  if (estado.stream) quadrosVideo++;
  const agora = performance.now();
  if (agora - inicioContagem > 1000) {
    estado.diag.fpsVideo = (quadrosVideo * 1000) / (agora - inicioContagem);
    quadrosVideo = 0; inicioContagem = agora;
  }
  enviarQuadro();
  requestAnimationFrame(laco);
}

/* ------------------------------------------------------------------ lista consolidada (RF05) */
function itemObjeto(o, indice) {
  const li = document.createElement("li");
  const nome = document.createElement("span"); nome.className = "nome"; nome.textContent = o.classe;
  const qtd = document.createElement("span"); qtd.className = "qtd";
  const origem = o.origem || "detector";
  const medida = origem === "aprendido" ? "semelhança" : "confiança";
  qtd.textContent = `${o.quantidade > 1 ? o.quantidade + " × · " : ""}${medida} ${pct(o.confianca)}`;
  const barra = document.createElement("div"); barra.className = "barra";
  const s = document.createElement("span"); s.style.width = pct(o.confianca);
  if (origem !== "detector") s.className = "aprendido";
  else if (o.confianca < 0.6) s.className = "baixa";
  barra.appendChild(s);
  li.append(nome, qtd, barra);
  if (origem !== "detector") {
    const selo = document.createElement("span"); selo.className = "selo-origem";
    const b = document.createElement("b");
    b.textContent = origem === "aprendido" ? "🧠 aprendido com visitantes" : "✏️ corrigido agora";
    selo.append(b, document.createTextNode(o.classe_original ? `o detector sugeriu “${o.classe_original}”` : "o detector não tinha encontrado"));
    li.appendChild(selo);
  }
  if (indice != null && estado.aprendizado.ativo && o.classe !== "pessoa" && origem !== "corrigido") {
    const bt = document.createElement("button");
    bt.type = "button"; bt.className = "btn-corrigir"; bt.disabled = estado.gerando;
    bt.textContent = "✏️ Está errado? Corrigir";
    bt.addEventListener("click", () => abrirCorrecao(li, bt, indice));
    li.appendChild(bt);
  }
  return li;
}

function atualizarAoVivo() {
  const vivos = estado.estavel.objetos.map((o) => o.classe);
  $("ao-vivo-agora").textContent = `Ao vivo agora: ${vivos.length ? vivos.join(", ") : "nenhum objeto"}`;
  $("ao-vivo-agora").hidden = false;
}

function renderizarLista() {
  const ul = $("lista-objetos"), selo = $("selo-lista");
  const objetos = estado.captura ? estado.captura.objetos : estado.estavel.objetos;
  ul.innerHTML = "";
  if (estado.captura) {
    selo.textContent = `Congelado às ${hora(estado.instanteCaptura)}`;
    selo.classList.add("congelado");
    atualizarAoVivo();
    $("capturar").textContent = "📸 Capturar nova cena";
  } else {
    selo.textContent = estado.instanteEstavel ? `Ao vivo · ${hora(estado.instanteEstavel)}` : "Ao vivo";
    selo.classList.remove("congelado");
    $("ao-vivo-agora").hidden = true;
    $("capturar").textContent = "📸 Capturar cena";
  }
  if (!objetos.length) {
    const li = document.createElement("li");
    li.className = "vazio";
    li.textContent = estado.captura
      ? "Nenhum objeto atingiu a confiança mínima nesta captura."
      : `Nenhum objeto com confiança acima de ${pct(estado.confiancaMinima)}. Aproxime o objeto ou melhore a iluminação.`;
    ul.appendChild(li);
  } else objetos.forEach((o, i) => ul.appendChild(itemObjeto(o, estado.captura ? i : null)));
  $("ensinar-novo").hidden = !(estado.captura && estado.aprendizado.ativo) || !$("form-novo").hidden;
  $("ensinar-novo").disabled = estado.gerando;
}

/* ------------------------------------------------------------------ captura e LLM (RF06-RF10) */
async function lerFluxo(resposta, aoEvento) {
  if (!resposta.ok) throw new Error(`Servidor respondeu ${resposta.status}`);
  const leitor = resposta.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n")) >= 0) {
      const l = buffer.slice(0, i).trim();
      buffer = buffer.slice(i + 1);
      if (l) aoEvento(JSON.parse(l));
    }
  }
}

function rodapeResposta(el, fim, inicio) {
  el.innerHTML = "";
  const nomes = { llm: "Gerado pela IA local", predefinida: "Descrição pré-definida", regra: "Resposta automática do sistema" };
  const f = document.createElement("span");
  f.className = `fonte ${fim.fonte}`;
  f.textContent = nomes[fim.fonte] || fim.fonte;
  el.appendChild(f);
  if (fim.tempo_total_ms != null) {
    const t = document.createElement("span");
    t.textContent = `${(fim.tempo_total_ms / 1000).toFixed(1)} s`;
    el.appendChild(t);
    estado.diag.ultimaLlmMs = fim.tempo_total_ms;
    estado.diag.primeiroTokenMs = fim.tempo_primeiro_token_ms;
  } else if (inicio) {
    const t = document.createElement("span");
    t.textContent = `${((performance.now() - inicio) / 1000).toFixed(1)} s`;
    el.appendChild(t);
  }
  if (fim.aviso) {
    const a = document.createElement("span");
    a.className = "aviso-resposta";
    a.textContent = fim.aviso;
    el.appendChild(a);
  }
}

function definirGerando(g) {
  estado.gerando = g;
  $("perguntar").disabled = g;
  $("capturar").disabled = g;
  document.querySelectorAll(".chip, .btn-corrigir, #ensinar-novo").forEach((c) => (c.disabled = g));
  $("perguntar").textContent = g ? "Pensando…" : "Perguntar";
}

function fotografarCena() {
  // A imagem fica só na memória da página (não é enviada à LLM nem gravada).
  const v = $("video"), c = $("foto-captura");
  if (!v.videoWidth) { c.hidden = true; return; }
  c.width = v.videoWidth; c.height = v.videoHeight;
  const ctx = c.getContext("2d");
  ctx.save();
  if (estado.espelhar) { ctx.translate(c.width, 0); ctx.scale(-1, 1); }
  ctx.drawImage(v, 0, 0);
  ctx.restore();
  desenharCaixas(ctx, estado.deteccoes, { x: 0, y: 0, w: c.width, h: c.height }, estado.espelhar, c.width / 640);
  c.hidden = false;
}

async function capturarCena() {
  if (estado.gerando) return;
  const pedido = {
    objetos: estado.estavel.objetos.map(({ classe, confianca, quantidade, origem, classe_original }) =>
      ({ classe, confianca, quantidade, origem: origem || "detector", classe_original: classe_original || null })),
    conflitos: estado.estavel.conflitos || [],
  };
  try {
    const r = await fetch("/api/captura", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pedido) });
    if (!r.ok) throw new Error(`Servidor respondeu ${r.status}`);
    estado.captura = await r.json();
  } catch (e) {
    definirAlerta("captura", `Não foi possível capturar a cena: ${e.message}`);
    return;
  }
  definirAlerta("captura", null);
  // Guarda (só na memória) o quadro e as caixas da captura, para uma eventual correção.
  estado.quadroCapturado = estado.blobDeteccoes;
  estado.deteccoesCapturadas = estado.deteccoes.slice();
  estado.caixasCapturadas = {};
  for (const o of estado.estavel.objetos) estado.caixasCapturadas[o.classe] = o.caixa;
  for (const d of [...estado.deteccoesCapturadas].sort((a, b) => a.confianca - b.confianca)) estado.caixasCapturadas[d.classe] = d.caixa;
  $("msg-aprendizado").hidden = true;
  estado.corrigindo = false; // uma nova captura descarta correções em andamento
  $("form-novo").hidden = true;
  $("form-novo").innerHTML = "";
  estado.instanteCaptura = new Date();
  estado.historico = [];
  $("perguntas").innerHTML = "";
  fotografarCena();
  renderizarLista();
  await explicar();
}

async function explicar() {
  const obs = $("texto-observacao"), geral = $("texto-geral"), bloco = $("bloco-geral"), rodape = $("rodape-explicacao");
  $("explicacao-vazia").hidden = true;
  $("explicacao-conteudo").hidden = false;
  obs.textContent = ""; geral.textContent = ""; rodape.innerHTML = "";
  bloco.hidden = true;
  obs.classList.add("pensando");
  definirGerando(true);
  const inicio = performance.now();
  const ctrl = new AbortController();
  estado.abortar = ctrl;
  try {
    const r = await fetch("/api/explicar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(estado.captura), signal: ctrl.signal,
    });
    await lerFluxo(r, (ev) => {
      if (ev.tipo === "observacao") {
        obs.classList.remove("pensando");
        obs.textContent = ev.texto;
        if (!estado.captura.sem_objetos) { bloco.hidden = false; geral.classList.add("pensando"); }
      } else if (ev.tipo === "token") {
        geral.classList.remove("pensando"); geral.classList.add("cursor");
        geral.textContent += ev.texto;
      } else if (ev.tipo === "texto" || ev.tipo === "substituir") {
        geral.classList.remove("pensando");
        geral.textContent = ev.texto;
      } else if (ev.tipo === "fim") {
        geral.classList.remove("pensando", "cursor");
        rodapeResposta(rodape, ev, inicio);
      }
    });
  } catch (e) {
    if (e.name !== "AbortError") {
      obs.textContent = obs.textContent || "Não foi possível gerar a explicação.";
      rodape.textContent = `Erro: ${e.message}`;
    }
  } finally {
    obs.classList.remove("pensando"); geral.classList.remove("pensando", "cursor");
    if (estado.abortar === ctrl) { estado.abortar = null; definirGerando(false); }
  }
}

async function perguntar(texto) {
  texto = (texto || "").trim();
  if (!texto || estado.gerando) return;
  if (!estado.captura) await capturarCena(); // pergunta sem captura: congela a cena atual primeiro
  if (!estado.captura) return;
  $("pergunta").value = "";
  const li = document.createElement("li");
  const p = document.createElement("div"); p.className = "p"; p.textContent = texto;
  const resp = document.createElement("p"); resp.className = "r pensando";
  const rodape = document.createElement("div"); rodape.className = "rodape-resposta";
  li.append(p, resp, rodape);
  $("perguntas").appendChild(li);
  li.scrollIntoView({ behavior: "smooth", block: "nearest" });
  definirGerando(true);
  const inicio = performance.now();
  const ctrl = new AbortController();
  estado.abortar = ctrl;
  let fonte = null;
  try {
    const r = await fetch("/api/perguntar", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
      body: JSON.stringify({ captura: estado.captura, pergunta: texto, historico: estado.historico.slice(-3) }),
    });
    await lerFluxo(r, (ev) => {
      if (ev.tipo === "token") { resp.classList.remove("pensando"); resp.classList.add("cursor"); resp.textContent += ev.texto; }
      else if (ev.tipo === "texto" || ev.tipo === "substituir") { resp.classList.remove("pensando"); resp.textContent = ev.texto; }
      else if (ev.tipo === "fim") { fonte = ev.fonte; rodapeResposta(rodape, ev, inicio); }
    });
    if (fonte === "llm") estado.historico.push({ pergunta: texto.slice(0, 300), resposta: resp.textContent.slice(0, 1200) });
  } catch (e) {
    if (e.name !== "AbortError") resp.textContent = `Não foi possível obter a resposta: ${e.message}`;
  } finally {
    resp.classList.remove("pensando", "cursor");
    if (estado.abortar === ctrl) { estado.abortar = null; definirGerando(false); }
  }
}

/* ------------------------------------------------------------------ correção e aprendizado (RF19) */
async function carregarRotulos() {
  try {
    const r = await (await fetch("/api/rotulos", { cache: "no-store" })).json();
    const dl = $("rotulos-conhecidos");
    dl.innerHTML = "";
    for (const rot of r.rotulos) { const o = document.createElement("option"); o.value = rot; dl.appendChild(o); }
  } catch { /* ignorado */ }
}

function atualizarContadorAprendizado() {
  const a = estado.aprendizado, el = $("contador-aprendizado");
  if (!a || !a.ativo || !a.objetos) { el.hidden = true; return; }
  el.textContent = `🧠 A IA já aprendeu ${a.objetos} ${a.objetos === 1 ? "objeto" : "objetos"} com os visitantes (${a.correcoes} ${a.correcoes === 1 ? "exemplo" : "exemplos"}).`;
  el.hidden = false;
}

function montarFormCorrecao(form, titulo, aoEnviar, aoCancelar) {
  form.innerHTML = "";
  form.className = "correcao";
  const label = document.createElement("label");
  label.textContent = titulo;
  const input = document.createElement("input");
  input.type = "text"; input.maxLength = 40; input.setAttribute("list", "rotulos-conhecidos");
  input.placeholder = "ex.: marca-texto, caneta, estojo…"; input.autocomplete = "off";
  const id = "corr-" + Math.random().toString(36).slice(2, 8);
  input.id = id; label.htmlFor = id;
  const botoes = document.createElement("div"); botoes.className = "botoes";
  const ok = document.createElement("button"); ok.type = "submit"; ok.className = "botao aprender"; ok.textContent = "🧠 Ensinar a IA";
  const cancelar = document.createElement("button"); cancelar.type = "button"; cancelar.className = "botao"; cancelar.textContent = "Cancelar";
  botoes.append(ok, cancelar);
  const erro = document.createElement("p"); erro.className = "erro"; erro.hidden = true;
  form.append(label, input, botoes, erro);
  cancelar.addEventListener("click", aoCancelar);
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const rotulo = input.value.trim();
    if (rotulo.length < 2) { erro.textContent = "Digite o nome do objeto."; erro.hidden = false; return; }
    ok.disabled = true; cancelar.disabled = true; ok.textContent = "Aprendendo…";
    try { await aoEnviar(rotulo); }
    catch (e) { erro.textContent = e.message; erro.hidden = false; ok.disabled = false; cancelar.disabled = false; ok.textContent = "🧠 Ensinar a IA"; }
  };
  setTimeout(() => input.focus(), 30);
}

function blobParaDataUrl(blob) {
  return new Promise((ok, falha) => {
    const r = new FileReader();
    r.onload = () => ok(r.result); r.onerror = () => falha(new Error("Falha ao ler o quadro capturado."));
    r.readAsDataURL(blob);
  });
}

async function enviarCorrecao(rotulo, caixa, classeOriginal) {
  if (!estado.quadroCapturado) throw new Error("O quadro desta captura não está disponível. Capture a cena novamente.");
  const imagem = await blobParaDataUrl(estado.quadroCapturado);
  const r = await fetch("/api/aprendizado", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ imagem, rotulo, caixa: caixa || null, classe_original: classeOriginal || null }),
  });
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corpo.detail || `Erro ${r.status}`);
  return corpo;
}

async function aposAprender(resp) {
  estado.corrigindo = false;
  estado.captura.sem_objetos = estado.captura.objetos.length === 0;
  const msg = $("msg-aprendizado");
  msg.textContent = (resp.pendente ? "⏳ " : "✅ ") + resp.mensagem;
  msg.hidden = false;
  estado.aprendizado = { ...estado.aprendizado, objetos: resp.objetos, correcoes: resp.correcoes, pendentes: resp.pendentes };
  atualizarContadorAprendizado();
  carregarRotulos();
  // A captura mudou: nova explicação, sem o histórico de perguntas anterior.
  estado.historico = [];
  $("perguntas").innerHTML = "";
  renderizarLista();
  // Ensino com vários ângulos: antes da explicação, coleta o objeto em outras posições.
  if (!iniciarEnsino(resp)) await explicar();
}

/* Ensino com vários ângulos: os próximos quadros da câmera viram novos exemplos. */
function iniciarEnsino(resp) {
  const ws = estado.ws;
  if (!resp.id || !ws || ws.readyState !== WebSocket.OPEN || estado.pausado) return false;
  estado.ensino = { rotulo: resp.rotulo, mensagem: $("msg-aprendizado").textContent };
  definirGerando(true);
  $("ensino-texto").textContent = `🔄 Agora mostre o objeto “${resp.rotulo}” para a câmera e gire devagar, em vários ângulos…`;
  $("ensino-progresso").style.width = "0";
  $("ensino-angulos").hidden = false;
  ws.send(JSON.stringify({ acao: "ensinar_angulos", id: resp.id }));
  estado.ensinoTimeout = setTimeout(() => finalizarEnsino({ coletados: 0, erro: "tempo esgotado" }), 15000);
  return true;
}

function atualizarEnsino(e) {
  if (!estado.ensino || e.coletados == null) return;
  $("ensino-progresso").style.width = `${Math.min(100, (100 * e.coletados) / Math.max(1, e.meta || 1))}%`;
}

async function finalizarEnsino(m) {
  if (!estado.ensino) return;
  clearTimeout(estado.ensinoTimeout);
  const rotulo = estado.ensino.rotulo;
  estado.ensino = null;
  $("ensino-angulos").hidden = true;
  definirGerando(false);
  const msg = $("msg-aprendizado");
  msg.textContent = m.coletados > 0
    ? `✅ A IA guardou ${m.coletados} ${m.coletados === 1 ? "ângulo novo" : "ângulos novos"} de “${rotulo}”. Tire o objeto da frente da câmera e mostre de novo para testar.`
    : `✅ Exemplo de “${rotulo}” guardado. Nenhum ângulo extra foi coletado; se quiser, corrija de novo mostrando o objeto inteiro na câmera.`;
  msg.hidden = false;
  await explicar();
}

function abrirCorrecao(li, botao, indice) {
  if (estado.gerando) return;
  estado.corrigindo = true;
  botao.hidden = true;
  const form = document.createElement("form");
  li.appendChild(form);
  const obj = estado.captura.objetos[indice];
  montarFormCorrecao(form, `O que é este objeto de verdade? (a IA disse “${obj.classe}”)`, async (rotulo) => {
    const original = obj.origem === "aprendido" ? obj.classe_original : obj.classe;
    const resp = await enviarCorrecao(rotulo, estado.caixasCapturadas[obj.classe], original);
    estado.captura.objetos[indice] = { ...obj, classe: resp.rotulo, origem: "corrigido", classe_original: original || null };
    await aposAprender(resp);
  }, () => { estado.corrigindo = false; renderizarLista(); });
}

function abrirEnsinarNovo() {
  if (estado.gerando || !estado.captura) return;
  estado.corrigindo = true;
  const form = $("form-novo");
  form.hidden = false;
  $("ensinar-novo").hidden = true;
  montarFormCorrecao(form, "Qual objeto você mostrou para a câmera?", async (rotulo) => {
    const resp = await enviarCorrecao(rotulo, null, null);
    estado.captura.objetos.push({ classe: resp.rotulo, confianca: resp.confianca_original || 0, quantidade: 1,
      origem: "corrigido", classe_original: resp.classe_original || null });
    form.hidden = true; form.innerHTML = "";
    await aposAprender(resp);
  }, () => { form.hidden = true; form.innerHTML = ""; estado.corrigindo = false; renderizarLista(); });
}

/* ------------------------------------------------------------------ Nova demonstração (RF11, RB05) */
function novaDemonstracao() {
  if (estado.ensino) { clearTimeout(estado.ensinoTimeout); estado.ensino = null; $("ensino-angulos").hidden = true; }
  if (estado.abortar) estado.abortar.abort();
  estado.abortar = null;
  definirGerando(false);
  estado.captura = null;
  estado.instanteCaptura = null;
  estado.historico = [];
  estado.quadroCapturado = null;
  estado.deteccoesCapturadas = [];
  estado.caixasCapturadas = {};
  estado.corrigindo = false;
  $("form-novo").hidden = true;
  $("form-novo").innerHTML = "";
  $("msg-aprendizado").hidden = true;
  estado.estavel = { objetos: [], conflitos: [] };
  $("perguntas").innerHTML = "";
  $("pergunta").value = "";
  $("texto-observacao").textContent = "";
  $("texto-geral").textContent = "";
  $("rodape-explicacao").innerHTML = "";
  $("explicacao-conteudo").hidden = true;
  $("explicacao-vazia").hidden = false;
  const foto = $("foto-captura");
  foto.getContext("2d").clearRect(0, 0, foto.width, foto.height);
  foto.width = foto.height = 0;
  foto.hidden = true;
  if (estado.ws && estado.ws.readyState === WebSocket.OPEN) estado.ws.send(JSON.stringify({ acao: "limpar" }));
  renderizarLista();
}

/* ------------------------------------------------------------------ painel do monitor (RF04, RF14, RF17) */
async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, { ...opcoes, headers: { "Content-Type": "application/json", "X-Monitor-Pin": estado.pin || "", ...(opcoes.headers || {}) } });
  if (r.status === 401) { estado.pin = null; mostrarPin(); throw new Error("PIN inválido"); }
  if (!r.ok) throw new Error(`Erro ${r.status}`);
  return r;
}

function mostrarPin() {
  $("form-pin").hidden = false;
  $("monitor-conteudo").hidden = true;
  $("pin").value = "";
  setTimeout(() => $("pin").focus(), 50);
}

const camposAjuste = {
  confianca_minima: ["aj-confianca", "out-confianca", (v) => pct(v)],
  janela_quadros: ["aj-janela", "out-janela", (v) => v],
  proporcao_estavel: ["aj-proporcao", "out-proporcao", (v) => pct(v)],
  fps_max_deteccao: ["aj-fps", "out-fps", (v) => v],
  fps_durante_llm: ["aj-fps-llm", "out-fps-llm", (v) => v],
  max_palavras: ["aj-palavras", "out-palavras", (v) => v],
  temperatura_llm: ["aj-temp", "out-temp", (v) => Number(v).toFixed(2)],
  semelhanca_minima: ["aj-semelhanca", "out-semelhanca", (v) => pct(v)],
  limiar_candidatos: ["aj-candidatos", "out-candidatos", (v) => pct(v)],
  confianca_nome: ["aj-nome", "out-nome", (v) => pct(v)],
  quadros_ensino: ["aj-ensino", "out-ensino", (v) => v],
};
const checksAjuste = { incluir_pessoas: "aj-pessoas", aprendizado_ativo: "aj-aprendizado", exigir_aprovacao: "aj-aprovacao",
  reconhecer_com_clip: "aj-clip" };

async function carregarAjustes() {
  const a = await (await api("/api/ajustes")).json();
  for (const [chave, [inp, out, fmt]] of Object.entries(camposAjuste)) {
    $(inp).value = a[chave];
    $(out).textContent = fmt(a[chave]);
  }
  for (const [chave, id] of Object.entries(checksAjuste)) $(id).checked = a[chave];
  carregarListaAprendizado();
}

let temporizadorSalvar = null;
function salvarAjustes() {
  clearTimeout(temporizadorSalvar);
  temporizadorSalvar = setTimeout(async () => {
    const corpo = {};
    for (const [chave, id] of Object.entries(checksAjuste)) corpo[chave] = $(id).checked;
    for (const [chave, [inp]] of Object.entries(camposAjuste)) corpo[chave] = Number($(inp).value);
    try {
      await api("/api/ajustes", { method: "POST", body: JSON.stringify(corpo) });
      $("monitor-msg").textContent = "Ajustes salvos.";
      atualizarStatus();
    } catch (e) { $("monitor-msg").textContent = `Falha ao salvar: ${e.message}`; }
  }, 250);
}

async function carregarListaAprendizado() {
  const ul = $("lista-aprendizado");
  let dados;
  try { dados = await (await api("/api/aprendizado")).json(); } catch { return; }
  ul.innerHTML = "";
  if (!dados.exemplos.length) {
    const li = document.createElement("li"); li.textContent = "Nenhuma correção registrada ainda."; ul.appendChild(li); return;
  }
  for (const e of dados.exemplos) {
    const li = document.createElement("li");
    if (!e.aprovado) li.className = "pendente";
    const info = document.createElement("div");
    const t = document.createElement("strong"); t.textContent = e.rotulo;
    const sub = document.createElement("small");
    sub.textContent = `${e.classe_original ? "detector disse “" + e.classe_original + "” · " : ""}${e.criado_em} · usado em ${e.vezes_reconhecido} quadros${e.aprovado ? "" : " · AGUARDANDO APROVAÇÃO"}`;
    info.append(t, sub);
    const botoes = document.createElement("div"); botoes.className = "botoes";
    if (!e.aprovado) {
      const ap = document.createElement("button"); ap.className = "botao pequeno primario"; ap.textContent = "Aprovar";
      ap.addEventListener("click", async () => { await api(`/api/aprendizado/${e.id}/aprovar`, { method: "POST" }).catch(() => {}); carregarListaAprendizado(); atualizarStatus(); });
      botoes.appendChild(ap);
    }
    const rm = document.createElement("button"); rm.className = "botao pequeno perigo"; rm.textContent = "Apagar";
    rm.addEventListener("click", async () => { await api(`/api/aprendizado/${e.id}`, { method: "DELETE" }).catch(() => {}); carregarListaAprendizado(); atualizarStatus(); carregarRotulos(); });
    botoes.appendChild(rm);
    li.append(info, botoes);
    ul.appendChild(li);
  }
}

function caixaDiag(rotulo, valor) {
  const d = document.createElement("div");
  const s = document.createElement("small"); s.textContent = rotulo;
  const b = document.createElement("strong"); b.textContent = valor;
  d.append(s, b);
  return d;
}

async function atualizarDiagnostico() {
  if (!$("monitor").open || !estado.pin) return;
  const s = estado.statusServidor || { llm: {}, detector: {} };
  let m = null;
  try { m = await (await api("/api/metricas")).json(); } catch { /* ignorado */ }
  const fmt = (x) => (x == null ? "—" : `${Math.round(x)} ms`);
  const serie = (k) => (m && m.series[k] && m.series[k].n ? m.series[k] : null);
  const inf = serie("inferencia_ms"), llmT = serie("llm_total_ms"), fpsS = serie("fps_deteccao"), tok = serie("llm_primeiro_token_ms");
  const d = $("diag");
  d.innerHTML = "";
  d.append(
    caixaDiag("FPS da prévia (vídeo)", estado.diag.fpsVideo.toFixed(1)),
    caixaDiag("FPS da detecção", `${estado.diag.fpsDeteccao.toFixed(1)}${fpsS ? ` (méd ${fpsS.media})` : ""}`),
    caixaDiag("Inferência do detector", `${fmt(estado.diag.inferenciaMs)}${inf ? ` (méd ${Math.round(inf.media)}, máx ${Math.round(inf.maximo)})` : ""}`),
    caixaDiag("Detector executa em", `${estado.diag.dispositivo || s.detector.dispositivo || "—"}${s.detector.threads ? ` (${s.detector.threads} núcleos)` : ""}`),
    caixaDiag("Detecção desacelerada p/ a LLM", estado.diag.economia ? "sim, IA respondendo" : "não"),
    caixaDiag("Tempo total da LLM", llmT ? `méd ${(llmT.media / 1000).toFixed(1)} s · máx ${(llmT.maximo / 1000).toFixed(1)} s` : "—"),
    caixaDiag("LLM: 1ª palavra", tok ? `méd ${(tok.media / 1000).toFixed(1)} s` : "—"),
    caixaDiag("LLM executa em", `${s.llm.dispositivo || "—"}${s.detector.threads_llm && s.llm.dispositivo !== "GPU" ? ` (${s.detector.threads_llm} núcleos)` : ""}`),
    caixaDiag("Modelo da LLM", s.llm.modelo || "—"),
    caixaDiag("Respostas da LLM medidas", llmT ? llmT.n : 0),
    caixaDiag("CLIP (nome + exemplos)", estado.diag.aprendizado
      ? `${Math.round(estado.diag.aprendizado.ms)} ms · ${estado.diag.aprendizado.recalculados || 0} recortes`
      : (s.reconhecedor && s.reconhecedor.ativo ? "—" : "desligado")),
    caixaDiag("Base de objetos", s.reconhecedor ? `${s.reconhecedor.objetos_na_base} objetos` : "—"),
    caixaDiag("Semelhança mais alta agora", estado.diag.aprendizado && estado.diag.aprendizado.semelhanca_max != null
      ? `${pct(estado.diag.aprendizado.semelhanca_max)} (${estado.diag.aprendizado.rotulo_proximo})` : "—"),
  );
}

function configurarMonitor() {
  const dlg = $("monitor");
  $("abrir-monitor").addEventListener("click", () => {
    dlg.showModal();
    if (estado.pin) { $("form-pin").hidden = true; $("monitor-conteudo").hidden = false; carregarAjustes().catch(() => {}); listarCameras(); atualizarDiagnostico(); }
    else mostrarPin();
  });
  $("fechar-monitor").addEventListener("click", () => dlg.close());
  $("form-pin").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    estado.pin = $("pin").value;
    try {
      await api("/api/monitor/entrar", { method: "POST" });
      $("erro-pin").hidden = true;
      $("form-pin").hidden = true;
      $("monitor-conteudo").hidden = false;
      await carregarAjustes();
      listarCameras();
      atualizarDiagnostico();
    } catch { $("erro-pin").hidden = false; }
  });
  for (const [, [inp, out, fmt]] of Object.entries(camposAjuste)) {
    $(inp).addEventListener("input", () => { $(out).textContent = fmt($(inp).value); salvarAjustes(); });
  }
  for (const id of Object.values(checksAjuste)) $(id).addEventListener("change", salvarAjustes);
  $("exportar-aprendizado").addEventListener("click", async () => {
    try {
      const blob = await (await api("/api/aprendizado/exportar")).blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `aprendizado-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) { $("monitor-msg").textContent = e.message; }
  });
  $("importar-aprendizado").addEventListener("click", () => $("arquivo-aprendizado").click());
  $("arquivo-aprendizado").addEventListener("change", async (ev) => {
    const f = ev.target.files[0];
    ev.target.value = "";
    if (!f) return;
    try {
      const r = await api("/api/aprendizado/importar", { method: "POST", body: await f.text() });
      const c = await r.json();
      $("monitor-msg").textContent = `${c.importados} correções importadas.`;
    } catch (e) { $("monitor-msg").textContent = `Falha ao importar: ${e.message}`; }
    carregarListaAprendizado(); atualizarStatus(); carregarRotulos();
  });
  $("esquecer-aprendizado").addEventListener("click", async () => {
    if (!confirm("Apagar tudo o que a IA aprendeu com os visitantes? Isso não pode ser desfeito.")) return;
    await api("/api/aprendizado/esquecer", { method: "POST" }).catch(() => {});
    $("monitor-msg").textContent = "Aprendizado apagado.";
    carregarListaAprendizado(); atualizarStatus(); carregarRotulos();
  });
  $("sel-camera").addEventListener("change", (ev) => {
    estado.cameraId = ev.target.value;
    localStorageSet("cameraId", estado.cameraId);
    iniciarCamera();
  });
  $("espelhar").checked = estado.espelhar;
  $("espelhar").addEventListener("change", (ev) => {
    estado.espelhar = ev.target.checked;
    localStorageSet("espelhar", estado.espelhar ? "1" : "0");
    $("video").classList.toggle("espelhado", estado.espelhar);
  });
  $("exportar-metricas").addEventListener("click", async () => {
    try {
      const r = await api("/api/metricas/exportar");
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `metricas-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (e) { $("monitor-msg").textContent = e.message; }
  });
  $("zerar-metricas").addEventListener("click", async () => {
    await api("/api/metricas/limpar", { method: "POST" }).catch(() => {});
    $("monitor-msg").textContent = "Métricas zeradas.";
    atualizarDiagnostico();
  });
  $("limpar-logs").addEventListener("click", async () => {
    if (!confirm("Apagar os logs técnicos? (RNF09: limpar após o evento)")) return;
    await api("/api/logs/limpar", { method: "POST" }).catch(() => {});
    $("monitor-msg").textContent = "Logs técnicos apagados.";
  });
  $("restaurar-ajustes").addEventListener("click", async () => {
    await api("/api/ajustes/restaurar", { method: "POST" }).catch(() => {});
    await carregarAjustes();
    $("monitor-msg").textContent = "Ajustes padrão restaurados.";
    atualizarStatus();
  });
  $("reiniciar-componentes").addEventListener("click", reiniciarComponentes);
}

async function reiniciarComponentes() {
  definirAlerta("captura", null);
  await fetch("/api/reiniciar-componentes", { method: "POST" }).catch(() => {});
  if (estado.ws) { try { estado.ws.close(); } catch { /* ignorado */ } }
  if (!estado.pausado) iniciarCamera();
  atualizarStatus();
}

/* ------------------------------------------------------------------ início */
function iniciar() {
  $("video").classList.toggle("espelhado", estado.espelhar);
  $("capturar").addEventListener("click", capturarCena);
  $("ensinar-novo").addEventListener("click", abrirEnsinarNovo);
  carregarRotulos();
  $("nova").addEventListener("click", novaDemonstracao);
  $("pausar").addEventListener("click", alternarPausa);
  $("alerta-reiniciar").addEventListener("click", reiniciarComponentes);
  $("formulario").addEventListener("submit", (ev) => { ev.preventDefault(); perguntar($("pergunta").value); });
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => perguntar(c.textContent)));
  configurarMonitor();
  renderizarLista();
  atualizarStatus();
  setInterval(atualizarStatus, 3000);
  setInterval(atualizarDiagnostico, 2000);
  conectarWs();
  iniciarCamera();
  requestAnimationFrame(laco);
  window.addEventListener("beforeunload", pararCamera); // CA01: libera a câmera ao fechar
  $("ensino-concluir").addEventListener("click", () => {
    if (estado.ws && estado.ws.readyState === WebSocket.OPEN) estado.ws.send(JSON.stringify({ acao: "concluir_ensino" }));
    else finalizarEnsino({ coletados: 0 });
  });
}

iniciar();
