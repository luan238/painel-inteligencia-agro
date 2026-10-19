import json
import os
import pandas as pd
import requests
import streamlit as st

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(
    page_title="Germinare | Market Intelligence Pro",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. CSS IDÊNTICO AO NUTRE COMPARE PRO DA GERMINARE
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0px !important;
    }
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 3rem !important;
        max-width: 96% !important;
    }

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', sans-serif !important;
        background-color: #0d0d0d !important;
        color: #e5e5e5 !important;
    }

    /* TOPBAR FIXA GERMINARE */
    .germinare-topbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 54px;
        background-color: #050505;
        border-bottom: 1.5px solid #ff7a00;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 28px;
        z-index: 999999;
    }
    .germinare-top-right {
        font-size: 13px;
        color: #a3a3a3;
        font-weight: 400;
    }

    /* SIDEBAR IDÊNTICA À FOTO */
    section[data-testid="stSidebar"] {
        background-color: #0a0a0a !important;
        border-right: 1px solid #1f1f1f !important;
        padding-top: 1.5rem !important;
    }
    .sidebar-section-title {
        font-size: 11.5px;
        font-weight: 700;
        color: #8c8c8c;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-top: 16px;
        margin-bottom: 12px;
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        background-color: #111111 !important;
        border: 1px solid #262626 !important;
        border-radius: 6px !important;
        color: #f5f5f5 !important;
    }

    /* TÍTULO PRINCIPAL */
    .main-title {
        font-size: 30px;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 2px;
        letter-spacing: -0.5px;
    }
    .main-title span {
        color: #ff7a00;
    }
    .main-subtitle {
        font-size: 14px;
        color: #8c8c8c;
        margin-bottom: 18px;
    }

    /* CAIXA DE REFERÊNCIA / RESUMO */
    .ref-box {
        background-color: #161616;
        border: 1px solid #282828;
        border-radius: 8px;
        padding: 14px 18px;
        font-size: 13.5px;
        color: #d4d4d4;
        line-height: 1.55;
        margin-bottom: 22px;
    }
    .ref-box b {
        color: #ffffff;
    }

    /* ABAS ESTILO NUTRE COMPARE PRO */
    div[data-baseweb="tab-list"] {
        border-bottom: 1px solid #262626 !important;
        gap: 28px !important;
        background-color: transparent !important;
    }
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        padding: 10px 4px !important;
        color: #8c8c8c !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #ff7a00 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #ff7a00 !important;
    }

    /* PÍLULAS DE COMMODITIES */
    .Filter-pills-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 12px 0 22px 0;
    }
    .pill-active {
        background-color: rgba(255, 122, 0, 0.08);
        border: 1px solid #ff7a00;
        color: #ff7a00;
        padding: 5px 14px;
        border-radius: 999px;
        font-size: 12.5px;
        font-weight: 500;
    }
    .pill-green {
        background-color: rgba(76, 175, 80, 0.1);
        border: 1px solid #4caf50;
        color: #66bb6a;
        padding: 5px 14px;
        border-radius: 999px;
        font-size: 12.5px;
        font-weight: 500;
    }

    .section-header {
        font-size: 18px;
        font-weight: 700;
        color: #ffffff;
        padding-bottom: 10px;
        border-bottom: 1px solid #222222;
        margin-top: 18px;
        margin-bottom: 16px;
    }

    /* CARTÕES NUTRE COMPARE PRO */
    .nutre-card {
        background-color: #141414;
        border: 1px solid #242424;
        border-radius: 10px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }
    .nutre-card:hover {
        border-color: #383838;
    }
    .nutre-card-label {
        font-size: 12.5px;
        color: #9e9e9e;
        margin-bottom: 6px;
        font-weight: 400;
    }
    .nutre-card-value {
        font-size: 24px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 4px;
        letter-spacing: -0.3px;
    }
    .nutre-card-unit {
        font-size: 12.5px;
        color: #8c8c8c;
        margin-bottom: 14px;
        line-height: 1.5;
    }
    .nutre-card-footer {
        border-top: 1px solid #222222;
        padding-top: 10px;
        font-size: 12.5px;
        color: #ff7a00;
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
    }
    .nutre-link {
        color: #ff7a00 !important;
        text-decoration: none !important;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    .nutre-link:hover {
        text-decoration: underline !important;
        color: #ffa040 !important;
    }
</style>

<!-- TOPBAR FIXA GERMINARE COM LOGO VETORIAL FIEL AO DA FOTO -->
<div class="germinare-topbar">
    <div style="display: flex; align-items: center;">
        <svg width="165" height="38" viewBox="0 0 210 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="germGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="#ff7a00" />
                    <stop offset="68%" stop-color="#e66a00" />
                    <stop offset="100%" stop-color="#5c2804" />
                </linearGradient>
            </defs>
            <!-- Folhinha verde saindo do topo direito da letra 'g' -->
            <path d="M22 14 C23 8, 29 6, 32 9 C29 13, 25 15, 22 14 Z" fill="#4caf50"/>
            <path d="M21 14 C19 10, 15 9, 13 11 C15 14, 18 15, 21 14 Z" fill="#388e3c"/>
            <!-- Palavra germinare unida sem espaços -->
            <text x="4" y="33" font-family="'Inter', 'Segoe UI', sans-serif" font-size="31" font-weight="300" letter-spacing="-0.8" fill="url(#germGrad)">germinare</text>
        </svg>
    </div>
    <div class="germinare-top-right">Inteligência em insumos</div>
</div>
""",
    unsafe_allow_html=True,
)


# 3. FUNÇÃO DE LEITURA DO JSON (API DO GITHUB)
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
    except Exception:
      pass
  if os.path.exists("boletim_atual.json"):
    try:
      with open("boletim_atual.json", "r", encoding="utf-8") as f:
        conteudo = f.read()
        if conteudo.strip():
          return limpar_e_ler_json(conteudo)
    except Exception as e:
      st.error(f"Erro no JSON: {e}")
      return None
  return None


url_padrao = "[https://raw.githubusercontent.com/luan238/painel-inteligencia-agro/main/boletim_atual.json](https://raw.githubusercontent.com/luan238/painel-inteligencia-agro/main/boletim_atual.json)"
dados = carregar_dados_boletim(url_padrao)
if not dados:
  st.stop()

# 4. SIDEBAR IDÊNTICA À FOTO
st.sidebar.markdown(
    '<div class="sidebar-section-title">CONFIGURAÇÕES DA ANÁLISE</div>',
    unsafe_allow_html=True,
)

culturas_lista = list(dados["blocos_culturas"].keys())
cultura_foco_sidebar = st.sidebar.selectbox(
    "Filtro de Complexo / Cadeia", culturas_lista
)
praca_referencia = st.sidebar.text_input(
    "Praça de Cotação / Foco", value="Triângulo Mineiro / MT / CBOT"
)
perfil_decisao = st.sidebar.selectbox(
    "Formato de Visão Estratégica",
    [
        "Todos os Perfis (Completa)",
        "Produtores Rurais",
        "Indústrias e Confinamentos",
        "Cooperativas e Revendas",
        "Tradings e Exportadores",
    ],
)

st.sidebar.markdown(
    '<div class="sidebar-section-title">COTAÇÕES DO DIA — REFERÊNCIA'
    " ATUAL</div>",
    unsafe_allow_html=True,
)
for item_pan in dados["panorama_geral"]:
  st.sidebar.text_input(item_pan["ativo"], value=item_pan["cotacao"])

st.sidebar.markdown(
    '<div class="sidebar-section-title">SINCRONIZAÇÃO API GITHUB</div>',
    unsafe_allow_html=True,
)
url_api = st.sidebar.text_input("Endpoint JSON", value=url_padrao)
if st.sidebar.button("🔄 Atualizar Boletim Agora", use_container_width=True):
  st.cache_data.clear()
  st.rerun()

# 5. CABEÇALHO PRINCIPAL ("Market Intelligence Pro") E CAIXA DE REFERÊNCIA
st.markdown(
    '<div class="main-title">Market Intelligence <span>Pro</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="main-subtitle">Monitoramento de grãos, coprodutos, pecuária,'
    " trading cambial e projeções auditáveis —"
    f" {dados['metadata']['titulo_edicao']} ({dados['metadata']['data_hora']})</div>",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="ref-box">
    <b>Resumo Executivo do Turno (Versão Falada).</b> {dados['metadata']['resumo_falado']}
</div>
""",
    unsafe_allow_html=True,
)

