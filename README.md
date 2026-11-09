# Visão Computacional com IA Local

Demonstração interativa do **Bacharelado em Inteligência Artificial da UniEvangélica**.

Você mostra um objeto para a webcam, e o sistema:

1. **encontra o objeto** na imagem com um detector de objetos (YOLO);
2. **explica em português** o que foi visto, usando uma IA de linguagem (Llama 3.2) que roda no próprio computador;
3. **responde perguntas** do visitante sobre a cena;
4. **aprende com os erros**: se a IA errar o nome do objeto, o visitante corrige e ela passa a acertar.

Tudo funciona **sem internet** depois da primeira instalação. Nenhuma imagem é enviada para fora do computador nem gravada.

> **Você só precisa instalar um programa: o Docker Desktop.** Python, bibliotecas e modelos de IA são baixados e configurados automaticamente dentro do Docker. Não é preciso saber programar para instalar e usar.

---

## Sumário

- [Resumo rápido (para quem tem pressa)](#resumo-rápido-para-quem-tem-pressa)
- [Parte 1 · Instalação passo a passo](#parte-1--instalação-passo-a-passo)
  - [Passo 1 · Conferir o computador](#passo-1--conferir-o-computador)
  - [Passo 2 · Instalar o Docker Desktop](#passo-2--instalar-o-docker-desktop)
  - [Passo 3 · Baixar este projeto](#passo-3--baixar-este-projeto)
  - [Passo 4 · Preparar (uma única vez, com internet)](#passo-4--preparar-uma-única-vez-com-internet)
  - [Passo 5 · Usar no dia a dia (sem internet)](#passo-5--usar-no-dia-a-dia-sem-internet)
  - [Passo 6 · Encerrar](#passo-6--encerrar)
- [Parte 2 · Como usar a demonstração](#parte-2--como-usar-a-demonstração)
- [Parte 3 · Como funciona por dentro (para as aulas)](#parte-3--como-funciona-por-dentro-para-as-aulas)
- [Parte 4 · Configurações avançadas](#parte-4--configurações-avançadas)
- [Parte 5 · Problemas comuns e soluções](#parte-5--problemas-comuns-e-soluções)
- [Parte 6 · Para desenvolvedores](#parte-6--para-desenvolvedores)

---

## Resumo rápido (para quem tem pressa)

| | Windows | macOS / Linux |
|---|---|---|
| 1. Instale e **abra** o Docker Desktop | [docker.com](https://www.docker.com/products/docker-desktop/) | [docker.com](https://www.docker.com/products/docker-desktop/) |
| 2. Baixe este projeto | **Code → Download ZIP** e extraia | `git clone https://github.com/jefersonsilvaaraujo/visao-computacional.git` |
| 3. Prepare (só na 1ª vez, com internet) | duplo clique em **`1-preparar.bat`** | `bash 1-preparar.sh` |
| 4. Use (funciona sem internet) | duplo clique em **`2-iniciar.bat`** | `bash 2-iniciar.sh` |
| 5. Encerre | duplo clique em **`3-parar.bat`** | `bash 3-parar.sh` |

O sistema abre no navegador em **<http://localhost:8080>**. Quando o navegador perguntar, **permita o uso da câmera**.

Se algo der errado, veja a [Parte 5](#parte-5--problemas-comuns-e-soluções). O resto deste documento explica cada passo com calma.

---

## Parte 1 · Instalação passo a passo

### Passo 1 · Conferir o computador

| Item | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10/11 (64 bits), macOS 12+ ou Linux | Windows 11 |
| Memória RAM | 8 GB | 16 GB ou mais |
| Espaço livre em disco | 15 GB | 20 GB |
| Webcam | integrada ou USB | USB com boa resolução |
| Placa de vídeo | não é obrigatória | NVIDIA (ex.: RTX 4050), que deixa as respostas da IA bem mais rápidas |
| Internet | só na preparação, para baixar cerca de 7 GB | — |
| Navegador | Chrome, Edge ou Firefox atualizado | Chrome ou Edge |

> **Windows:** a "virtualização" precisa estar ativada no computador. Na maioria dos notebooks ela já vem ativada. Para conferir: abra o **Gerenciador de Tarefas** (Ctrl + Shift + Esc) → aba **Desempenho** → **CPU** → deve aparecer **Virtualização: Habilitado**. Se estiver desabilitado, é preciso ativar na BIOS do computador; procure "ativar virtualização" + o modelo do seu notebook.

### Passo 2 · Instalar o Docker Desktop

O Docker é o programa que "empacota" todo o sistema e faz ele funcionar igual em qualquer computador.

#### No Windows

1. Acesse <https://www.docker.com/products/docker-desktop/> e clique em **Download for Windows**.
2. Execute o instalador baixado (`Docker Desktop Installer.exe`).
3. Na tela de opções, deixe marcado **Use WSL 2 instead of Hyper-V** (recomendado) e clique em **OK**.
4. Ao terminar, **reinicie o computador**.
5. Abra o **Docker Desktop** pelo menu Iniciar. Na primeira vez:
   - aceite os termos de uso;
   - o login é **opcional**: pode clicar em *Skip* / *Continue without signing in*;
   - se aparecer um aviso pedindo para atualizar o **WSL**, siga as instruções da tela (normalmente é só clicar em atualizar ou rodar `wsl --update` no PowerShell) e abra o Docker Desktop de novo.
6. Espere até aparecer **Engine running** (com um indicador verde) no canto inferior esquerdo da janela do Docker Desktop.

**Para conferir se deu certo:** abra o **PowerShell** (menu Iniciar → digite "PowerShell") e rode:

```bash
docker --version
```

Se aparecer `Docker version` seguido de um número, está tudo certo.

#### No macOS

1. Acesse <https://www.docker.com/products/docker-desktop/> e baixe a versão do seu Mac:
   - **Apple Silicon** (M1, M2, M3, M4…) ou
   - **Intel**.

   Para saber qual é o seu: menu da Apple (canto superior esquerdo) → **Sobre Este Mac** → linha "Chip" ou "Processador".
2. Abra o arquivo `.dmg` e arraste o Docker para a pasta **Aplicativos**.
3. Abra o Docker pela pasta Aplicativos, aceite os termos e espere aparecer **Engine running**.

> No Mac a IA roda só no processador, porque o Docker não usa a GPU do Mac. Funciona bem, só um pouco mais devagar.

#### No Linux (Ubuntu e similares)

Instale o Docker Engine com o plugin Compose seguindo o guia oficial: <https://docs.docker.com/engine/install/>. Depois, para usar o Docker sem `sudo`:

```bash
sudo usermod -aG docker $USER
```

Saia e entre de novo na sessão para a mudança valer.

### Passo 3 · Baixar este projeto

Escolha **uma** das opções.

**Opção A: baixar o ZIP (mais simples, sem instalar nada)**

1. No topo desta página do GitHub, clique no botão verde **Code** → **Download ZIP**.
2. Encontre o arquivo `visao-computacional-main.zip` na pasta **Downloads**.
3. Clique com o botão direito → **Extrair tudo…** (Windows) ou dê duplo clique (Mac).
4. Mova a pasta extraída para um lugar fácil, como a **Área de Trabalho** ou **Documentos**.

> **Windows:** extraia o ZIP antes de usar. Não rode os scripts de dentro do ZIP.

**Opção B: usar o Git (para quem já usa)**

```bash
git clone https://github.com/jefersonsilvaaraujo/visao-computacional.git
```

### Passo 4 · Preparar (uma única vez, com internet)

Esta etapa baixa tudo o que o sistema precisa: detector YOLO, modelo de IA de linguagem e bibliotecas. **Ela só precisa ser feita uma vez por computador.**

⏱ Leva de **15 a 40 minutos**, dependendo da internet. Use uma conexão boa: são cerca de 7 GB.

1. Confira se o **Docker Desktop está aberto** e mostrando *Engine running*.
2. Abra a pasta do projeto e:
   - **Windows:** dê **duplo clique** em **`1-preparar.bat`**.
   - **macOS/Linux:** abra o Terminal na pasta do projeto e rode:

     ```bash
     bash 1-preparar.sh
     ```

3. Uma janela preta (terminal) vai mostrar o progresso em 3 etapas:
   - **[1/3] Construindo a imagem da aplicação**: a parte mais demorada. Muitas linhas vão passar na tela, e isso é normal.
   - **[2/3] Iniciando os containers.**
   - **[3/3] Baixando o modelo de linguagem**: uma barra de progresso de cerca de 2 GB.
4. No fim, o navegador abre sozinho em **<http://localhost:8080>** e a janela mostra **"Preparação concluída!"**.
5. O navegador vai perguntar se o site pode usar a câmera: clique em **Permitir**.

> **Windows: apareceu "O Windows protegeu o computador"?** Isso acontece com arquivos baixados da internet. Clique em **Mais informações** → **Executar assim mesmo**. O script apenas executa comandos do Docker; você pode abrir o `.bat` no Bloco de Notas para conferir.

**Como saber se deu certo:** no topo da página aparecem três indicadores. Os três precisam ficar **verdes**:

| Indicador | Verde significa |
|---|---|
| **Câmera** · ativa | a webcam foi liberada pelo navegador |
| **Detector** · pronto | o YOLO está funcionando |
| **IA local** · pronta | a IA de linguagem foi carregada (na primeira vez pode levar até 1 minuto) |

Mostre uma garrafa, um celular ou um livro para a câmera: deve aparecer uma caixa azul com o nome do objeto.

### Passo 5 · Usar no dia a dia (sem internet)

Depois da preparação, **não é mais preciso internet**.

1. Abra o **Docker Desktop** e espere o *Engine running*.
2. Dê duplo clique em **`2-iniciar.bat`** (Windows) ou rode `bash 2-iniciar.sh` (macOS/Linux).
3. O navegador abre em <http://localhost:8080>.

Dicas para o evento:
- Aperte **F11** para deixar o navegador em tela cheia.
- Se o sistema já estiver aberto e você fechar o navegador sem querer, é só abrir <http://localhost:8080> de novo.

### Passo 6 · Encerrar

- **`3-parar.bat`** (ou `bash 3-parar.sh`): desliga o sistema. Os modelos baixados e o que a IA aprendeu **continuam salvos** para a próxima vez.
- **`4-limpar-dados-do-evento.bat`** (ou `bash 4-limpar-dados-do-evento.sh`): use depois do evento para apagar os registros técnicos. O script pergunta se você também quer apagar o que a IA aprendeu com os visitantes.

---

## Parte 2 · Como usar a demonstração

### Roteiro com o visitante (2 a 3 minutos)

1. **Mostrar um objeto** comum para a câmera: caneta, marca-texto, estojo, mouse, garrafa, caneca, celular, livro, tesoura, banana… São 160 objetos na [base](#ampliar-a-base-de-objetos). Evite documentos ou qualquer dado pessoal.
2. **Observar** a caixa ao redor do objeto, com o nome em português e a **confiança** em porcentagem.
3. Clicar em **📸 Capturar cena**. As detecções ficam "congeladas" e a IA escreve uma explicação curta em duas partes:
   - **📷 Observação da câmera**: o que o detector viu (fato);
   - **📚 Conhecimento geral**: para que esse tipo de objeto costuma servir.
4. **Fazer perguntas** digitando ou clicando nas sugestões: *O que você identificou?*, *Para que serve este objeto?*, *Qual é a marca do objeto?*
   A última é ótima para mostrar os limites da IA: ela responde que **não consegue saber a marca**, porque o detector só informa a classe do objeto.
5. **Se a IA errou o nome** (por exemplo, chamou um marca-texto de "taco de beisebol"):
   - clique em **✏️ Está errado? Corrigir**, digite o nome certo e clique em **🧠 Ensinar a IA**;
   - se a IA nem encontrou o objeto, use **➕ A IA não viu meu objeto: ensinar**;
   - aparece uma barra roxa sobre o vídeo: **mostre o objeto e gire devagar por alguns segundos**. A IA guarda o objeto em vários ângulos (até 12) e a barra some sozinha;
   - tire o objeto da frente da câmera e mostre de novo, em qualquer posição: agora a caixa fica **roxa**, com o selo **aprendido**.
6. Clicar em **↺ Nova demonstração** antes do próximo visitante. Isso apaga a explicação, as perguntas e a captura anterior.

### Botões do monitor (acadêmico que conduz a demonstração)

| Botão | Para que serve |
|---|---|
| **⏸ Pausar demonstração** | Desliga a câmera (a luz da webcam apaga). **▶ Retomar** liga de novo. |
| **↺ Nova demonstração** | Limpa tudo para o próximo visitante. |
| **Tentar novamente** | Aparece na faixa vermelha quando algo falha. Reabre a câmera e reconecta os componentes. |

### Painel do responsável técnico (botão ⚙ no canto superior direito)

O painel pede um **PIN**. O padrão é **`2026`**, e é bom trocar antes do evento (veja a [Parte 4](#parte-4--configurações-avançadas)).

| Seção | O que dá para fazer |
|---|---|
| **Diagnóstico** | Ver FPS do vídeo e da detecção, tempo de resposta da IA e se ela está usando **CPU** ou **GPU**. |
| **Câmera** | Escolher outra webcam (USB) e espelhar ou não a imagem. |
| **Detecção e reconhecimento** | Ligar/desligar o CLIP (bom para comparar com o YOLO sozinho em aula), a *certeza mínima do nome* (padrão 35%), a confiança mínima do YOLO (padrão 50%), a estabilidade da lista, o FPS máximo e mostrar ou ocultar a classe "pessoa". |
| **Aprendizado com os visitantes** | Ligar/desligar as correções, exigir aprovação do monitor, a semelhança mínima (padrão 75%), quantos ângulos coletar depois de cada correção, ver, aprovar ou apagar cada correção, e exportar ou importar o que foi aprendido. |
| **IA local** | Tamanho máximo das respostas e "criatividade" (temperatura). |
| **Ações** | Exportar métricas de desempenho, limpar logs, restaurar os ajustes padrão. |

O roteiro de testes de aceitação (CA01 a CA12), com tabelas para preencher, está em [docs/roteiro-de-testes.md](docs/roteiro-de-testes.md).

---

## Parte 3 · Como funciona por dentro (para as aulas)

### O caminho de uma imagem

```
  NAVEGADOR (http://localhost:8080)                      DOCKER (no mesmo computador)
 ┌────────────────────────────────────┐            ┌──────────────────────────────────────┐
 │ 1. a webcam capta o vídeo          │  quadros   │ 2. LOCALIZADOR (YOLO11n)             │
 │                                    │ ─────────▶ │    acha as regiões com objetos       │
 │                                    │            │ 2b. RECONHECEDOR (CLIP)              │
 │                                    │            │    dá o nome usando a base de 160    │
 │                                    │            │    objetos e os exemplos ensinados   │
 │ 4. desenha as caixas sobre o vídeo │ ◀───────── │                                      │
 │                                    │  caixas    │ 3. ESTABILIZADOR                     │
 │                                    │            │    junta vários quadros para a lista │
 │ 5. "Capturar cena"                 │  só texto  │    não ficar "piscando"              │
 │    (detecções congeladas)          │ ─────────▶ │ 6. REGRAS + IA DE LINGUAGEM          │
 │ 8. mostra explicação e respostas   │ ◀───────── │    (Llama 3.2 3B no Ollama)          │
 └────────────────────────────────────┘            │ 7. escreve a explicação em português │
                                                   └──────────────────────────────────────┘
```

Pontos que valem a pena discutir com os alunos:

- **Visão e linguagem são etapas separadas.** A IA de linguagem **nunca vê a imagem**. Ela recebe só um texto como este:

  ```json
  {"objetos": [{"classe": "garrafa", "confianca": 0.82, "quantidade": 1}]}
  ```

  Por isso ela não sabe cor, marca ou o que está escrito no objeto, e o sistema é programado para admitir isso.
- **Confiança não é certeza.** "82%" é uma estimativa do modelo, não uma probabilidade garantida. Por isso o sistema nunca mostra 100%. Objetos fora da base podem receber nomes errados, e é aí que entra o aprendizado.
- **Regras de segurança.** Pedidos para identificar pessoas, perguntas sobre marca ou cor e tentativas de "enganar" a IA ("ignore as instruções…") recebem respostas fixas, programadas sem passar pela IA.
- **Por que a câmera é aberta pelo navegador?** O Docker no Windows e no Mac não consegue acessar a webcam diretamente. Então o navegador capta a imagem e manda os quadros para o detector, que roda no mesmo computador.
- **Privacidade.** Os quadros ficam só na memória enquanto são analisados. Nada é gravado, e nada sai do computador.

### Duas IAs para reconhecer: uma acha, a outra dá o nome

O detector **YOLO11n** foi treinado com as **80 classes do conjunto COCO**: garrafa, celular, mouse, tesoura, livro… Caneta, marca-texto, lápis, borracha, régua, estojo, carteira e fone de ouvido **não estão lá**. Por isso, sozinho, ele chamava um marca-texto de "taco de beisebol". Mas ele costuma achar **onde** o objeto está, mesmo errando o nome.

Por isso o reconhecimento tem duas etapas:

1. O **YOLO localiza**: devolve caixas, inclusive as de confiança baixa (a partir de 5%).
2. O **CLIP dá o nome**. Ele é um modelo treinado com milhões de pares imagem + legenda e transforma cada recorte em uma lista de 512 números (*embedding*). O sistema compara essa lista com as listas geradas a partir dos **nomes da base de objetos** (`app/vocabulario.json`, 160 objetos) e escolhe o mais parecido. Isso se chama classificação ***zero-shot***: o CLIP nunca foi treinado especificamente para "marca-texto", só aprendeu a relacionar imagens e textos.

Medimos as duas abordagens com 160 fotos de 20 objetos do dia a dia de sala de aula:

| Abordagem | Acertou o nome | Velocidade |
|---|---|---|
| Só o YOLO11n (versão anterior) | 18% | ~24 quadros/s |
| Detectores de "vocabulário aberto" (YOLO-World, YOLOE) | 19% a 25% | 2 a 4 quadros/s |
| **YOLO localiza + CLIP dá o nome (atual)** | **58%** | ~15 quadros/s |

Para não pesar, o CLIP não roda em todo quadro: se uma caixa quase não se mexeu, o nome calculado há menos de 0,5 s é reaproveitado.

Um bom exercício para os alunos é desligar o CLIP no painel ⚙ e comparar os nomes que aparecem.

### Como a IA "aprende" com as correções

Este recurso mostra na prática que **modelos de IA erram** e que existem formas de corrigi-los sem treinar tudo de novo.

1. Quando o visitante corrige um nome, o recorte do objeto passa pelo **CLIP** e vira uma lista de **512 números**, o *embedding* ou "impressão digital visual".
2. O sistema guarda esses números e o nome correto. **A imagem é descartada.** Para tolerar mudanças de luz e enquadramento, ele guarda 8 versões do recorte: espelhado, mais perto, mais longe, mais claro, mais escuro…
3. **Ensino com vários ângulos:** logo depois da correção, o visitante gira o objeto na frente da câmera. O sistema acompanha o objeto (procura, em cada quadro, a caixa mais parecida com o que foi ensinado) e guarda até 12 ângulos diferentes, descartando os repetidos.
4. A partir daí, cada objeto que aparece na câmera também vira uma lista de 512 números, que é comparada com as guardadas (**similaridade do cosseno**).
5. Se for parecida o bastante (padrão: **75%** de semelhança), o nome ensinado substitui o do CLIP e do YOLO, e a caixa fica **roxa**. Os exemplos ensinados têm prioridade sobre a base.

No teste, um marca-texto ensinado uma vez, com a coleta de ângulos, foi reconhecido em **100% dos quadros** enquanto a imagem girava 6 voltas completas. Com a versão anterior, ele se perdia com pequenas variações.

Esse método se chama **classificação por vizinho mais próximo (k-NN)**. Nem o YOLO nem o CLIP são **re-treinados**, porque isso exigiria muitas imagens e horas de processamento. O que existe é uma "memória de exemplos" ao lado dele. A explicação da IA também deixa isso claro, por exemplo: *"reconhecido como marca-texto a partir de exemplos ensinados por visitantes (semelhança de 87%; o detector original sugeriu taco de beisebol)"*.

**Dicas para ensinar bem:**
- use fundo liso, boa luz e o objeto inteiro na tela;
- durante a barra roxa, **gire o objeto devagar** e mostre os dois lados;
- se ainda falhar em alguma posição, corrija de novo **nessa posição**: cada correção soma novos exemplos;
- se o nome ensinado aparecer em objetos errados, **aumente** a semelhança mínima no painel ⚙;
- se o objeto ensinado não for reconhecido, **diminua** a semelhança mínima.

O painel mostra a *semelhança mais alta agora* para ajudar a calibrar.

**Cuidados num evento público:**
- não é possível corrigir objetos da classe "pessoa";
- nomes com palavras ligadas a pessoas (rosto, idade…), palavrões comuns e comandos para a IA são recusados;
- o filtro **não reconhece qualquer nome próprio**. Para ter controle total, ligue **"Exigir aprovação do monitor"** no painel ⚙: assim cada correção só vale depois de aprovada.

**Levar o que foi aprendido para outro computador:** painel ⚙ → **Exportar aprendizado** (gera um arquivo `.json`) → no outro computador, **Importar aprendizado**.

### Quem faz o quê no computador

| Componente | Onde roda | Por quê |
|---|---|---|
| Localizador YOLO11n | processador (CPU) | é pequeno e rápido (~25 ms por quadro) |
| Reconhecedor CLIP ViT-B/32 | processador (CPU) | ~30 ms por objeto; reaproveita o nome de caixas paradas |
| IA de linguagem Llama 3.2 3B | placa de vídeo NVIDIA, se houver; senão, CPU | é o componente mais pesado |

Quando não há placa NVIDIA, os dois dividem o processador. Para um não atrasar o outro, cada um usa uma parte dos núcleos, e a detecção desacelera para 2 quadros por segundo enquanto a IA escreve. O vídeo continua fluido; só as caixas atualizam mais devagar nesse momento.

---

## Parte 4 · Configurações avançadas

### Trocar o PIN, a porta e outras opções

1. Na pasta do projeto, faça uma cópia do arquivo **`.env.example`** com o nome **`.env`**:
   - **Windows (PowerShell, dentro da pasta):** `copy .env.example .env`
   - **macOS/Linux:** `cp .env.example .env`
2. Abra o `.env` no Bloco de Notas (ou outro editor) e altere o que quiser.
3. Rode **`2-iniciar`** de novo para aplicar.

| Opção | Padrão | O que faz |
|---|---|---|
| `MONITOR_PIN` | `2026` | PIN do painel ⚙. **Troque antes do evento.** |
| `PORTA` | `8080` | Porta do endereço (`http://localhost:8080`). Mude se a 8080 já estiver em uso. |
| `LLM_MODELO` | `llama3.2:3b` | Modelo de IA de linguagem. Se trocar, rode `1-preparar` de novo (com internet). |
| `MODELO_YOLO` | `yolo11n` | Detector. `yolo11s` é mais preciso e mais lento. Se trocar, rode `1-preparar` de novo. |
| `THREADS_DETECTOR` | `0` | Núcleos do processador para o detector (0 = automático). |
| `LLM_THREADS` | `0` | Núcleos para a IA quando não há placa NVIDIA (0 = automático). |
| `FUSO_HORARIO` | `America/Sao_Paulo` | Fuso horário dos registros técnicos. |
| `OLLAMA_VERSAO` | `0.6.8` | Versão do Ollama, o servidor da IA de linguagem. |

### Ampliar a base de objetos

A lista de objetos que o CLIP sabe nomear fica em **`app/vocabulario.json`**. Para incluir um objeto, acrescente um bloco como este dentro de `"objetos"`:

```json
{
 "rotulo": "apagador",
 "ingles": ["whiteboard eraser", "chalkboard eraser"],
 "descricao": "Objeto usado para apagar o quadro."
}
```

- **`rotulo`**: o nome que aparece na tela, em português.
- **`ingles`**: um ou mais termos em inglês. O CLIP foi treinado em inglês, e termos específicos funcionam melhor ("whiteboard eraser" em vez de "eraser").
- **`descricao`**: frase curta usada quando a IA de linguagem está indisponível.

Depois de salvar, rode **`1-preparar`** de novo, com internet. Ele recalcula os vetores dos nomes, em cerca de 1 minuto se o resto já estiver baixado.

> Para objetos muito específicos (o mascote da turma, um protótipo), use o botão **Corrigir** na demonstração: o ensino por exemplos funciona melhor do que um nome genérico na base.

### Usar a placa de vídeo NVIDIA (Windows)

Os scripts detectam a placa NVIDIA **automaticamente**. Para que funcione:

1. Instale o driver mais recente da NVIDIA: <https://www.nvidia.com/pt-br/drivers/>.
2. Confira no PowerShell:

   ```bash
   nvidia-smi
   ```

   Deve aparecer uma tabela com o nome da placa.
3. No Docker Desktop, em **Settings → General**, deixe marcado **Use the WSL 2 based engine**.
4. Rode `2-iniciar.bat`. A janela mostra **"GPU NVIDIA encontrada: a LLM vai usar a GPU."**
5. Confira no painel ⚙ → Diagnóstico: **LLM executa em: GPU**.

Se a GPU não funcionar dentro do Docker, o script avisa e inicia em modo CPU. Tudo continua funcionando, só mais devagar.

### Levar o sistema para um computador sem internet

Útil quando a máquina do evento não tem internet nem para a preparação. No computador **já preparado**, abra o terminal (PowerShell no Windows) na pasta do projeto e rode:

```bash
docker save visao-computacional-app:1.0 ollama/ollama:0.6.8 alpine -o imagens.tar
```

```bash
docker run --rm -v visao-computacional_modelos_ollama:/dados -v "${PWD}:/saida" alpine tar czf /saida/modelos.tgz -C /dados .
```

Copie a pasta do projeto, agora com `imagens.tar` e `modelos.tgz`, para um pendrive ou HD externo (cerca de 10 GB). No outro computador, com o Docker Desktop instalado e aberto, rode na pasta copiada:

```bash
docker load -i imagens.tar
```

```bash
docker run --rm -v visao-computacional_modelos_ollama:/dados -v "${PWD}:/entrada" alpine tar xzf /entrada/modelos.tgz -C /dados
```

Pronto: o `2-iniciar` já funciona nesse computador. Se o primeiro comando reclamar que a imagem `alpine` não existe, rode antes `docker pull alpine`, ainda no computador com internet.

---

## Parte 5 · Problemas comuns e soluções

**Ao instalar ou iniciar**

| O que aparece | O que fazer |
|---|---|
| "O Docker não está em execução" | Abra o Docker Desktop e espere **Engine running**. Depois rode o script de novo. |
| Docker Desktop pede para atualizar o WSL | No PowerShell: `wsl --update`. Depois reinicie o computador. |
| "Virtualization support not detected" | Ative a virtualização na BIOS (veja o [Passo 1](#passo-1--conferir-o-computador)). |
| "O Windows protegeu o computador" ao abrir o `.bat` | **Mais informações → Executar assim mesmo**. |
| A preparação parou com erro no meio | Confira a internet e rode `1-preparar` de novo: ele continua de onde parou. |
| "Se for o primeiro uso, rode antes 1-preparar" | O `2-iniciar` não encontrou os arquivos baixados. Rode o `1-preparar` com internet. |
| "Porta 8080 já está em uso" (*port is already allocated*) | Outro programa usa a porta. Crie o `.env` com `PORTA=8090` e acesse `http://localhost:8090`. |

**Câmera**

| O que aparece | O que fazer |
|---|---|
| "Permissão da câmera negada" | Clique no ícone de câmera (ou cadeado) na barra de endereço → **Permitir** → **Tentar novamente**. |
| "A câmera está em uso por outro programa" | Feche Teams, Zoom, Meet, OBS ou o app Câmera do Windows. |
| "Nenhuma câmera encontrada" | Conecte a webcam e clique em **Tentar novamente**. Para trocar de câmera: painel ⚙ → Câmera. |
| A câmera não abre ao acessar pelo IP (ex.: `http://192.168…`) | O navegador só libera a câmera em `localhost`. Use sempre **`http://localhost:8080`** no próprio computador. |

**IA e detecção**

| O que aparece | O que fazer |
|---|---|
| "IA local: baixando modelo" | Primeiro uso: espere o download terminar (precisa de internet). |
| "IA local: carregando…" por alguns segundos | Normal ao iniciar: a IA está sendo carregada na memória. |
| "IA local indisponível" | Clique em **Tentar novamente** ou reinicie com `3-parar` + `2-iniciar`. A detecção continua funcionando, e as respostas usam textos prontos. |
| Respostas da IA muito lentas | Veja no painel ⚙ se a IA está em **CPU** ou **GPU**. Para usar a placa NVIDIA, veja a [Parte 4](#usar-a-placa-de-vídeo-nvidia-windows). Sem placa NVIDIA, diminua o *FPS da detecção enquanto a IA responde*. |
| O objeto não é reconhecido | Melhore a luz, aproxime o objeto e use um fundo liso. Se ele não estiver na base, [inclua na base](#ampliar-a-base-de-objetos) ou ensine pelo botão **Corrigir**. |
| A IA dá nomes errados a coisas do fundo | Painel ⚙ → aumente a *certeza mínima do nome* (ex.: 50%) ou a *confiança mínima das caixas que o CLIP analisa* (ex.: 10%). |
| A barra roxa do ensino termina sem coletar ângulos | O objeto precisa aparecer inteiro e próximo da câmera. Corrija de novo e mostre o objeto logo em seguida. |
| A IA "aprendeu" um nome que aparece em objetos errados | Painel ⚙ → aumente a *semelhança mínima* ou apague a correção na lista. |
| Detecção lenta (FPS baixo no painel) | Feche programas pesados ou reduza o *FPS máximo da detecção* no painel ⚙. Para comparar, desligue o CLIP no painel: só o YOLO é bem mais leve. |

**Ver os registros técnicos (para quem entende de terminal):**

```bash
docker compose logs -f app
```

---

## Parte 6 · Para desenvolvedores

### Estrutura do projeto

```
visao-computacional/
├── 1-preparar / 2-iniciar / 3-parar / 4-limpar-dados-do-evento   (.bat e .sh)
├── docker-compose.yml          serviços "app" e "ollama"
├── docker-compose.gpu.yml      complemento para GPU NVIDIA
├── .env.example                configurações opcionais
├── docs/roteiro-de-testes.md   critérios de aceitação CA01–CA12
├── Requisitos_Visao_Computacional_IA_Local.docx   documento de requisitos
├── scripts/                    funções auxiliares dos scripts
└── app/
    ├── Dockerfile              build em 2 etapas (exporta os modelos para ONNX)
    ├── vocabulario.json        base de objetos (nome em português, termos em inglês, descrição)
    ├── exportar_detector.py    baixa YOLO11n e CLIP, exporta para ONNX e calcula os vetores dos nomes
    ├── servidor/               backend em Python (FastAPI)
    │   ├── main.py             rotas HTTP/WebSocket e orquestração
    │   ├── detector.py         YOLO via ONNX Runtime (localiza as caixas)
    │   ├── reconhecimento.py   duas etapas (YOLO + CLIP), cache por caixa, ensino com vários ângulos
    │   ├── vocabulario.py      carrega a base de objetos
    │   ├── estabilizador.py    agregação temporal das detecções
    │   ├── aprendizado.py      CLIP (embeddings e nomes) + memória k-NN das correções
    │   ├── guardrails.py       regras determinísticas da IA (RB01–RB06)
    │   ├── llm.py              cliente do Ollama e prompt do sistema
    │   ├── classes_pt.py       80 classes COCO em português
    │   ├── config.py, metricas.py
    ├── static/                 interface web (HTML, CSS e JavaScript puros)
    └── tests/                  testes automáticos (pytest)
```

### Comandos úteis

```bash
docker compose up -d --build                                            # sobe em modo CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d    # sobe com GPU NVIDIA
docker compose run --rm --no-deps app python -m pytest -q -p no:cacheprovider tests   # testes
docker compose logs -f app                                              # registros
docker compose down                                                     # desliga
```

### Decisões de arquitetura

- **Câmera no navegador + WebSocket**, porque o Docker Desktop (Windows/macOS) não repassa webcams para containers. O navegador só libera a câmera em `localhost` ou HTTPS.
- **Modelos em ONNX.** O PyTorch é usado só no build. A imagem final tem cerca de 1,4 GB e funciona sem internet.
- **Reconhecimento em duas etapas (YOLO + CLIP zero-shot)** em vez de um detector de vocabulário aberto: nas medições, foi mais preciso (58% contra 19–25%) e 4 a 7 vezes mais rápido na CPU. Exemplos ensinados (k-NN sobre embeddings do CLIP) têm prioridade sobre a base; caixas do mesmo nome vizinhas ou contidas são unidas (ex.: tampa e corpo de um marca-texto).
- **Segurança:** o Ollama não publica nenhuma porta; a interface é publicada só em `127.0.0.1`. Logs técnicos nunca registram perguntas, respostas ou imagens.
- **Respostas críticas sem LLM:** cena sem objetos, perguntas sobre pessoas, marca ou cor e tentativas de *prompt injection* têm respostas determinísticas (`guardrails.py`). Depois de cada resposta da LLM, o sistema verifica se ela citou objetos que não estavam na captura.
- **Divisão de CPU:** núcleos reservados para cada componente, ONNX Runtime sem *spin-wait* e detecção a 2 FPS enquanto a LLM gera texto na CPU. Na medição, a resposta com a câmera ligada caiu de 162 s para 2,2 s.

### Rastreabilidade dos requisitos

| Requisito | Implementação |
|---|---|
| RF01 Inicialização | Indicadores do topo + `/api/status` |
| RF02 Captura | `getUserMedia` 640×480 no navegador, sem gravação (`static/app.js`) |
| RF03 Detecção | YOLO11n localiza + CLIP nomeia (`servidor/reconhecimento.py`); caixas, rótulo em português e % |
| RF04 Limiar | Painel ⚙, padrão 0,50 |
| RF05 Estabilidade | Janela temporal com histerese + NMS (`servidor/estabilizador.py`) |
| RF06 Congelamento | **Capturar cena**: "Congelado às HH:MM:SS" + miniatura só em memória |
| RF07 Explicação | Observação determinística + conhecimento geral da LLM (~80 palavras) |
| RF08 Perguntas | `/api/perguntar`, com contexto limitado à captura |
| RF09 Incerteza | Mensagem fixa quando nada atinge o limiar |
| RF10 Correção | Prompt restritivo + respostas fixas + verificação pós-resposta |
| RF11 Reinício | **Nova demonstração** limpa interface e agregador |
| RF12 Offline | Modelos dentro da imagem e em volume local; nenhum recurso externo na página |
| RF13 Erros | Mensagens específicas + **Tentar novamente** |
| RF14 Alternar câmera | Painel ⚙ → Câmera |
| RF15 Idioma | `app/vocabulario.json` (160 objetos) + `servidor/classes_pt.py` (80 classes COCO) |
| RF16 Modo demonstração | Perguntas sugeridas |
| RF17 Diagnóstico | Painel ⚙ (PIN) |
| RF18 Fallback | Descrições pré-definidas quando a LLM cai |
| RF19 Correção e aprendizado *(adicionado após a v1.0 do documento)* | **Corrigir** / **Ensinar** + ensino com vários ângulos + memória k-NN (`servidor/aprendizado.py`, `servidor/reconhecimento.py`) |
| RNF03 Disponibilidade | Reconexão automática da câmera e do WebSocket; `restart: unless-stopped` |
| RNF05 Privacidade | Quadros só em memória; o aprendizado guarda só vetores numéricos |
| RNF06 Segurança | Ollama sem porta publicada; app só em `127.0.0.1` |
| RNF08 Portabilidade | Este README + scripts |
| RNF09 Auditabilidade | Logs técnicos mínimos com rotação; script de limpeza |
| RB01–RB06 | `servidor/guardrails.py` + `PROMPT_SISTEMA` em `servidor/llm.py` |

> O documento de requisitos v1.0 deixava "aprendizagem de novas classes em tempo real" fora do escopo. O RF19 foi incluído depois, como recurso P1, e pode ser desligado no painel sem afetar o resto.

### Licença deste projeto

O código deste repositório é distribuído sob a **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)**. Escolhemos essa licença por compatibilidade com o Ultralytics YOLO, que também é AGPL-3.0.

Na prática:
- você pode **usar, estudar, modificar e redistribuir** o projeto livremente, inclusive em aulas e outros eventos;
- se distribuir uma versão modificada, ou disponibilizá-la para outras pessoas usarem **pela rede**, precisa publicar o código-fonte dessa versão também sob a AGPL-3.0, mantendo os créditos.

Os modelos de IA usados pelo sistema têm licenças próprias, listadas abaixo.

### Licenças dos componentes

Confira antes de redistribuir:

| Componente | Licença | Observação |
|---|---|---|
| Ultralytics YOLO11 (pesos e biblioteca, usados no build) | AGPL-3.0 | Distribuir software derivado exige código aberto sob AGPL ou licença comercial da Ultralytics |
| Llama 3.2 3B | Llama 3.2 Community License + Acceptable Use Policy | Ao redistribuir, exige o aviso "Built with Llama" |
| OpenCLIP · CLIP ViT-B/32 (pesos LAION-2B `laion2b_s34b_b79k`) | MIT | Pesos treinados no conjunto público LAION-2B; os autores recomendam uso em pesquisa e educação |
| Ollama · ONNX Runtime | MIT | |
| OpenCV | Apache 2.0 | |
| FastAPI · Uvicorn · httpx · Pydantic | MIT / BSD | |

**Built with Llama.**
