# Consumo Nominal do Governo — Replicação Santos et al. (2015)

Replicação metodológica de:

> Santos, C. H. M. dos, et al. (2015). *Uma metodologia de estimação do consumo do
> governo em base trimestral*. IPEA Carta de Conjuntura nº 27.

## O que este projeto faz

Estima o consumo nominal do governo brasileiro em frequência trimestral usando dados
fiscais bimestrais do SICONFI RREO como indicador de alta frequência e a CNT anual
do IBGE como benchmark. A estimativa segue o método de desagregação proporcional
de Denton (1971).

**Cobertura:** 2015–presente (início do SICONFI). O artigo original cobre 2010–2014
com uma base de dados diferente; os números da Tabela 2 original não são
numericamente reproduzíveis aqui — o que se replica é a *metodologia*.

**Série vencedora (MSE vs CNT):** `estados_only_lef` — GND1 sem intra-orçamentárias,
estágio `liq_efetiva` (liquidado + RP Processados Pagos), 27 estados. MAPE = 2,40%,
RMSE = 12,0, correlação = 0,994 (2015–2025, 44 trimestres).

## Como executar

```bash
pip install -r requirements.txt

python download.py          # baixa CNT (IBGE), TRU, RREO Anexo 1 e RPPS Uniao 04.2/04.3
python build_indicators.py  # constroi grade de candidatos -> data/processed/
python replicate.py         # desagrega (Denton), rankeia, gera tabelas e grafico
python deflate.py           # serie real: deflator implicito CNT -> output/serie_real.csv
python nowcast.py           # nowcast Chow-Lin para trimestres sem CNT (extensao)
```

As saidas em `output/` nao sao versionadas. Reexecute os scripts acima para
regenera-las do zero a partir dos dados brutos.

## Estrutura

```
config.py            -- entidades, grade declarativa de candidatos, caminhos
download.py          -- baixa CNT (IBGE) + RREO (SICONFI) -> data/raw/
build_indicators.py  -- raw -> series trimestrais por componente e candidato
denton.py            -- desagregacao proporcional de Denton + helpers
replicate.py         -- roda a grade, rankeia por MSE, gera tabelas e grafico
deflate.py           -- serie real: deflator implicito CNT + crescimento a/a
nowcast.py           -- Chow-Lin AR(1) para trimestres sem CNT publicada (extensao)
docs/METODOLOGIA.md  -- detalhes metodologicos, schema SICONFI, validacao nowcast

data/raw/            -- dados brutos baixados (nao versionados)
data/processed/      -- series trimestrais intermediarias
output/              -- resultados finais (nao versionados)
```

## Saidas

| Arquivo | Conteudo |
|---------|----------|
| `output/ranking.csv` | Composites ordenados por MSE vs CNT |
| `output/diagnostico_blocos.csv` | Blocos atomicos individuais — diagnostico |
| `output/tabela2_desvios.csv` | Melhor serie vs CNT, desvios trimestrais (Tabela 2) |
| `output/tabela3_repres.csv` | Representatividade dos componentes vs TRU anual (Tabela 3) |
| `output/serie_real.csv` | Serie deflacionada + crescimento real a/a |
| `output/fig_serie.png` | Melhor serie vs CNT — linha (Grafico 1) |
| `output/nowcast.csv` | Estimativas Chow-Lin para trimestres sem CNT |
| `output/vintage_nowcast.csv` | Log append-only de todas as rodadas de nowcast |

## Configuracao

Parametros relevantes em `config.py`:

| Constante | Padrao | Quando alterar |
|-----------|--------|----------------|
| `YEAR_START` | `2015` | Se o SICONFI retroagir dados anteriores a 2015. |
| `YEAR_END` | `date.today().year` | Derivado automaticamente — nao requer edicao manual. |
| `TRU_EDITION` | `2021` | Quando o IBGE publicar SCN com TRU nao-nula por componente. Atualizar tambem `TRU_ZIP_URL`. |
| `RPPS_UNIAO_START_YEAR` | `2016` | Se o SICONFI retroagir Anexo 04.2/04.3 para antes de 2016. |
| `RPPS_UNIAO_ANEXOS` | `["RREO-Anexo 04.2", "RREO-Anexo 04.3"]` | Se o SICONFI adicionar novos sub-anexos RPPS. |
| `INCLUDE_MUNICIPIOS` | `False` | `True` ativa os 27 municipios-capital (piora MSE no periodo atual). |

## Nowcast (extensao, nao replicacao)

**Este modulo NAO faz parte da replicacao de Santos et al. (2015).** Os valores
produzidos por `nowcast.py` sao estimativas provisorias que serao revisadas quando o
IBGE publicar os dados oficiais. Registro historico: `output/vintage_nowcast.csv`
(append-only).

Metodo: **Chow-Lin AR(1) GLS**, rho por MV, correcao sazonal ex-post. Indicador:
`estados_only_lef`. Exclui 2020 do treinamento (quebra COVID). MAPE pseudo-OOS:
**2,34%** (rolling-origin 2023-2025, regime completo/parcial).

### Tres regimes

| `regime` | Quando | O que e projetado |
|----------|--------|-------------------|
| **completo** | Todos os bimestres do trimestre publicados | Indicador observado |
| **parcial** | Parte dos bimestres disponivel | Indicador escalado por razao historica |
| **projetado** | Nenhum bimestre do trimestre disponivel | Indicador via participacao sazonal x multiplicador LOO |

O regime muda automaticamente a cada nova rodada conforme novos bimestres chegam.
Regime `projetado`: MAPE Q3 ~3%, Q4 ~5% (validado em 6 origens, 2019-2025; horse
race de 4 metodos — vencedor: metodo B, multiplicador LOO).

Os multiplicadores de vies (`_PROJ_BIAS` em `nowcast.py`) **devem ser revistos
anualmente** com os erros ex-post de `vintage_nowcast.csv`. Derivacao, backtest
completo e analise de estabilidade: ver [`docs/METODOLOGIA.md`](docs/METODOLOGIA.md).

## Limitacoes

- **GND vs elemento de despesa:** SICONFI nao expoe codigos de elemento (319011 etc.); proxy e o total GND1. Ver `docs/METODOLOGIA.md`.
- **Restos a Pagar:** RP Processados Pagos sem pesos Finbra/EOE que o artigo aplicava. Ver `docs/METODOLOGIA.md`.
- **Contribuicoes imputadas:** cobertura parcial no SICONFI (militares 2018-2020, civis 2023+, estados 2021+). Ver `docs/METODOLOGIA.md`.
- **Municipios (capitais):** desativados por padrao; piora o MSE no periodo atual. Ver `docs/METODOLOGIA.md`.
- **TRU 2021:** ultima edicao com decomposicao nao-nula; Tabela 3 limitada a 2015-2021. Ver `docs/METODOLOGIA.md`.
- **Cobertura temporal:** 2015-presente; periodo 2010-2014 do artigo requer bases Finbra/EOE/SIGA Brasil nao disponiveis via API publica.

---

Detalhes metodologicos completos, descobertas de schema SICONFI e justificativas de
cada desvio do paper: ver [`docs/METODOLOGIA.md`](docs/METODOLOGIA.md).
