TURNO: {turno} — {data_hora}
BLOCO: {titulo_bloco}

Escreva a análise deste bloco usando exclusivamente os dados abaixo.

FATOS (cotações verificadas pelo sistema):
{fatos}

CALCULOS (spreads e indicadores calculados pelo sistema):
{calculos}

NOTICIAS (coletadas hoje nas fontes confiáveis; cite pelo ID):
{noticias}

Responda com um JSON neste formato exato:
{{
  "resumo_curto": "2 a 4 frases para o resumo executivo geral do turno, com os principais números do bloco",
  "manchete": "manchete curta do bloco (até 90 caracteres)",
  "vies": "1 frase com o viés de mercado e o ponto de atenção do bloco",
  "resumo_executivo": "1 parágrafo (80 a 160 palavras) ligando cotações e notícias, citando [N#]",
  "noticias_destaque": ["N#", "..."],
  "elos": [
{elos_formato}
  ],
  "drivers_semana": {{ {ids_semana} }},
  "narrativas_mes": {{ {ids_mes} }},
  "gatilhos": {{ {ids_projecao} }},
  "vieses_projecao": {{ {ids_vies} }}
}}

Instruções dos campos:
- "elos": um item para CADA elo, na mesma ordem e com o nome exatamente igual; "direcionamento" com 2 a 4 frases práticas para aquele elo; "referencias" com 1 a 3 IDs de notícias que embasam o texto (lista vazia se nenhuma notícia se aplica).
- "drivers_semana": 1 frase por indicador explicando o movimento da semana (use var_semana).
- "narrativas_mes": 1 a 2 frases por indicador sobre o acumulado do mês (use var_mes).
- "gatilhos": 1 frase por indicador com o evento ou condição que invalidaria o cenário atual. Não cite limites de banda.
- "vieses_projecao": "alta", "baixa" ou "neutro" para cada indicador — use "neutro" se os dados não sustentarem uma direção.
