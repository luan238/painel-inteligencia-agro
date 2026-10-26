import os
import re
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types

# 1. Configura fuso horário de Brasília (BRT)
agora_brt = datetime.now(ZoneInfo("America/Sao_Paulo"))
data_str = agora_brt.strftime("%Y-%m-%d")
hora_str = agora_brt.strftime("%H:%M")
timestamp_iso = agora_brt.strftime("%Y-%m-%dT%H:%M:00-03:00")
id_relatorio = agora_brt.strftime("AGRI-INTEL-%Y-%m-%d-%H%M")

# Ajustado para 'Historico/' (com H maiúsculo para coincidir com a pasta do seu repositório)
nome_arquivo_historico = agora_brt.strftime("Historico/historico_%Y_%m_%d-%Hh.json")
nome_relatorio_md = agora_brt.strftime("Historico/relatorio_%Y_%m_%d-%Hh.md")

# 2. Carrega o boletim_atual.json anterior (se existir) para manter o histórico diário do gráfico
contexto_anterior = ""
if os.path.exists("boletim_atual.json"):
    with open("boletim_atual.json", "r", encoding="utf-8") as f:
        contexto_anterior = f.read()

# 3. Inicializa o cliente Gemini (a chave vem da variável de ambiente GEMINI_API_KEY)
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 4. Define o Prompt com as instruções exatas da nossa conversa
prompt = f"""
Data e Hora Atual da Execução: {data_str} às {hora_str} BRT (Timestamp: {timestamp_iso}).
Atue como Analista Sênior, Estrategista de Derivativos e Mentor de Inteligência de Mercado da Germinare Agro.

OBRIGATÓRIO: Utilize a ferramenta Google Search agora para buscar as cotações e notícias EM TEMPO REAL deste exato momento ({data_str} às {hora_str}) para:
- Dólar Comercial Spot (USD/BRL), Dólar Futuro B3 (WDO/DOL) e Petróleo (Brent e WTI);
- Complexo Soja (CBOT Grão, Farelo e Óleo, Indicador Esalq Paranaguá, Cepea PR, IMEA-MT, Triângulo-MG e Biodiesel);
- Complexo Milho, Etanol e DDGS (CBOT, Curva B3 Nov/Jan/Mar/Mai/Jul, Indicador Esalq, IMEA-MT, Pará de Minas-MG, Sul de MG e DDG FOB);
- Complexo Algodão (ICE NY, Cepea Pluma, Cotlook A e Arbitragem do Caroço de Algodão IMEA-MT vs. MG/GO/BA);
- Complexo Café (ICE NY Arábica, ICE Londres Robusta, B3, Indicadores Cepea e Cooperativas de MG: Expocaccer Patrocínio, Coocacer Araguari, Cooxupé Guaxupé, Machado e Vitória-ES).

Abaixo está o JSON do turno anterior para você manter a estrutura exata das chaves e atualizar a série diária (`daily_dates` e `daily_history`) até a data de hoje ({agora_brt.strftime('%d/%m')}):
{contexto_anterior}

Gere o relatório completo e, ao final, inclua OBRIGATORIAMENTE o bloco ```json ... ``` contendo o JSON completo, válido e atualizado com report_id "{id_relatorio}" e timestamp "{timestamp_iso}".
"""

print(f"🔄 Consultando Gemini com Pesquisa Google ao vivo ({timestamp_iso})...")

response = None
max_tentativas = 3

for tentativa in range(1, max_tentativas + 1):
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            ),
        )
        break  # Se deu certo, sai do loop
    except Exception as e:
        print(f"⚠️ Tentativa {tentativa} falhou: {e}")
        if tentativa < max_tentativas:
            print("⏳ Aguardando 20 segundos para tentar novamente...")
            time.sleep(20)
        else:
            raise e

texto_resposta = response.text

# 5. Extrai o bloco JSON da resposta
padrao_json = re.search(r"```json\s*(\{.*?\})\s*```", texto_resposta, re.DOTALL)
if not padrao_json:
    raise ValueError("❌ Não foi possível encontrar um bloco ```json válido na resposta do modelo.")

json_str = padrao_json.group(1).strip()

# Valida se o JSON está perfeitamente formatado antes de salvar
dados_json = json.loads(json_str)

# 6. Salva o boletim_atual.json (que alimenta o index.html)
with open("boletim_atual.json", "w", encoding="utf-8") as f:
    json.dump(dados_json, f, ensure_ascii=False, indent=2)
print("✅ Arquivo 'boletim_atual.json' atualizado com sucesso!")

# 7. Cria a pasta 'Historico/' e salva o NOVO arquivo JSON e o relatório em Markdown
os.makedirs("Historico", exist_ok=True)

with open(nome_arquivo_historico, "w", encoding="utf-8") as f:
    json.dump(dados_json, f, ensure_ascii=False, indent=2)
print(f"✅ Novo arquivo de histórico criado: '{nome_arquivo_historico}'")

with open(nome_relatorio_md, "w", encoding="utf-8") as f:
    f.write(texto_resposta)
print(f"✅ Relatório completo em texto salvo em: '{nome_relatorio_md}'")
