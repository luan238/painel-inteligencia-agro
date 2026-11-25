# 🌱 Agro Intel Agent — Inteligência de Mercado Agrícola automatizada e verificável

Agente **open source** que gera, sozinho e em horários fixos, o relatório de inteligência de mercado
(Soja, Milho/Sorgo/Trigo/DDGS, Algodão, Café & Pecuária, Macro/Câmbio/NDF) e publica o
`boletim_atual.json` que o painel **Germinare Market Intelligence Pro** (`index.html`) lê.

Roda de graça no **GitHub Actions**. O texto é escrito por uma **fila de IAs gratuitas**:
Groq → NVIDIA (Nemotron) → Google Gemini → OpenRouter. Quando uma bate o limite, o pedido passa para a
próxima; quando todas esgotam, tudo vai para a **IA local** (um modelo open source no Ollama, rodando
dentro do próprio GitHub, **sem chave e sem limite de chamadas**). Se toda IA falhar, o boletim sai com
texto automático. O boletim nunca deixa de sair, e nada é inventado.

---

## Como funciona

```
 fontes da sua lista ──► COLETORES ──► CONFERÊNCIA ──► HISTÓRICO ──► CÁLCULOS ─┐
 (APIs oficiais, tabelas,   (código)     faixa, salto,   data/          WTD, MTD,  │
  RSS, páginas de notícia)               defasagem,      historico.csv  NDF, spreads,
                                         divergência                    bandas σ   │
                                                                                   ▼
            painel (index.html) ◄── boletim_atual.json ◄── MONTAGEM ◄── IA ESCREVE O TEXTO
            relatorio_atual.md       (schema validado)    + checagem    + VERIFICADOR confere
                                                            final        cada número e link
```

### Por que dá para confiar (o que o Gemini não fazia)

| Problema no chat do Gemini | Como o agente resolve |
|---|---|
| A IA “lembrava” ou estimava cotações | **A IA não gera números.** Cotações vêm de código (API do BCB, ajustes da B3, tabelas das fontes) e ficam gravadas com fonte, link e horário em `data/historico.csv`. |
| Séries diárias inventadas (ex.: Boi subindo R$ 1,50 por dia, sem falhar) | `daily_history` sai do histórico real. Dia sem cotação fica **em branco**, e o painel não interpola mais. |
| Número errado no texto | O **verificador** extrai todo número do texto da IA e confere com os dados entregues. Se algum número não bate, a resposta volta para a IA com a lista de erros. Se ela insistir, o campo vira texto automático. |
| Link inventado | A IA só cita notícias por ID (`[N3]`). O código troca o ID pelo link real, coletado da fonte. Antes de publicar, o sistema confere que **todos** os links vieram da coleta. |
| Leitura errada de um site (centavos × dólares, coluna errada) | Faixa plausível, limite de variação diária, defasagem máxima e **checagem cruzada entre fontes**. Valor suspeito é rejeitado ou marcado com ⚠️. |
| “Auditoria” feita pela própria IA (“✅ 100% cravado”) | As bandas de projeção são calculadas pela **volatilidade** (±σ). A IA só sugere o viés. Na data-alvo, o código confere o valor realizado e calcula o **track record**. |
| Conversa ficou longa demais e o Gemini parou de responder | Cada execução começa do zero. O contexto fica em arquivos, não no chat. |
| Se tudo der errado… | Se o boletim não passa no schema, ou se menos de 40% dos indicadores tiverem dado válido, o **boletim anterior é mantido** e o GitHub abre uma issue de alerta. |

---

## Instalação (≈ 15 minutos, tudo pelo navegador)

1. **Crie um repositório** no GitHub (ou use o que já hospeda o seu painel) e envie todos os arquivos
   deste projeto para a raiz. O `index.html` e o `boletim_atual.json` ficam lado a lado.
2. **IA:** cadastre as chaves gratuitas em *Settings → Secrets and variables → Actions → New repository
   secret*: `GROQ_API_KEY`, `NVIDIA_API_KEY`, `GEMINI_API_KEY` e `OPENROUTER_API_KEY` (onde pegar cada
   uma está na tabela abaixo). Pode cadastrar só algumas: chave que falta é pulada. Sem nenhuma, o
   boletim sai com a IA local (sem limite, porém mais lenta). Depois rode *Actions → Testar IAs*.
   *(Opcional)* `EIA_API_KEY`: chave gratuita da EIA (governo dos EUA) para checagem cruzada de WTI/Brent
   (o petróleo já vem do FRED, sem chave).
