# Checagem de fontes — 18/11/2026 10:14

## Cotações

| Indicador | Fonte | Status | Detalhe |
|---|---|---|---|
| dolar_ptax | Banco Central do Brasil | ✅ ok | 40 valor(es); último 5.7851 em 17/11/2026 · PTAX venda — boletim de fechamento 17/11/2026 13:07 (API olinda.bcb.gov.br) |
| dolar_ptax | Yahoo Finance (checagem) | ⏸️ inativa | fonte desativada na configuração |
| dolar_futuro_b3 | B3 Agro | ✅ ok | 1 valor(es); último 5786.407 em 17/11/2026 · DOLZ26 · preço de ajuste (boletim oficial da B3) |
| selic_meta | Banco Central do Brasil | ✅ ok | 61 valor(es); último 13.75 em 18/11/2026 · SGS série 432 (API api.bcb.gov.br) |
| petroleo_wti | EIA (governo dos EUA) | ⏸️ inativa | opcional — defina o secret EIA_API_KEY no GitHub para ativar |
| petroleo_brent | EIA (governo dos EUA) | ⏸️ inativa | opcional — defina o secret EIA_API_KEY no GitHub para ativar |
| soja_cbot | BCR – Bolsa de Comercio de Rosario | ❌ erro | a tabela mudou: 13 colunas em vez de 7 · cabeçalhos=['Precios de cierr', '', '17/11/2026'] · linhas=[['Dic-26', '218,72', '2,94', '232,59', '5,14', '175,88', '- |
| farelo_cbot | BCR – Bolsa de Comercio de Rosario | ❌ erro | a tabela mudou: 13 colunas em vez de 7 · cabeçalhos=['Precios de cierr', '', '17/11/2026'] · linhas=[['Dic-26', '218,72', '2,94', '232,59', '5,14', '175,88', '- |
| oleo_soja_cbot | BCR – Bolsa de Comercio de Rosario | ❌ erro | a tabela mudou: 13 colunas em vez de 7 · cabeçalhos=['Precios de cierr', '', '17/11/2026'] · linhas=[['Dic-26', '218,72', '2,94', '232,59', '5,14', '175,88', '- |
| soja_paranagua | Canal Rural | ✅ ok | 1 valor(es); último 169.0 em 17/11/2026 · regex 'Paranagu[aá]\s+PR\s+[^$]{0,40}?R\$\s*([\' |
| soja_parana | Canal Rural | ✅ ok | 1 valor(es); último 158.0 em 17/11/2026 · regex 'Cascavel\s+PR\s+[^$]{0,40}?R\$\s*([\d.]+' |
| soja_uberlandia | Agrolink | ✅ ok | 1 valor(es); último 155.0 em 18/11/2026 · tabela '' · linha '' · coluna 'Preço (R$)' · data não informada na página |
| soja_b3 | B3 Agro | ✅ ok | 1 valor(es); último 27.0172 em 17/11/2026 · SJCF27 · preço de ajuste (boletim oficial da B3) |
| soja_rosario | BCR – Bolsa de Comercio de Rosario | ✅ ok | 1 valor(es); último 550000.0 em 18/11/2026 · tabela 'Precios Cámara Arbitral de Cereales de Rosario* / Cotizacion' · linha 'Soja' · coluna '1ª coluna numérica'  |
| milho_cbot | BCR – Bolsa de Comercio de Rosario | ❌ erro | a tabela mudou: 13 colunas em vez de 7 · cabeçalhos=['Precios de cierr', '', '17/11/2026'] · linhas=[['Dic-26', '218,72', '2,94', '232,59', '5,14', '175,88', '- |
| milho_campinas | Canal Rural | ✅ ok | 1 valor(es); último 67.5 em 17/11/2026 · regex 'Campinas\s+SP\s+[^$]{0,40}?R\$\s*([\d.]+' |
| milho_b3 | B3 Agro | ✅ ok | 1 valor(es); último 71.1 em 17/11/2026 · CCMF27 · preço de ajuste (boletim oficial da B3) |
| milho_b3_2 | B3 Agro | ✅ ok | 1 valor(es); último 75.45 em 17/11/2026 · CCMH27 · preço de ajuste (boletim oficial da B3) |
| trigo_cbot | BCR – Bolsa de Comercio de Rosario | ❌ erro | a tabela mudou: 13 colunas em vez de 7 · cabeçalhos=['Precios de cierr', '', '17/11/2026'] · linhas=[['Dic-26', '218,72', '2,94', '232,59', '5,14', '175,88', '- |
| trigo_parana | Canal Rural | ✅ ok | 1 valor(es); último 1550.0 em 17/11/2026 · regex 'Ponta Grossa\s+PR\s+[^$]{0,40}?R\$\s*([\' |
| trigo_rs | Canal Rural | ✅ ok | 1 valor(es); último 1630.0 em 17/11/2026 · regex 'Porto Alegre\s+RS\s+[^$]{0,40}?R\$\s*([\' |
| algodao_cepea | Canal Rural | ✅ ok | 1 valor(es); último 396.0 em 17/11/2026 · regex 'Rondon[oó]polis\s+MT\s+[^$]{0,40}?R\$\s*' · convertido de R$/lb (×100) |
| cafe_arabica_cepea | Canal Rural | ✅ ok | 1 valor(es); último 1830.0 em 17/11/2026 · regex 'Sul de Minas\s+MG\s+[^$]{0,40}?R\$\s*([\' |
| cafe_manhuacu | Agrolink | ✅ ok | 1 valor(es); último 1688.0 em 18/11/2026 · tabela '' · linha '' · coluna '1ª coluna numérica' · data não informada na página |
| boi_gordo_cepea | Canal Rural | ✅ ok | 1 valor(es); último 395.0 em 17/11/2026 · regex 'S[aã]o Paulo\s+SP\s+arroba\s+R\$\s*([\d.' |
| boi_b3 | B3 Agro | ✅ ok | 1 valor(es); último 398.5 em 17/11/2026 · BGIX26 · preço de ajuste (boletim oficial da B3) |

## Notícias

| Fonte | Região | Status | Modo | Na janela | Lidos | Feed / mensagem |
|---|---|---|---|---|---|---|
| Farmnews | Brasil | ✅ ok | rss | 7 | 7 | https://www.farmnews.com.br/feed/ |
| AgFeed | Brasil | ✅ ok | rss | 7 | 10 | https://agfeed.com.br/feed/ |
| Canal Rural | Brasil | ✅ ok | rss | 10 | 10 | https://www.canalrural.com.br/feed/ |
| Globo Rural | Brasil | ✅ ok | rss | 27 | 30 | https://globorural.globo.com/rss/globorural |
| Agrolink | Brasil | ✅ ok | rss | 30 | 30 | https://www.agrolink.com.br/rss/noticias.rss |
| Money Times Agro | Brasil | ✅ ok | rss | 10 | 10 | https://www.moneytimes.com.br/feed/ |
| CONAB | Brasil | ✅ ok | pagina | 0 | 2 |  |
| Bolsa de Cereales de Buenos Aires | Argentina | ❌ falha | — | 0 | 0 | página e feed inacessíveis |
| BCR – Bolsa de Comercio de Rosario | Argentina | ⚠️ sem_itens | pagina | 0 | 0 | nenhuma matéria reconhecida na página |
| Infobae Campo | Argentina | ✅ ok | pagina | 0 | 10 |  |
| Clarín Rural | Argentina | ✅ ok | rss | 10 | 10 | https://www.clarin.com/rss |
| Pro Farmer | Internacional | ✅ ok | pagina | 7 | 8 |  |
| Barchart Grains | Internacional | ❌ falha | — | 0 | 0 | página e feed inacessíveis |
| Reuters Commodities | Internacional | 🚫 robots | — | 0 | 0 | robots.txt de www.reuters.com não permite ler https://www.reuters.com/markets/commodities/ |
| Bloomberg Agriculture | Internacional | ❌ falha | — | 0 | 0 | página e feed inacessíveis |
| USDA WASDE | Internacional | 🚫 robots | — | 0 | 0 | robots.txt de www.usda.gov não permite ler https://www.usda.gov/oce/commodity/wasde |
| USDA FAS | Internacional | 🚫 robots | — | 0 | 0 | robots.txt de www.fas.usda.gov não permite ler https://www.fas.usda.gov/ |
| Grain Central | Internacional | 🚫 robots | — | 0 | 0 | robots.txt de www.graincentral.com não permite ler https://www.graincentral.com/ |
| Successful Farming | Internacional | ❌ falha | — | 0 | 0 | página e feed inacessíveis |
| AgWeb | Internacional | ❌ falha | — | 0 | 0 | página e feed inacessíveis |
| World Grain | Internacional | ✅ ok | pagina | 5 | 10 |  |
| eFeedLink | China | ✅ ok | rss | 30 | 30 | https://www.efeedlink.com/rss.xml |
| CZ App / China Agri | China | ❌ falha | — | 0 | 0 | página e feed inacessíveis |
| SunSirs | China | ⚠️ sem_itens | pagina | 0 | 0 | nenhuma matéria reconhecida na página |
| Reuters China Agri | China | 🚫 robots | — | 0 | 0 | robots.txt de www.reuters.com não permite ler https://www.reuters.com/world/china/ |

Legenda: ✅ ok · ❌ erro · 🚫 bloqueado pelo robots.txt do site · ⚠️ sem itens · ⏸️ desativada