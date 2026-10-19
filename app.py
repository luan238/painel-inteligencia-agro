import json
import os
import pandas as pd
import requests
import streamlit as st

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(
    page_title="Agente de Inteligência de Mercado Agro",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Função auxiliar que limpa crases ```json caso tenham sido coladas sem querer
def limpar_e_ler_json(texto_bruto):
  texto = texto_bruto.strip()
  if texto.startswith("```json"):
    texto = texto[7:]
  elif texto.startswith("```"):
    texto = texto[3:]
  if texto.endswith("```"):
    texto = texto[:-3]
  texto = texto.strip()
  return json.loads(texto)


# 2. FUNÇÃO PARA LER A "API" DO GITHUB (OU ARQUIVO LOCAL)
@st.cache_data(ttl=30)
def carregar_dados_boletim(url_raw_github=None):
  # Tenta primeiro pela URL Raw se fornecida
  if url_raw_github and url_raw_github.startswith("http"):
    try:
      resposta = requests.get(url_raw_github, timeout=10)
      if resposta.status_code == 200 and resposta.text.strip():
        return limpar_e_ler_json(resposta.text)
    except Exception as e:
      st.sidebar.warning(f"Aviso na URL remota: {e}")

  # Tenta ler o arquivo boletim_atual.json direto do repositório
  if os.path.exists("boletim_atual.json"):
    try:
      with open("boletim_atual.json", "r", encoding="utf-8") as f:
        conteudo = f.read()
        if conteudo.strip():
          return limpar_e_ler_json(conteudo)
    except Exception as e:
      st.error(f"⚠️ Erro de formatação no arquivo `boletim_atual.json`: {e}")
      st.info(
          "Dica: Verifique no GitHub se o arquivo `boletim_atual.json` começa"
          " exatamente com `{` e termina com `}`."
      )
      return None
  return None


# 3. BARRA LATERAL
st.sidebar.title("🌾 Inteligência Agro")
st.sidebar.caption("Painel Integrado ao Agente de Mercado")

url_padrao = "[https://raw.githubusercontent.com/luan238/painel-inteligencia-agro/main/boletim_atual.json](https://raw.githubusercontent.com/luan238/painel-inteligencia-agro/main/boletim_atual.json)"
url_api = st.sidebar.text_input(
    "🔗 Link Raw JSON do GitHub:",
    value=url_padrao,
    help=(
        "Link direto da sua API no GitHub para atualização instantânea sem"
        " reiniciar o app."
    ),
)

if st.sidebar.button("🔄 Forçar Atualização da API"):
  st.cache_data.clear()
  st.rerun()

dados = carregar_dados_boletim(url_api)

if not dados:
  st.stop()

# 4. CABEÇALHO E RESUMO FALADO
st.title("📊 Painel de Inteligência de Mercado Agrícola")
st.markdown(
    f"**Turno:** `{dados['metadata']['titulo_edicao']}` | **Atualização:**"
    f" `{dados['metadata']['data_hora']}`"
)

with st.expander("🔊 Ouvir / Ler Resumo Falado do Turno (Boletim Executivo)"):
  st.info(dados["metadata"]["resumo_falado"])

st.markdown("---")

# 5. ESTRUTURA DE ABAS PRINCIPAIS DO PAINEL
(
    aba_panorama,
    aba_culturas,
    aba_noticias,
    aba_cambio,
    aba_mentoria,
    aba_projecoes,
) = st.tabs([
    "📌 1. Panorama do Turno",
    "🌱 2. Análise por Cultura & Trading",
    "📰 3. Central de Notícias & Links",
    "💵 4. Mesa de Câmbio & Calc. NDF",
    "🧠 5. Pílula de Mentoria",
    "🎯 6. Projeções Auditáveis (Backtesting)",
])

# ABA 1: PANORAMA GERAL DO TURNO
with aba_panorama:
  st.subheader("1. Panorama Consolidado do Turno")
  df_panorama = pd.DataFrame(dados["panorama_geral"])
  df_panorama.columns = [
      "Indicador / Ativo",
      "Cotação / Referência Atual",
      "Destaque e Gatilhos de Mercado",
  ]
  st.dataframe(df_panorama, use_container_width=True, hide_index=True)

# ABA 2: ANÁLISE POR CULTURA, PERFIS E VISÃO DO TRADER
with aba_culturas:
  st.subheader("2. Análise Detalhada por Cultura / Commodity")
  culturas_disponiveis = list(dados["blocos_culturas"].keys())
  cultura_selecionada = st.selectbox(
      "Selecione o Complexo / Commodity:", culturas_disponiveis
  )
  bloco = dados["blocos_culturas"][cultura_selecionada]

  st.warning(f"🧭 **Viés de Mercado:** {bloco['vies_mercado']}")
  st.markdown("#### A. Resumo Executivo (O que está movendo o mercado)")
  st.write(bloco["resumo_executivo"])

  st.markdown("#### B. Fatos Geradores, Dados de Campo e Links das Fontes")
  for idx, noticia in enumerate(bloco["noticias_detalhadas"], 1):
    with st.container(border=True):
      st.markdown(f"**{idx}. {noticia['titulo']}**")
      st.write(noticia["resumo_noticia"])
      st.markdown("**🔗 Links diretos das matérias para aprofundamento:**")
      for link_obj in noticia["links"]:
        st.markdown(f"- 🌐 [{link_obj['titulo_link']}]({link_obj['url']})")

  st.markdown("---")
  st.markdown("#### C. Indicações Estratégicas por Elo da Cadeia")
  col_cons1, col_cons2 = st.columns(2)

  with col_cons1:
    st.success(
        "**🚜 Para Produtores Rurais:**\n\n"
        + bloco["consultoria"].get("Produtores Rurais", "")
    )
    st.info(
        "**🤝 Para Cooperativas e Revendas:**\n\n"
        + bloco["consultoria"].get("Cooperativas e Revendas", "")
    )

  with col_cons2:
    st.warning(
        "**🐄 Para Indústrias e Confinamentos/Nutrição:**\n\n"
        + bloco["consultoria"].get("Indústrias e Confinamentos", "")
    )
    st.info(
        "**🚢 Para Tradings e Exportadores:**\n\n"
        + bloco["consultoria"].get("Tradings e Exportadores", "")
    )

  st.markdown("#### 📈 Visão do Trader (Long / Short, Derivativos e Câmbio)")
  col_tr1, col_tr2 = st.columns(2)
  with col_tr1:
    st.error(
        "**🎯 Posicionamento Direcional e Spreads:**\n\n"
        + bloco["visao_trader"].get("Direcional e Spreads", "")
    )
  with col_tr2:
    st.error(
        "**💵 Cross-Hedge e Trading do Dólar na Cultura:**\n\n"
        + bloco["visao_trader"].get("Cross-Hedge e Trading do Dólar", "")
    )

# ABA 3: CENTRAL DE NOTÍCIAS E LINKS
with aba_noticias:
  st.subheader(
      "📰 Hub de Notícias do Boletim (Resumo + Impacto no Trading + Links)"
  )
  st.markdown(
      "Acesse rapidamente o resumo de cada notícia que compôs a análise do"
      " turno e clique nos links abaixo para ler a matéria completa."
  )

  filtro_cultura_not = st.multiselect(
      "Filtrar notícias por Complexo:",
      options=list(dados["blocos_culturas"].keys()),
      default=list(dados["blocos_culturas"].keys()),
  )

  for nome_cultura in filtro_cultura_not:
    bloco_c = dados["blocos_culturas"][nome_cultura]
    st.markdown(f"### 📌 {nome_cultura}")
    st.caption(
        "**Impacto no Trading:**"
        f" {bloco_c['visao_trader'].get('Direcional e Spreads', '')}"
    )

    for noticia in bloco_c["noticias_detalhadas"]:
      with st.container(border=True):
        st.markdown(f"#### 🗞️ {noticia['titulo']}")
        st.write(noticia["resumo_noticia"])
        st.markdown("**Fontes oficiais e reportagens completas:**")
        for i, link_obj in enumerate(noticia["links"], 1):
          st.markdown(
              f"**Link {i}:** [{link_obj['titulo_link']}]({link_obj['url']})"
          )

# ABA 4: MESA DE CÂMBIO E CALCULADORA DE DÓLAR FUTURO (NDF)
with aba_cambio:
  st.subheader("💵 Visão da Mesa de Câmbio (FX Desk) & Hedge Cambial")
  cambio = dados["mesa_cambio"]

  c1, c2, c3 = st.columns(3)
  c1.metric("Dólar Comercial (Spot)", cambio["spot"])
  c2.metric("Dólar Futuro (Nov/26 B3)", cambio["futuro_nov"])
  c3.metric("NDF Colheita Soja (Mar/27)", cambio["ndf_marco27_estimado"])

  st.info(f"**🎯 Decisão da Mesa de Câmbio:** {cambio['decisao_mesa']}")
  st.write(f"**Racional Macro e Fluxo:** {cambio['racional']}")

  st.markdown("---")
  st.subheader(
      "🧮 Simulador de Dólar Futuro / NDF e Impacto na Saca (Selic vs. Cupom"
      " Cambial)"
  )
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
  fator_cambial = fator_real / fator_dolar
  dolar_futuro_calc = dolar_spot_in * fator_cambial
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
      f"+R$ {ganho_por_saca:.2f}/sc de ganho no câmbio!",
  )

# ABA 5: PÍLULA DE MENTORIA
with aba_mentoria:
  st.subheader("🧠 3. Pílula de Inteligência de Mercado (Mentoria do Turno)")
  st.markdown(f"### {dados['pilula_mentoria']['titulo']}")
  st.success(dados["pilula_mentoria"]["conteudo"])

# ABA 6: MATRIZ DE PROJEÇÕES AUDITÁVEIS
with aba_projecoes:
  st.subheader("🎯 Matriz de Projeções Auditáveis e Track Record")
  df_proj = pd.DataFrame(dados["matriz_projecoes"])
  st.dataframe(df_proj, use_container_width=True, hide_index=True)