# 6. ABAS NO ESTILO DO NUTRE COMPARE PRO
aba_panorama, aba_culturas, aba_noticias, aba_cambio, aba_projecoes = st.tabs([
    "Panorama & Cotações",
    "Análise por Cultura & Trading",
    "Central de Notícias & Links",
    "Simulador NDF & Câmbio",
    "Base de Projeções & Mentoria",
])

# ABA 1: PANORAMA & COTAÇÕES
with aba_panorama:
  st.markdown(
      '<div style="font-size:15px; font-weight:600; color:#ffffff;'
      ' margin-top:6px;"><span style="color:#ff7a00;">▼</span> Ativos'
      " monitorados neste boletim</div>",
      unsafe_allow_html=True,
  )
  pills_html = "".join([
      f'<span class="pill-active">☑ {c["ativo"].split("(")[0].strip()}</span>'
      for c in dados["panorama_geral"]
  ])
  st.markdown(
      f'<div class="Filter-pills-row">{pills_html}<span class="pill-green">🌱'
      f' Turno: {dados["metadata"]["data_hora"]}</span></div>',
      unsafe_allow_html=True,
  )

  st.markdown(
      f'<div class="section-header">Fechamento e Drivers — Praça:'
      f" {praca_referencia}</div>",
      unsafe_allow_html=True,
  )

  cols = st.columns(2)
  for idx, item in enumerate(dados["panorama_geral"]):
    with cols[idx % 2]:
      st.markdown(
          f"""
            <div class="nutre-card">
                <div class="nutre-card-label">{item['ativo']}</div>
                <div class="nutre-card-value">{item['cotacao']}</div>
                <div class="nutre-card-unit">{item['destaque']}</div>
                <div class="nutre-card-footer">
                    <span>ⓘ Impacto analisado nos blocos de cultura e na mesa de trading</span>
                </div>
            </div>
            """,
          unsafe_allow_html=True,
      )

