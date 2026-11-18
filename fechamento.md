TURNO: {turno} — {data_hora}

Abaixo estão os resumos JÁ VERIFICADOS de cada bloco, os principais fatos e o cálculo do NDF.

RESUMOS DOS BLOCOS:
{resumos}

FATOS PRINCIPAIS:
{fatos}

CALCULO DO NDF (feito pelo sistema):
{ndf}

Responda com um JSON neste formato exato:
{{
  "escopo": "frase de até 160 caracteres resumindo o turno (aparece no topo do painel)",
  "pilula": {{
    "titulo": "título da pílula de inteligência de mercado (até 110 caracteres)",
    "analise": "até 150 palavras: explique um conceito técnico (NDF, cupom cambial, basis, spread calendário, carrego, paridade de exportação...) aplicado aos números de hoje",
    "conclusao": "1 a 2 frases com a conclusão estratégica"
  }},
  "roteiro_audio": "texto corrido de 300 a 450 palavras para ser lido em voz alta (2 a 3 minutos): abra com saudação, dia e horário; passe por câmbio e macro, soja, milho e trigo, algodão, café e pecuária; termine com 'Vamos às tabelas e ao painel'. Use algarismos para os números."
}}