3. **Permita que o robô salve arquivos**: *Settings → Actions → General → Workflow permissions →
   Read and write permissions*. Crie também as etiquetas `nova-fonte` e `falha-boletim` em
   *Issues → Labels → New label*. O GitHub só aplica etiquetas que já existem, e o formulário de fontes depende da `nova-fonte`.
4. **Publique o painel**: *Settings → Pages → Deploy from a branch → main / (root)*.
   O painel fica em `https://SEU_USUARIO.github.io/SEU_REPO/`.
5. **Calibre as fontes**: *Actions → Checar fontes → Run workflow*. O resultado aparece no resumo da
   execução e em `relatorios/checagem_fontes.md` (✅ ok · ❌ erro · 🚫 bloqueado por robots.txt).
6. **Gere o primeiro boletim**: *Actions → Relatório de Inteligência de Mercado → Run workflow*.

> **Primeiras semanas:** o histórico se forma sozinho. A PTAX/Selic (API do BCB) e as tabelas que
> mostram vários dias já chegam com histórico. Para os demais indicadores, a variação semanal aparece
> após a 1ª semana, as bandas de projeção após 10 pregões e o track record 5 pregões depois do 1º registro.

### A IA: fila de APIs gratuitas, com a IA local como rede de segurança

Nenhum provedor hospedado é grátis **e** ilimitado: todo plano gratuito tem teto por minuto, por dia ou
de créditos. Para não depender de um só, o agente usa uma **fila**. Somadas, as quatro APIs cobrem
com folga os 4 boletins do dia e os cliques no botão; a IA local cobre o que passar disso.

```
Groq ──► NVIDIA (Nemotron) ──► Google Gemini ──► OpenRouter ──► IA local (Ollama, sem limite)
```

| # | API | Secret | Onde pegar a chave (grátis) | Limite do plano gratuito (nov/2026) |
|---|---|---|---|---|
| 1 | **Groq** | `GROQ_API_KEY` | console.groq.com → API Keys | `openai/gpt-oss-120b`: 30 pedidos/min, 1.000/dia, 8 mil tokens/min, 200 mil tokens/dia |
| 2 | **NVIDIA** (Nemotron) | `NVIDIA_API_KEY` | build.nvidia.com → Get API Key (começa com `nvapi-`) | cerca de 40 pedidos/min por conta |
| 3 | **Google Gemini** | `GEMINI_API_KEY` | aistudio.google.com → Get API key | Flash-Lite: cerca de 10 pedidos/min e 500/dia |
| 4 | **OpenRouter** | `OPENROUTER_API_KEY` | openrouter.ai → Keys | modelos gratuitos: 20 pedidos/min e 50/dia |

Os limites e os nomes de modelo mudam com frequência; confira na página de cada provedor.

**Como a fila decide** (cada boletim faz de 6 a 9 pedidos):
- **Limite por minuto** (HTTP 429 com espera curta): a API descansa os segundos pedidos e o bloco vai
  para a próxima da fila. O bloco seguinte volta a tentar a preferida.
- **Cota do dia, chave recusada ou sem créditos:** a API sai da fila até o fim daquele boletim. No
  próximo boletim ela é tentada de novo.
- **Pedido grande demais para o plano grátis** (HTTP 413): o agente encolhe o pedido (menos notícias,
  resumos curtos) e tenta de novo. A Groq já recebe o pedido enxuto por causa do limite de 8 mil tokens/min.
- **Modelo aposentado** (HTTP 404): o agente usa o próximo modelo da lista daquela API.
- **Todas esgotadas:** tudo vai para a IA local. Se só falta esperar alguns segundos por uma API, o
  agente espera, porque a IA local leva minutos por resposta.

Qualquer que seja a IA, o **verificador** confere cada número escrito. O resumo do boletim mostra quem
escreveu e quantas vezes (ex.: `openai/gpt-oss-120b @ Groq ×4 → nvidia/… @ NVIDIA ×2`).

