import json
import os
import pandas as pd
import requests
import streamlit as st

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(
    page_title="Germinare Agro | Inteligência de Mercado",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. INJEÇÃO DE CSS CUSTOMIZADO (DESIGN DARK PREMIUM GERMINARE)
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
        background-color: #0a0c10 !important;
        color: #f0f4f8 !important;
    }

    /* Fundo principal e Sidebar */
    .stApp {
        background: radial-gradient(circle at top right, #112218 0%, #0a0c10 45%);
    }
    section[data-testid="stSidebar"] {
        background-color: #0d1017 !important;
        border-right: 1px solid #1e2633 !important;
    }

    /* Cabeçalho Germinare */
    .germinare-header {
        background: linear-gradient(135deg, #121722 0%, #0d1512 100%);
        border: 1px solid #1f2d24;
        border-left: 5px solid #00e676;
        border-radius: 14px;
        padding: 24px 28px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
    }
    .germinare-brand {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #00e676;
        margin-bottom: 4px;
    }
    .germinare-title {
        font-size: 28px;
        font-weight: 800;
        color: #ffffff;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .germinare-badge {
        background: rgba(0, 230, 118, 0.12);
        border: 1px solid rgba(0, 230, 118, 0.35);
        color: #00e676;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 13px;
        font-weight: 600;
    }

    /* Cartões Customizados (Estilo App Web Dark) */
    .dark-card {
        background-color: #12161f;
        border: 1px solid #1e2633;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .dark-card:hover {
        border-color: #00e676;
    }
    .card-tag {
        display: inline-block;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 4px 10px;
        border-radius: 6px;
        margin-bottom: 10px;
    }
    .tag-green { background: rgba(0, 230, 118, 0.15); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); }
    .tag-blue  { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }
    .tag-amber { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }
    .tag-red   { background: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); }

    /* Botões de Link para Notícias */
    .news-link-btn {
        display: inline-block;
        background-color: #18202c;
        color: #00e676 !important;
        border: 1px solid #263345;
        padding: 7px 14px;
        border-radius: 8px;
        text-decoration: none !important;
        font-size: 13px;
        font-weight: 500;
        margin-right: 8px;
        margin-top: 8px;
        transition: all 0.2s ease;
    }
    .news-link-btn:hover {
        background-color: #00e676;
        color: #0a0c10 !important;
        border-color: #00e676;
        font-weight: 600;
    }

    /* Estilização de Métricas e Abas do Streamlit */
    div[data-testid="stMetric"] {
        background-color: #12161f;
        border: 1px solid #1e2633;
        border-top: 3px solid #00e676;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    }
    button[data-baseweb="tab"] {
        background-color: #12161f !important;
        border-radius: 8px 8px 0 0 !important;
        margin-right: 6px !important;
        padding: 10px 18px !important;
        border: 1px solid #1e2633 !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #16241d !important;
        color: #00e676 !important;
        border-bottom: 2px solid #00e676 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


# 3. FUNÇÃO AUXILIAR PARA LIMPAR E LER O JSON DA API
def limpar_e_ler_json(texto_bruto):
  texto = texto_bruto.strip()
  if texto.startswith("```json"):
    texto = texto[7:]
  elif texto.startswith("```"):
    texto = texto[3:]
  if texto.endswith("```"):
    texto = texto[:-3]
  return json.loads(texto.strip())


@st.cache_data(ttl=30)
def carregar_dados_boletim(url_raw_github=None):
  if url_raw_github and url_raw_github.startswith("http"):
    try:
      resposta = requests.get(url_raw_github, timeout=10)
      if resposta.status_code == 200 and resposta.text.strip():
        return limpar_e_ler_json(resposta.text)
    except Exception as e:
      st.sidebar.warning(f"Aviso na URL remota: {e}")

  if os.path.exists("boletim_atual.json"):
    try:
      with open("boletim_atual.json", "r", encoding="utf-8") as f:
        conteudo = f.read()
        if conteudo.strip():
          return limpar_e_ler_json(conteudo)
    except Exception as e:
      st.error(f"⚠️ Erro de formatação no arquivo `boletim_atual.json`: {e}")
      return None
  return None


# 4. BARRA LATERAL (BRANDING GERMINARE)
st.sidebar.markdown(
    """
<div style="text-align: left; padding-bottom: 12px; border-bottom: 1px solid #1e2633; margin-bottom: 16px;">
    <div style="color: #00e676; font-weight: 800; font-size: 18px; letter-spacing: 0.5px;">🌱 GERMINARE AGRO</div>
    <div style="color: #94a3b8; font-size: 12px;">Analytics & Market Intelligence</div>
</div>
""",
    unsafe_allow_html=True,
)

url_padrao = "[https://raw.githubusercontent.com/luan238/painel-inteligencia-agro/main/boletim_atual.json](https://raw.githubusercontent.com/luan238/painel-inteligencia-agro/main/boletim_atual.json)"
url_api = st.sidebar.text_input(
    "🔗 Endpoint da API (GitHub Raw):", value=url_padrao
)

if st.sidebar.button("🔄 Sincronizar Dados Agora", use_container_width=True):
  st.cache_data.clear()
  st.rerun()

dados = carregar_dados_boletim(url_api)
if not dados:
  st.stop()

st.sidebar.markdown("---")
st.sidebar.caption(f"📅 **Última Sincronização:**\n{dados['metadata']['data_hora']}")

# 5. CABEÇALHO CORPORATIVO GERMINARE
st.markdown(
    f"""
<div class="germinare-header">
    <div>
        <div class="germinare-brand">Germinare Analytics Center • Market Intelligence</div>
        <h1 class="germinare-title">Painel de Inteligência de Mercado Agro</h1>
    </div>
    <div style="margin-top: 8px;">
        <span class="germinare-badge">⚡ {dados['metadata']['titulo_edicao']} | {dados['metadata']['data_hora']}</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

with st.expander("🔊 Ouvir / Ler Resumo Falado do Turno (Podcast Executivo)"):
  st.markdown(
      f"<div style='color:#d1fae5; line-height:1.6; font-size:15px;'>{dados['metadata']['resumo_falado']}</div>",
      unsafe_allow_html=True,
  )

# 6. NAVEGAÇÃO POR ABAS
(
    aba_panorama,
    aba_culturas,
    aba_noticias,
    aba_cambio,
    aba_mentoria,
    aba_projecoes,
) = st.tabs([
    "📌 Panorama Geral",
    "🌱 Culturas & Trading",
    "📰 Central de Notícias & Links",
    "💵 Mesa de Câmbio & NDF",
    "🧠 Pílula de Mentoria",
    "🎯 Projeções & Backtesting",
])

# ABA 1: PANORAMA GERAL
with aba_panorama:
  st.markdown("### 📊 Panorama Consolidado do Turno")

  # Exibe Cards executivos em vez de apenas tabela simples
  cols_pan = st.columns(2)
  for i, item in enumerate(dados["panorama_geral"]):
    with cols_pan[i % 2]:
      st.markdown(
          f"""
            <div class="dark-card">
                <span class="card-tag tag-green">{item['ativo']}</span>
                <div style="font-size: 18px; font-weight: 700; color: #ffffff; margin-bottom: 6px;">{item['cotacao']}</div>
                <div style="font-size: 13.5px; color: #94a3b8; line-height: 1.5;">{item['destaque']}</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

  st.markdown("#### 📋 Tabela Resumo de Indicadores")
  df_panorama = pd.DataFrame(dados["panorama_geral"])
  df_panorama.columns = [
      "Indicador / Ativo",
      "Cotação / Referência Atual",
      "Destaque e Gatilhos de Mercado",
  ]
  st.dataframe(df_panorama, use_container_width=True, hide_index=True)

# ABA 2: ANÁLISE POR CULTURA & TRADING
with aba_culturas:
  culturas_disponiveis = list(dados["blocos_culturas"].keys())
  cultura_selecionada = st.selectbox(
      "🔍 Selecione o Complexo / Commodity para Análise:", culturas_disponiveis
  )
  bloco = dados["blocos_culturas"][cultura_selecionada]

  st.markdown(
      f"""
    <div class="dark-card" style="border-left: 4px solid #fbbf24;">
        <span class="card-tag tag-amber">🧭 Viés de Mercado do Turno</span>
        <div style="font-size: 15px; font-weight: 600; color: #f8fafc;">{bloco['vies_mercado']}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  st.markdown(
      f"""
    <div class="dark-card">
        <span class="card-tag tag-blue">A. Resumo Executivo (Drivers Atuais)</span>
        <div style="font-size: 14.5px; color: #cbd5e1; line-height: 1.65;">{bloco['resumo_executivo']}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  st.markdown("#### 📰 B. Fatos Geradores, Impacto no Mercado e Links Diretos")
  for idx, noticia in enumerate(bloco["noticias_detalhadas"], 1):
    botoes_links = "".join([
        f'<a href="{l["url"]}" target="_blank" class="news-link-btn">🔗'
        f' {l["titulo_link"]}</a>'
        for l in noticia["links"]
    ])
    st.markdown(
        f"""
        <div class="dark-card">
            <div style="font-size: 16px; font-weight: 700; color: #00e676; margin-bottom: 8px;">{idx}. {noticia['titulo']}</div>
            <div style="font-size: 14px; color: #cbd5e1; line-height: 1.6; margin-bottom: 12px;">{noticia['resumo_noticia']}</div>
            <div style="font-size: 12px; color: #94a3b8; font-weight: 600; text-transform: uppercase;">Fontes Oficiais para Leitura Completa:</div>
            <div>{botoes_links}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

  st.markdown("#### 🎯 C. Direcionamento Estratégico por Perfil")
  c_col1, c_col2 = st.columns(2)
  with c_col1:
    st.markdown(
        f"""
        <div class="dark-card">
            <span class="card-tag tag-green">🚜 Produtores Rurais</span>
            <div style="font-size: 14px; color: #e2e8f0; line-height: 1.6;">{bloco['consultoria'].get('Produtores Rurais', '')}</div>
        </div>
        <div class="dark-card">
            <span class="card-tag tag-blue">🤝 Cooperativas e Revendas</span>
            <div style="font-size: 14px; color: #e2e8f0; line-height: 1.6;">{bloco['consultoria'].get('Cooperativas e Revendas', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
  with c_col2:
    st.markdown(
        f"""
        <div class="dark-card">
            <span class="card-tag tag-amber">🐄 Indústrias e Confinamentos</span>
            <div style="font-size: 14px; color: #e2e8f0; line-height: 1.6;">{bloco['consultoria'].get('Indústrias e Confinamentos', '')}</div>
        </div>
        <div class="dark-card">
            <span class="card-tag tag-blue">🚢 Tradings e Exportadores</span>
            <div style="font-size: 14px; color: #e2e8f0; line-height: 1.6;">{bloco['consultoria'].get('Tradings e Exportadores', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

  st.markdown("#### 📈 Visão do Trader (Long / Short, Derivativos e Câmbio)")
  t_col1, t_col2 = st.columns(2)
  with t_col1:
    st.markdown(
        f"""
        <div class="dark-card" style="border-left: 4px solid #f87171;">
            <span class="card-tag tag-red">⚡ Posicionamento Direcional & Spreads</span>
            <div style="font-size: 14px; color: #e2e8f0; line-height: 1.6;">{bloco['visao_trader'].get('Direcional e Spreads', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
  with t_col2:
    st.markdown(
        f"""
        <div class="dark-card" style="border-left: 4px solid #00e676;">
            <span class="card-tag tag-green">💵 Cross-Hedge & Trading do Dólar</span>
            <div style="font-size: 14px; color: #e2e8f0; line-height: 1.6;">{bloco['visao_trader'].get('Cross-Hedge e Trading do Dólar', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ABA 3: CENTRAL DE NOTÍCIAS E LINKS
with aba_noticias:
  st.markdown("### 📰 Central de Notícias, Fundamentos e Links Verificados")
  filtro_cultura_not = st.multiselect(
      "Filtrar por Complexo:",
      options=list(dados["blocos_culturas"].keys()),
      default=list(dados["blocos_culturas"].keys()),
  )

  for nome_cultura in filtro_cultura_not:
    bloco_c = dados["blocos_culturas"][nome_cultura]
    st.markdown(f"#### 🌱 {nome_cultura}")
    for noticia in bloco_c["noticias_detalhadas"]:
      botoes_links = "".join([
          f'<a href="{l["url"]}" target="_blank" class="news-link-btn">🌐'
          f' Link {i}: {l["titulo_link"]}</a>'
          for i, l in enumerate(noticia["links"], 1)
      ])
      st.markdown(
          f"""
            <div class="dark-card">
                <span class="card-tag tag-green">Fato Gerador & Notícia</span>
                <div style="font-size: 17px; font-weight: 700; color: #ffffff; margin-bottom: 8px;">{noticia['titulo']}</div>
                <div style="font-size: 14px; color: #cbd5e1; line-height: 1.6; margin-bottom: 10px;">{noticia['resumo_noticia']}</div>
                <div style="background:#0d1017; padding:10px 14px; border-radius:8px; border-left:3px solid #38bdf8; font-size:13px; color:#94a3b8; margin-bottom:12px;">
                    <b style="color:#38bdf8;">Impacto na Visão Trading:</b> {bloco_c['visao_trader'].get('Direcional e Spreads', '')}
                </div>
                <div>{botoes_links}</div>
            </div>
            """,
          unsafe_allow_html=True,
      )

# ABA 4: MESA DE CÂMBIO E CALCULADORA NDF
with aba_cambio:
  st.markdown("### 💵 Mesa de Câmbio (FX Desk) & Simulador de NDF")
  cambio = dados["mesa_cambio"]

  c1, c2, c3 = st.columns(3)
  c1.metric("Dólar Comercial (Spot)", cambio["spot"])
  c2.metric("Dólar Futuro (Nov/26 B3)", cambio["futuro_nov"])
  c3.metric("NDF Colheita Soja (Mar/27)", cambio["ndf_marco27_estimado"])

  st.markdown(
      f"""
    <div class="dark-card" style="margin-top: 16px; border-left: 4px solid #00e676;">
        <span class="card-tag tag-green">🎯 Diretriz da Mesa de Câmbio</span>
        <div style="font-size: 15px; font-weight: 600; color: #ffffff; margin-bottom: 8px;">{cambio['decisao_mesa']}</div>
        <div style="font-size: 14px; color: #94a3b8;"><b>Racional Macro e Fluxo:</b> {cambio['racional']}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  st.markdown("#### 🧮 Calculadora de Arbitragem de Juros (Dólar Futuro / NDF)")
  col_calc1, col_calc2, col_calc3 = st.columns(3)
  with col_calc1:
    dolar_spot_in = st.number_input(
        "Dólar Spot Hoje (R$):", value=5.0700, step=0.0100, format="%.4f"
    )
    preco_saca_usd = st.number_input(
        "Preço da Commodity em US$/saca:", value=27.50, step=0.10
    )
  with col_calc2:
    taxa_di = st.number_input(
        "Taxa DI / Selic Anual (% a.a.):", value=11.50, step=0.25
    )
    cupom_cambial = st.number_input(
        "Cupom Cambial Limpo (% a.a.):", value=4.80, step=0.10
    )
  with col_calc3:
    dias_uteis = st.number_input(
        "Dias Úteis até o Vencimento (du - Base 252):", value=111, step=1
    )
    dias_corridos = st.number_input(
        "Dias Corridos até o Vencimento (dc - Base 360):", value=163, step=1
    )

  fator_real = (1 + (taxa_di / 100)) ** (dias_uteis / 252)
  fator_dolar = 1 + ((cupom_cambial / 100) * (dias_corridos / 360))
  dolar_futuro_calc = dolar_spot_in * (fator_real / fator_dolar)
  forward_points = dolar_futuro_calc - dolar_spot_in

  saca_reais_spot = preco_saca_usd * dolar_spot_in
  saca_reais_ndf = preco_saca_usd * dolar_futuro_calc
  ganho_por_saca = saca_reais_ndf - saca_reais_spot

  res1, res2, res3 = st.columns(3)
  res1.metric(
      "Dólar Futuro / NDF Calculado",
      f"R$ {dolar_futuro_calc:.4f}",
      f"+R$ {forward_points:.4f} (Forward Points)",
  )
  res2.metric(
      "Preço da Saca no Dólar Spot", f"R$ {saca_reais_spot:.2f}/sc", "Base Spot"
  )
  res3.metric(
      "Preço da Saca Travando NDF",
      f"R$ {saca_reais_ndf:.2f}/sc",
      f"+R$ {ganho_por_saca:.2f}/sc de ganho!",
  )

# ABA 5: PÍLULA DE MENTORIA
with aba_mentoria:
  st.markdown(
      f"""
    <div class="dark-card" style="border-left: 4px solid #00e676;">
        <span class="card-tag tag-green">🧠 Mentoria Executiva do Turno</span>
        <h3 style="color: #ffffff; margin-top: 6px;">{dados['pilula_mentoria']['titulo']}</h3>
        <div style="font-size: 15px; color: #cbd5e1; line-height: 1.75; white-space: pre-line;">{dados['pilula_mentoria']['conteudo']}</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

# ABA 6: MATRIZ DE PROJEÇÕES AUDITÁVEIS
with aba_projecoes:
  st.markdown("### 🎯 Matriz de Projeções Auditáveis e Track Record")
  st.caption(
      "Conferência sistemática toda sexta-feira (curto prazo) e na última"
      " sexta-feira do mês (fechamento mensal)."
  )
  df_proj = pd.DataFrame(dados["matriz_projecoes"])
  st.dataframe(df_proj, use_container_width=True, hide_index=True)
