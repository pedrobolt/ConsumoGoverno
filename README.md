# Consumo Nominal do Governo — Replicação Santos et al. (2015)

Replicação metodológica de:

> Santos, C. H. M. dos, et al. (2015). *Uma metodologia de estimação do consumo do
> governo em base trimestral*. IPEA Carta de Conjuntura nº 27.

## O que este projeto faz

Estima o consumo nominal do governo brasileiro em frequência trimestral usando dados
fiscais bimestrais do SICONFI RREO como indicador de alta frequência e a CNT anual
do IBGE como benchmark. A estimativa segue o método de desagregação proporcional
de Denton (1971).

**Cobertura:** 2015–2025 (início do SICONFI). O artigo original cobre 2010–2014
com uma base de dados diferente; os números da Tabela 2 original não são
numericamente reproduzíveis aqui — o que se replica é a *metodologia*.

## Desvios em relação ao artigo original

| Aspecto | Artigo (2015) | Este projeto |
|---------|--------------|--------------|
| Cobertura temporal | 2010–2014 | 2015–2025 |
| Base fiscal subnacional | Finbra + EOE (pesos para RP) | SICONFI RREO (simplificado) |
| Restos a Pagar | Pesos Finbra/EOE por esfera | Soma direta SICONFI (ver nota) |
| Municípios | Capitais com ponderação | Capitais, sem ponderação (OFF por padrão) |

**Nota sobre Restos a Pagar:** O artigo usa pesos derivados do Finbra e do
Balanço do Setor Público (EOE) para distribuir RP entre esferas de governo.
Esses microdados não estão disponíveis publicamente no SICONFI; este projeto
usa a soma direta dos RP pagos reportados no RREO — uma aproximação simplificada.
O impacto é documentado no ranking de MSE (coluna `mse` em `output/ranking.csv`).

**Nota sobre Consumo Intermediário:** O artigo extraía CI do GND3 usando pesos
Finbra/EOE e o tradutor de contas IBGE(2008b), que não estão disponíveis.
Este projeto testa duas aproximações:

- `consumo_intermediario_gnd3` — total do GND3 ("OUTRAS DESPESAS CORRENTES"):
  teto, pois inclui itens que não são CI (transferências, multas, etc.).
- `consumo_intermediario_elem` — filtro pelos elementos 339030, 339036 e 339039:
  piso, pois pode excluir itens que o tradutor incluiria.

A Série 13 vencedora do artigo excluía CI inteiramente; esses candidatos existem
para completar o espaço de busca, sem expectativa de vitória no ranking.

## Estrutura

```
config.py            — entidades, grade declarativa de candidatos, caminhos
download.py          — baixa CNT (IBGE) + RREO (SICONFI) → data/raw/
build_indicators.py  — raw → séries trimestrais por componente e candidato
denton.py            — desagregação proporcional de Denton + helpers
replicate.py         — roda a grade, rankeia por MSE, gera tabelas e gráfico
deflate.py           — série real: deflator implícito CNT + crescimento a/a

data/raw/            — dados brutos baixados (não versionados)
data/processed/      — séries trimestrais intermediárias
output/              — resultados finais (não versionados)
```

## Como executar

```bash
pip install -r requirements.txt

python download.py          # baixa dados brutos (~10–20 min na primeira vez)
python build_indicators.py  # constrói grade de candidatos
python replicate.py         # desagrega, rankeia, gera tabelas e gráfico
```

## Saídas

| Arquivo | Conteúdo |
|---------|----------|
| `output/ranking.csv` | Todos os candidatos ordenados por MSE (≈ Anexo I) |
| `output/tabela2_desvios.csv` | Melhor série vs CNT, desvios trimestrais (Tabela 2) |
| `output/tabela3_repres.csv` | Representatividade dos componentes vs TRU anual (Tabela 3) |
| `output/serie_real.csv` | Série deflacionada + crescimento real a/a |
| `output/fig_serie.png` | Melhor série vs CNT — linha (Gráfico 1) |

## Fontes de dados

- **CNT (benchmark):** IBGE, Tab_Compl_CNT.zip — coluna "Consumo do Governo",
  valores correntes e índice de volume (base 2010=100).
- **SICONFI RREO:** Tesouro Nacional, apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo
  — Anexo 1 (Pessoal/GND) e Anexo 4 (RPPS/contrib. imputadas).

## O que este projeto NÃO é

Este projeto testa a **metodologia** de Santos et al. (2015) — desagregação
proporcional de Denton com indicadores SICONFI — sobre dados 2015–2025.

**Não reproduz numericamente** o Anexo I do artigo nem a Tabela 2: os dados
são diferentes (SICONFI vs Finbra/EOE, 2015–2025 vs 2010–2014) e a extração
de consumo intermediário é uma aproximação (sem o tradutor IBGE(2008b) + pesos
Finbra). Qualquer correspondência numérica com os resultados originais é
coincidência, não validação.

## Grade de indicadores

**Blocos atômicos** (`CANDIDATE_SPECS` em `config.py`): 22 séries trimestrais,
uma por combinação de esfera × estágio × componente × método de isolamento.
Alimentam os composites e o diagnóstico de blocos individuais.

**Séries compostas** (`COMPOSITES` em `config.py`): 10 séries economicamente
defensáveis (7 ativas por padrão), cada uma somando blocos atômicos antes do
Denton. Estas são o objeto principal do ranking por MSE.

| Série | Esferas | Componentes | Estágio |
|-------|---------|-------------|---------|
| uniao_only | U | sal+CE+CI | liquidado |
| estados_only | E | sal+CE | liquidado |
| uniao_estados | U+E | sal+CE | liquidado |
| uniao_estados_ci | U+E | sal+CE+contrib.imp | liquidado |
| estados_only_lef | E | sal+CE | liq_efetiva |
| uniao_estados_lef | U+E | sal+CE | liq_efetiva |
| estados_only_gnd1 | E | sal+CE (GND1) | liquidado |
| estados_munic* | E+M | sal+CE | liquidado |
| uniao_estados_munic* | U+E+M | sal+CE | liquidado |
| uniao_estados_munic_ci* | U+E+M | sal+CE+contrib.imp | liquidado |

\* Ativadas com `INCLUDE_MUNICIPIOS = True`.

O ranking por MSE vs CNT revela qual combinação de cobertura e estágio
melhor aproxima o consumo do governo trimestral. O diagnóstico de blocos
individuais (`output/diagnostico_blocos.csv`) indica qual componente isolado
tem maior correlação com a CNT — útil, mas não é o objeto de replicação.