**Ajustes (sem programar):**
- **Ordem da fila:** mude a ordem dos itens em `config/configuracoes.yaml` → `llm.provedores`.
- **Modelo de cada API:** variáveis `GROQ_MODEL`, `NVIDIA_MODEL`, `GEMINI_MODEL`, `OPENROUTER_MODEL` em
  *Settings → Secrets and variables → Actions → Variables*. A lista do arquivo vira reserva.
- **Mais uma API** (ex.: Cerebras, DeepSeek): secrets `LLM_BASE_URL`, `LLM_API_KEY` e `LLM_MODEL`. Ela
  entra depois das quatro e antes da IA local.
- **Conferir as chaves:** *Actions → Testar IAs → Run workflow* manda um pedido curtinho a cada API e
  mostra ✔/✖ no resumo da execução.
- **Privacidade:** nos planos gratuitos o provedor pode usar os pedidos para melhorar os produtos dele.
  O agente só envia cotações e notícias públicas.

**IA local (rede de segurança):** o workflow instala o [Ollama](https://ollama.com) e baixa um modelo
aberto (padrão `qwen2.5:7b`) **em segundo plano**, enquanto o agente já coleta as cotações. Se as APIs
derem conta, ela nem é usada e não atrasa nada. Se for usada, sem placa de vídeo o boletim leva de 20 a
40 min. Troque o modelo com a variável `LLM_LOCAL_MODEL` (`qwen2.5:3b` é mais rápido) ou desligue com
`IA_LOCAL` = `nao`.

---

## 🔄 Atualização automática e sob demanda

O painel fica atualizado de três formas, sem ninguém precisar colar JSON:

| Como | Quando | O que faz | Tempo |
|---|---|---|---|
| **Monitor de cotações** (automático, pelo Plantão) | a cada 20 min, seg–sex, das 9h07 às 19h47 | Confere **só as cotações**. Se alguma mudou, republica os números. A análise escrita continua com o horário em que foi feita. Se nada mudou, não publica nada. | 1–2 min |
| **Boletim completo** (automático, pelo Plantão) | 08:41, 13:17, 19:43 e domingo 17:11 | Cotações + notícias + análise da IA verificada | 5–40 min* |
| **Botão 🔄 Atualizar agora** (no painel) | quando você quiser | **Completo**: o boletim inteiro. **Rápido**: só as cotações (monitor). Acompanha o progresso e recarrega o painel sozinho | 2–40 min* |

\* 4–8 min com a fila de APIs gratuitas; 20–40 min quando a análise é escrita pela IA local (sem limite).

O painel aberto confere a cada 5 minutos se saiu boletim novo e **recarrega sozinho**. O topo mostra
“📈 Cotações conferidas há X min · 📝 análise escrita às HH:MM”.

> “Tempo real” aqui significa minutos, não segundos: o agente lê ~30 sites com pausas educadas entre
> acessos e a IA ainda escreve e confere o texto. Várias fontes (Cepea, B3, PTAX) publicam uma vez por dia.

### Configurar o botão “Atualizar agora” (uma vez por navegador)

O botão pede ao GitHub para rodar o agente, e para isso o GitHub exige uma chave sua:

1. Abra **github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. *Repository access*: **Only select repositories** → escolha **só** o repositório do agente.
3. *Permissions*: **Actions: Read and write** e **Contents: Read-only**. Defina uma validade (ex.: 90 dias).
4. No painel, clique em **🔑 Acesso do botão**, cole a chave e clique em **Salvar neste navegador**.

A chave fica guardada **só no seu navegador**. Ela não vai para o site, para o repositório nem para
quem mais abrir o painel. Quem não tiver a chave continua vendo o painel normalmente, sem o botão funcionar.
Para revogar, apague a chave no GitHub.

> **Minutos do GitHub Actions:** em repositório **público** são gratuitos. Em repositório **privado**,
> monitor + boletins usam algo como 1.300–1.500 min/mês. Confira a cota do seu plano em *Settings → Billing*
> e, se precisar, aumente o intervalo do monitor em `.github/workflows/monitor.yml`. O GitHub Pages
> em repositório privado exige plano pago.

## Horários (fuso de Brasília) e o Plantão

| Turno | Quando |
|---|---|
| Abertura | seg–sex 08:41 |
| Meio do dia | seg–sex 13:17 (PTAX publicada) |
| Fechamento | seg–sex 19:43 (Cepea, B3 e Chicago fechados) |
| Balanço da semana | domingo 17:11 |
| Monitor de cotações | seg–sex, a cada 20 min, 09:07–19:47 |

O agendador do GitHub (“schedule”) atrasa execuções em horas e descarta muitas delas. Por isso quem
cumpre a agenda é o **Plantão** (`.github/workflows/plantao.yml`):

- é acordado de hora em hora (basta **um** desses chamados funcionar no dia);
- fica ativo durante o expediente e dispara o monitor e os boletins **na hora**, pelo mesmo disparo
  que o botão do painel usa;
- se um boletim ficou para trás (até 2h30), ele sai atrasado em vez de não sair;
- antes do limite de 6 h de um job do GitHub, passa o plantão para uma nova execução;
- só existe um plantão por vez: um chamado que encontra outro ativo encerra em segundos (aparece como
  ✅ curto na aba Actions — é normal).

Os horários ficam em `config/configuracoes.yaml → agenda` (sempre entre aspas, ex.: `"13:17"`).
O botão **🔄 Atualizar agora** do painel também acorda o Plantão, caso ele esteja parado.

---

## Fontes: a aba “🌐 Fontes & Qualidade”

A lista de sites confiáveis fica em [`config/fontes.yaml`](config/fontes.yaml), agrupada por
Brasil / Argentina / Internacional / China, e aparece no painel com o status de cada fonte em cada execução.

**Para adicionar um site**, há três caminhos:
1. **Pelo painel:** aba *Fontes & Qualidade → ➕ Adicionar nova fonte → Enviar pelo GitHub*. Abre o
   formulário já preenchido. Ao enviar, o robô inclui o site, comenta e fecha a issue.
2. **Pelo GitHub:** *Issues → New issue → ➕ Nova fonte confiável*.
3. **Editando o arquivo** `config/fontes.yaml` (ícone de lápis). Basta copiar um bloco existente.

Para **notícias**, basta nome + URL: o agente procura o feed RSS sozinho. Se não houver feed, ele lê a
página de últimas notícias e abre as matérias para pegar a data de publicação. Para **desativar** uma
fonte sem apagá-la, use `ativa: false`.

Só o dono do repositório e os colaboradores conseguem adicionar fontes pelo formulário.

### Cotações (`config/indicadores.yaml`)

Cada indicador declara de onde vem o número e como ele é conferido:

```yaml
- id: soja_paranagua
  nome: "Soja — Indicador Cepea/Esalq Paranaguá"
  bloco: complexo_soja
  unidade: "R$/sc"
  faixa: [60, 450]                 # fora disso = rejeitado
  var_max_dia_pct: 6               # acima disso = alerta (3x = rejeitado)
  defasagem_max_dias_uteis: 2
  fontes:
    - fonte: Notícias Agrícolas    # nome igual ao de fontes.yaml
      tipo: tabela_html
      url: https://www.noticiasagricolas.com.br/cotacoes/soja
      titulo_contem: ["soja", "paranagu"]   # escolhe a tabela pelo título
      linha: 1                              # ou linha_contem: ["uberl"]
      coluna_valor: ["vista", "r$", "valor"]
      coluna_data: ["data"]                 # se houver: lê a série inteira
```

Tipos de coletor: `bcb_ptax`, `bcb_sgs`, `b3_ajustes`, `tabela_html`, `regex_pagina`, `json_api`, `yahoo`.
Com duas fontes para o mesmo indicador, a primeira vale e a segunda faz a **checagem cruzada**.

> ⚠️ **Calibração:** as regras de leitura de Notícias Agrícolas, Agrolink, B3 e BCR foram escritas a
> partir da estrutura pública dessas páginas, mas não foram testadas nos sites reais. Rode **Checar
> fontes**. Se algo der ❌, a mensagem mostra os títulos de tabela encontrados na página, e basta ajustar
> `titulo_contem` / `linha_contem` / `coluna_valor`.

---

## O que cada execução gera

| Arquivo | Conteúdo |
|---|---|
| `boletim_atual.json` | O que o painel lê: as mesmas chaves de antes, mais `audio_script`, `ndf_parameters`, `data_quality` e `trusted_sources` |
| `relatorios/relatorio_atual.md` | Relatório completo nas 8 seções (🎧 versão para ouvir, 📈 panorama, 🌱 análise por complexo, 📅 WTD, 🗓️ MTD, 🎯 projeções, 💡 pílula, 💻 payload) e mais a seção 🛡️ qualidade |
| `relatorios/arquivo/AAAA/MM/` | Cópia de todos os boletins (auditoria) |
| `data/historico.csv` | Toda cotação coletada, com fonte, link, horário e status |
| `data/projecoes.jsonl` | Cada projeção registrada e o resultado da aferição |
| `data/noticias/AAAA-MM-DD.json` | Notícias coletadas e status de cada fonte |
| `data/ultima_analise.json` | Última análise verificada (o monitor a reaproveita entre os turnos) |
| `data/estado_cotacoes.json` | Cotações do último boletim publicado (é com ele que o monitor detecta mudança) |

### Novidades no painel (`index.html`)
- Aba **🌐 Fontes & Qualidade**: conferência de cada cotação, status de cada fonte e botão para adicionar sites.
- Linha de qualidade no topo (ok / alerta / desatualizado / indisponível).
- **🎧 Ouvir resumo do turno**: lê o roteiro em voz alta, com a voz pt-BR do próprio navegador.
- Calculadora de NDF já vem preenchida com o spot, a Selic e os dias úteis do dia.
- Gráfico mensal **sem interpolação**: antes, o painel desenhava uma curva inventada quando faltava histórico.
- Os links das notícias citadas no texto são clicáveis.
- Botão **🔄 Atualizar agora** e recarga automática quando sai boletim novo.

---

## Rodar no seu computador (opcional)

```bash
pip install -r requirements.txt
python -m agente validar-config      # confere os arquivos de config/
python -m agente testar-ia           # testa cada API gratuita da fila (precisa das chaves no ambiente)
python -m agente checar-fontes       # testa todas as fontes
python -m agente executar            # gera o boletim (turno pelo horário)
python -m agente executar --turno fechamento --sem-ia
python -m agente monitorar           # só cotações; republica se houver cotação nova
python -m agente adicionar-fonte --nome "Portal X" --url https://... --regiao Brasil
python -m pytest -q                  # 84 testes (internet e IA simuladas)
python tests/gerar_exemplo.py        # gera exemplos/boletim_exemplo_FICTICIO.json
```

Se o site de alguma fonte bloquear os servidores do GitHub, rode o agente no seu PC com um
*self-hosted runner* ou pelo Agendador de Tarefas do Windows.

## Limites conhecidos
- Sites com paywall ou bloqueio de robôs (Reuters, Bloomberg) costumam falhar. A **Notícias Agrícolas** recusa
  robôs (HTTP 403) desde nov/2026 e está desligada em `config/fontes.yaml`. As cotações vêm de: Banco Central
  (PTAX, Selic), arquivo oficial de ajustes da B3 (dólar, milho, boi, soja, café arábica e conilon), Bolsa de
  Rosario (Chicago: soja, farelo, óleo, milho, trigo), Canal Rural/CMA (praças físicas), Agrolink (Manhuaçu,
  Uberlândia, caroço de algodão MT/BA) e FRED/EIA (petróleo WTI e Brent spot, sem chave, com alguns dias de atraso).
- Sem fonte gratuita que aceite robôs hoje: algodão e café na ICE (Nova York) e robusta em Londres. Esses
  indicadores estão com `ativo: false` em `config/indicadores.yaml` (saem do painel) até surgir uma fonte; no
  lugar do café ICE entram os contratos de café da B3.
- O agente **respeita o robots.txt** de cada site (`respeitar_robots_txt: true`). Fontes que proíbem
  robôs aparecem como 🚫 no painel. Use `ignorar_robots: true` numa fonte só se você tiver autorização do site.
- As projeções são bandas estatísticas de volatilidade, não previsões. O track record mostra a calibração real.
- Conteúdo analítico: não constitui recomendação de investimento.

## Estrutura
```
agente/            código (coletores/, validacao, analise, projecoes, redator, verificador, montador)
config/            fontes.yaml · indicadores.yaml · blocos.yaml · configuracoes.yaml
prompts/           instruções da IA (sistema, bloco, fechamento)
tests/             testes com internet e IA simuladas
.github/           workflows (plantão, relatório, monitor, testar IAs, checar fontes, nova fonte) e formulário de nova fonte
scripts/           instalação da IA local em segundo plano e inclusão de fonte via issue
index.html         painel Germinare Market Intelligence Pro (atualizado)
```

Licença MIT.