# ABA 2: ANÁLISE POR CULTURA & TRADING
with aba_culturas:
  cultura_sel = st.selectbox(
      "Selecione o Complexo para detalhamento:",
      culturas_lista,
      index=culturas_lista.index(cultura_foco_sidebar),
  )
  bloco = dados["blocos_culturas"][cultura_sel]

  st.markdown(
      f'<div class="section-header">{cultura_sel} — Análise Fundamentalista &'
      " Trading</div>",
      unsafe_allow_html=True,
  )

  st.markdown(
      f"""
    <div class="ref-box">
        <b>🧭 Viés de Mercado:</b> {bloco['vies_mercado']}<br><br>
        <b>Resumo Executivo:</b> {bloco['resumo_executivo']}
    </div>
    """,
      unsafe_allow_html=True,
  )

  st.markdown("**Posicionamento de Mesa (Commodities & Dólar)**")
  col_t1, col_t2 = st.columns(2)
  with col_t1:
    st.markdown(
        f"""
        <div class="nutre-card">
            <div class="nutre-card-label">Visão do Trader (Long / Short & Derivativos)</div>
            <div class="nutre-card-value" style="font-size:18px; color:#ff7a00;">Estratégia Direcional e Spreads</div>
            <div class="nutre-card-unit" style="color:#d4d4d4; font-size:13.5px;">{bloco['visao_trader'].get('Direcional e Spreads', '')}</div>
            <div class="nutre-card-footer"><span>ⓘ Operação tática CBOT / B3 / ICE</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
  with col_t2:
    st.markdown(
        f"""
        <div class="nutre-card">
            <div class="nutre-card-label">Mesa de Câmbio Aplicada à Cultura</div>
            <div class="nutre-card-value" style="font-size:18px; color:#4caf50;">Cross-Hedge & Trava de NDF</div>
            <div class="nutre-card-unit" style="color:#d4d4d4; font-size:13.5px;">{bloco['visao_trader'].get('Cross-Hedge e Trading do Dólar', '')}</div>
            <div class="nutre-card-footer"><span style="color:#4caf50;">ⓘ Arbitragem Selic vs. Cupom Cambial</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

  st.markdown("**Indicações Estratégicas por Elo da Cadeia**")
  perfis_exibir = (
      [
          "Produtores Rurais",
          "Cooperativas e Revendas",
          "Indústrias e Confinamentos",
          "Tradings e Exportadores",
      ]
      if perfil_decisao == "Todos os Perfis (Completa)"
      else [perfil_decisao]
  )
  cols_p = st.columns(2)
  for i, p_nome in enumerate(perfis_exibir):
    with cols_p[i % 2]:
      st.markdown(
          f"""
            <div class="nutre-card">
                <div class="nutre-card-label">Recomendação Direcionada</div>
                <div class="nutre-card-value" style="font-size:19px;">{p_nome}</div>
                <div class="nutre-card-unit" style="color:#d4d4d4; font-size:13.5px;">{bloco['consultoria'].get(p_nome, '')}</div>
                <div class="nutre-card-footer"><span>ⓘ Diretriz comercial atualizada</span></div>
            </div>
            """,
          unsafe_allow_html=True,
      )

# ABA 3: CENTRAL DE NOTÍCIAS & LINKS
with aba_noticias:
  st.markdown(
      '<div class="section-header">Central de Notícias, Fundamentos e Links'
      " Diretos</div>",
      unsafe_allow_html=True,
  )

  for nome_cultura, bloco_c in dados["blocos_culturas"].items():
    for noticia in bloco_c["noticias_detalhadas"]:
      links_html = " &nbsp;|&nbsp; ".join([
          f'<a href="{l["url"]}" target="_blank" class="nutre-link">ⓘ Link'
          f' {i}: {l["titulo_link"]}</a>'
          for i, l in enumerate(noticia["links"], 1)
      ])
      st.markdown(
          f"""
            <div class="nutre-card">
                <div class="nutre-card-label">{nome_cultura}</div>
                <div class="nutre-card-value" style="font-size:19px;">{noticia['titulo']}</div>
                <div class="nutre-card-unit" style="color:#d4d4d4; font-size:13.8px;">
                    {noticia['resumo_noticia']}<br><br>
                    <b style="color:#ff7a00;">O que afeta na Visão Trading:</b> {bloco_c['visao_trader'].get('Direcional e Spreads', '')}
                </div>
                <div class="nutre-card-footer">
                    {links_html}
                </div>
            </div>
            """,
          unsafe_allow_html=True,
      )

# ABA 4: SIMULADOR NDF & MESA DE CÂMBIO
with aba_cambio:
  cambio = dados["mesa_cambio"]
  st.markdown(
      '<div class="section-header">Mesa de Câmbio (FX Desk) & Simulador de'
      " NDF</div>",
      unsafe_allow_html=True,
  )

  col_c1, col_c2, col_c3 = st.columns(3)
  with col_c1:
    st.markdown(
        f'<div class="nutre-card"><div class="nutre-card-label">Dólar Comercial'
        f' (Spot)</div><div class="nutre-card-value">{cambio["spot"]}</div>'
        '<div class="nutre-card-footer"><span>ⓘ Referência à'
        " vista</span></div></div>",
        unsafe_allow_html=True,
    )
  with col_c2:
    st.markdown(
        f'<div class="nutre-card"><div class="nutre-card-label">Dólar Futuro'
        ' (Nov/26 B3)</div><div'
        f' class="nutre-card-value">{cambio["futuro_nov"]}</div><div'
        ' class="nutre-card-footer"><span>ⓘ Contrato'
        " WDO/DOL</span></div></div>",
        unsafe_allow_html=True,
    )
  with col_c3:
    st.markdown(
        f'<div class="nutre-card"><div class="nutre-card-label">NDF Colheita'
        ' Soja (Mar/27)</div><div class="nutre-card-value"'
        f' style="color:#4caf50;">{cambio["ndf_marco27_estimado"]}</div><div'
        ' class="nutre-card-footer"><span style="color:#4caf50;">ⓘ Prêmio de'
        " Carrego</span></div></div>",
        unsafe_allow_html=True,
    )

  st.markdown(
      f"""
    <div class="ref-box">
        <b>Diretriz da Mesa de Câmbio:</b> {cambio['decisao_mesa']}<br>
        <b>Racional Macro e Fluxo:</b> {cambio['racional']}
    </div>
    """,
      unsafe_allow_html=True,
  )

  st.markdown("**Simulador de Cálculo de NDF (Selic vs. Cupom Cambial)**")
  cc1, cc2, cc3 = st.columns(3)
  with cc1:
    dolar_spot_in = st.number_input(
        "Dólar Spot Hoje (R$)", value=5.0700, step=0.0100, format="%.4f"
    )
    preco_saca_usd = st.number_input(
        "Preço da Saca em US$", value=27.50, step=0.10
    )
  with cc2:
    taxa_di = st.number_input(
        "Taxa DI / Selic (% a.a.)", value=11.50, step=0.25
    )
    cupom_cambial = st.number_input(
        "Cupom Cambial (% a.a.)", value=4.80, step=0.10
    )
  with cc3:
    dias_uteis = st.number_input("Dias Úteis (Base 252)", value=111, step=1)
    dias_corridos = st.number_input(
        "Dias Corridos (Base 360)", value=163, step=1
    )

  fator_real = (1 + (taxa_di / 100)) ** (dias_uteis / 252)
  fator_dolar = 1 + ((cupom_cambial / 100) * (dias_corridos / 360))
  dolar_futuro_calc = dolar_spot_in * (fator_real / fator_dolar)
  forward_points = dolar_futuro_calc - dolar_spot_in
  saca_spot = preco_saca_usd * dolar_spot_in
  saca_ndf = preco_saca_usd * dolar_futuro_calc

  rc1, rc2 = st.columns(2)
  with rc1:
    st.markdown(
        f"""
        <div class="nutre-card">
            <div class="nutre-card-label">Dólar Futuro / NDF Calculado</div>
            <div class="nutre-card-value">R$ {dolar_futuro_calc:.4f}</div>
            <div class="nutre-card-unit">Forward Points (Ganho de Carrego): +R$ {forward_points:.4f} por dólar</div>
            <div class="nutre-card-footer"><span>ⓘ Como essa conta é feita? Arbitragem DI (252 du) vs Cupom (360 dc)</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
  with rc2:
    st.markdown(
        f"""
        <div class="nutre-card">
            <div class="nutre-card-label">Receita na Saca de Soja (Travando NDF vs Spot)</div>
            <div class="nutre-card-value" style="color:#4caf50;">R$ {saca_ndf:.2f} <span style="font-size:14px; color:#8c8c8c;">(vs R$ {saca_spot:.2f} no Spot)</span></div>
            <div class="nutre-card-unit">Ganho líquido pelo carrego cambial: <b>+R$ {(saca_ndf - saca_spot):.2f} por saca</b></div>
            <div class="nutre-card-footer"><span style="color:#4caf50;">ⓘ Ganho financeiro puro sem depender de alta do Dólar Spot</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ABA 5: BASE DE PROJEÇÕES AUDITÁVEIS & MENTORIA
with aba_projecoes:
  st.markdown(
      '<div class="section-header">Pílula de Inteligência de Mercado (Mentoria'
      " do Turno)</div>",
      unsafe_allow_html=True,
  )
  st.markdown(
      f"""
    <div class="nutre-card">
        <div class="nutre-card-label">Conceito Técnico de Consultoria</div>
        <div class="nutre-card-value" style="font-size:20px; color:#ff7a00;">{dados['pilula_mentoria']['titulo']}</div>
        <div class="nutre-card-unit" style="color:#d4d4d4; font-size:14px; white-space:pre-line;">{dados['pilula_mentoria']['conteudo']}</div>
        <div class="nutre-card-footer"><span>ⓘ Aplicação direta em reuniões comerciais e de inteligência</span></div>
    </div>
    """,
      unsafe_allow_html=True,
  )

  st.markdown(
      '<div class="section-header">Matriz de Projeções Auditáveis (Backtesting'
      " Semanal e Mensal)</div>",
      unsafe_allow_html=True,
  )
  df_proj = pd.DataFrame(dados["matriz_projecoes"])
  st.dataframe(df_proj, use_container_width=True, hide_index=True)
