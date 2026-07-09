# Metodologia Detalhada — Consumo Nominal do Governo

Referência: Santos, C. H. M. dos, et al. (2015). *Uma metodologia de estimação do
consumo do governo em base trimestral*. IPEA Carta de Conjuntura nº 27.

Este documento consolida os detalhes investigativos e justificativos do projeto:
desvios em relação ao paper original, descobertas de schema SICONFI, grade completa
de indicadores, e toda a validação do módulo de nowcast (horse race, backtest,
calibração de multiplicadores).

---

## Desvios em relação ao artigo original

### Tabela comparativa

| Aspecto | Artigo (2015) | Este projeto |
|---------|--------------|--------------|
| Cobertura temporal | 2010–2014 | 2015–presente |
| Base fiscal subnacional | Finbra + EOE (pesos para RP) | SICONFI RREO (simplificado) |
| Restos a Pagar | Pesos Finbra/EOE por esfera | RP Processados Pagos (SICONFI direto) |
| Granularidade de despesas | Elemento (319011 etc., via SIAFI) | GND apenas |
| Consumo intermediário | Pesos Finbra + tradutor IBGE(2008b) | GND3 total (teto) |
| Municípios | Capitais com ponderação | Capitais sem ponderação (OFF por padrão) |

### Granularidade SICONFI — limitação fundamental

O SICONFI RREO Anexo 1 retorna somente o nível GND (Grupo de Natureza de Despesa).
Os códigos de elemento de natureza de despesa (319011, 319012, 319013, 319113,
339030, …) que o artigo usou existem apenas no SIAFI e em planos de trabalho
estaduais, acessados pelos autores via SIGA Brasil. O SICONFI bulk API não expõe
esse nível — verificado empiricamente: zero linhas com códigos de elemento em 3.710
linhas de SP (Anexo 1, bim. 1/2023) e 4.308 linhas da União. A comparação
elemento-vs-GND proposta no artigo **não é replicável a partir desta fonte**. O
proxy de salários é o total GND1 ("PESSOAL E ENCARGOS SOCIAIS").

### Restos a Pagar — ausência de pesos Finbra/EOE

Usa `RESTOS A PAGAR PROCESSADOS PAGOS` do Anexo 1 (coluna
`RREO6PessoalEEncargosSociais`), sem os pesos Finbra/EOE que o artigo aplicava para
distribuir RP entre esferas. Impacto visível no ranking de MSE.

**Lacuna RP Processados Pagos (2015–2017):** A representatividade de 2015–2017
(~73–76%) subestima a cobertura real em ~20 pp porque o SICONFI não reportava Restos
a Pagar Processados Pagos para estados antes de 2018. A partir de 2018, com RP
disponível, a cobertura sobe para ~87–96%, consistente com a participação dos 27
estados nas remunerações nacionais. O Denton não é afetado por essa lacuna (MAPE sem
quebra estrutural pré/pós-2018) porque usa apenas o perfil sazonal, não o nível. As
linhas de 2015–2017 em `tabela3_repres.csv` trazem a nota "RP indisponível no
SICONFI" na coluna `nota`.

### Consumo Intermediário — GND3 como teto

O artigo extraía CI do GND3 usando pesos Finbra/EOE e o tradutor IBGE(2008b). Este
projeto usa o total GND3 ("OUTRAS DESPESAS CORRENTES"), que é um teto: inclui
transferências, juros e outros itens que não são CI. O artigo encontrou a série
vencedora excluindo CI inteiramente; o GND3 existe como diagnóstico, não como
candidato esperado.

### Intra-orçamentárias: com ou sem?

`PessoalEEncargosSociaisIntra` representa as contribuições patronais pagas pelo ente
ao próprio RPPS, registradas como despesa intra-orçamentária (~12% do GND1 para
estados em 2023). O artigo (Tabela 1) lista CE e CI como componentes separados
(R$63 bi vs R$50 bi em 2010), sugerindo que incluir a intra não é automaticamente
dupla contagem com o Anexo 4.

Porém, se a intra-orçamentária e a contribuição imputada (Anexo 4) medem o mesmo
fluxo de obrigação previdenciária, o composite `com_intra` sistematicamente
sobrestimará o consumo. Este projeto constrói os dois indicadores e deixa o ranking
de MSE decidir: `estados_only` usa sem intra; `estados_only_com_intra` usa com intra.

### Municípios (capitais) — análise detalhada

Desativados por padrão (`INCLUDE_MUNICIPIOS = False`). Testados empiricamente sobre
2015–2025: os 27 municípios-capital adicionam **+5,1 pp de representatividade** (de
29,3% para 34,4% da CNT, estável em todos os anos) — SP sozinho soma ~R$33 bi/ano em
pessoal. Porém, o critério de seleção é o **MSE vs CNT**, e incluir as capitais
*piora* o ajuste: `estados_munic` (RMSE = 13,9) fica atrás de `estados_only`
(RMSE = 13,6) e ambos atrás de `estados_only_lef` (RMSE = 12,0). Motivo provável:
temporização diferente dos Restos a Pagar municipais. **Lacuna conhecida:** as
capitais foram testadas apenas contra `liquidado`; a interação com `liq_efetiva` não
foi testada. Para ativá-las: `INCLUDE_MUNICIPIOS = True` em `config.py`.

### TRU 2021 — última edição com decomposição não-nula

SCN 2021 é a última edição com decomposição não-nula por componente de governo.
Unidade no arquivo bruto: R$1 milhão (verificado empiricamente — GDP 2021 bate R$9 T);
convertido para R$bilhões (÷ 1000). Cobertura: 2000–2021; anos 2022+ omitidos da
Tabela 3. Quando o IBGE publicar o SCN de referência 2021 com TRU não-nula, atualizar
`TRU_EDITION` e `TRU_ZIP_URL` em `config.py`.

---

## Fontes de dados

- **CNT (benchmark):** IBGE, Tab_Compl_CNT.zip — coluna "Consumo do Governo",
  valores correntes e índice de volume (base 2010=100).
- **SICONFI RREO:** Tesouro Nacional, apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo
  — Anexo 1 (Pessoal/GND) e Anexo 04.2 + 04.3 (RPPS União: civis e militares).
  Baixado em `data/raw/rreo_rpps_uniao.csv` via `download_siconfi_rpps_uniao()`.
  Estados: contribuição patronal (`ReceitaDeContribuicoesPatronalFinanceiro`, Anexo 4).
- **TRU (denominador Tabela 3):** IBGE, SCN edição 2021, `TRU_resumo_2000_2021_xls.zip`
  — coluna "Administração Pública" (detectada dinamicamente via linha de contribuições
  imputadas dos empregadores). Linhas: 54 = Remunerações dos empregados;
  59 = Contribuições imputadas dos empregadores. Cobertura: 2000–2021.

---

## Descobertas de schema SICONFI

### Sub-anexos RPPS União (04.2 / 04.3)

Anexo 04.2 cobre servidores civis; 04.3 cobre militares. Disponibilidade verificada:

- Militares (04.3): dados disponíveis a partir de 2018
- Civis (04.2): dados disponíveis a partir de 2023
- Novos sub-anexos (ex.: 04.5): basta incluir em `RPPS_UNIAO_ANEXOS` em `config.py`

Cobertura plena (~100% da TRU) exigiria fontes não disponíveis via API pública
(SIAFI, Portal da Transparência — testado e bloqueado por controle de acesso).

### Formato pré-2018 da União (Anexo 1)

Antes de 2018, o SICONFI retorna duas linhas por conta no Anexo 1 da União com
coluna `'No Bimestre'`. O valor liquidado é a linha onde a *próxima* linha tem
coluna contendo `'Bimestre (h)'`. `build_indicators.py` implementa essa detecção
automaticamente.

### Campos SICONFI relevantes (verificados via API em 2024)

Resposta Anexo 1: `conta`, `cod_conta`, `coluna`, `valor` (+ `exercicio`, `periodo`, …)

| `cod_conta` | `coluna` | O que mede |
|-------------|----------|------------|
| `PessoalEEncargosSociais` | `DESPESAS LIQUIDADAS NO BIMESTRE` | GND1 liquidado |
| `PessoalEEncargosSociaisIntra` | (mesma coluna) | GND1 intra liquidado |
| `RREO6PessoalEEncargosSociais` | `RESTOS A PAGAR PROCESSADOS PAGOS (b)` | GND1 RP pagos |
| `OutrasDespesasCorrentes` | `DESPESAS LIQUIDADAS NO BIMESTRE` | GND3 liquidado |
| `RREO6OutrasDespesasCorrentes` | `RESTOS A PAGAR PROCESSADOS PAGOS (b)` | GND3 RP pagos |

Pré-2018 União: coluna == `'No Bimestre'`; liquidado = linha onde a próxima tem `'Bimestre (h)'`.

---

## Grade de indicadores

### Blocos atômicos e composites

**Blocos atômicos** (`CANDIDATE_SPECS` em `config.py`): 17 séries trimestrais, uma
por combinação de esfera × estágio × componente.

**Composites ativos** (INCLUDE_MUNICIPIOS=False):

| Série | Esferas | Componentes | Estágio |
|-------|---------|-------------|---------|
| uniao_only | U | sal+CE(sem intra)+contrib.imp+CI | liquidado |
| estados_only | E | sal+CE sem intra | liquidado |
| estados_only_com_intra | E | sal+CE com intra | liquidado |
| uniao_estados | U+E | sal+CE sem intra | liquidado |
| uniao_estados_ci | U+E | sal+CE sem intra + contrib.imp | liquidado |
| estados_only_lef | E | sal+CE sem intra | liq_efetiva |
| uniao_estados_lef | U+E | sal+CE sem intra | liq_efetiva |

\* Com `INCLUDE_MUNICIPIOS = True`: `estados_munic`, `uniao_estados_munic`, `uniao_estados_munic_ci`.

**Contrib. imputadas — cobertura parcial:** SICONFI Anexo 04.2/04.3 da União só
expõe Resultado RPPS para militares (2018–2020) e civis (2023+). Estados a partir de
2021. Configurável via `RPPS_UNIAO_START_YEAR` e `RPPS_UNIAO_ANEXOS` em `config.py`.

### Ranking empírico (2015–2025, 44 trimestres, INCLUDE_MUNICIPIOS=False)

| Rank | Série | RMSE | MAPE | Corr |
|------|-------|------|------|------|
| 1 | `estados_only_lef` | 12,0 | 2,40% | 0,994 |
| 2 | `estados_only` | 13,6 | 2,67% | 0,992 |
| 3 | `estados_only_com_intra` | 13,9 | 2,57% | 0,992 |
| 4 | `uniao_estados_lef` | 14,0 | 2,69% | 0,992 |
| 5 | `uniao_estados` | 15,9 | 2,75% | 0,989 |
| 6 | `uniao_estados_ci` | 16,9 | 2,96% | 0,988 |
| 7 | `uniao_only` | 65,3 | 9,15% | 0,834 |

### Tabela 3 — representatividade vs TRU (INCLUDE_MUNICIPIOS=False)

Divide cada componente da amostra SICONFI pelo total do mesmo componente na TRU
"governo geral" (coluna Administração Pública). Numerador: `estados_lef_sal_sem_intra`.

| Ano  | Componente            | TRU (R$ bi) | Amostra (R$ bi) | Repr. (%) |
|------|-----------------------|-------------|-----------------|-----------|
| 2015 | remuneracoes_sal_ce   | 797,9       | 583,7           | 73,2%     |
| 2016 | remuneracoes_sal_ce   | 847,0       | 619,6           | 73,2%     |
| 2017 | remuneracoes_sal_ce   | 897,7       | 681,3           | 75,9%     |
| 2018 | remuneracoes_sal_ce   | 938,5       | 819,0           | 87,3%     |
| 2019 | remuneracoes_sal_ce   | 990,2       | 953,3           | 96,3%     |
| 2020 | remuneracoes_sal_ce   | 1.028,9     | 960,9           | 93,4%     |
| 2021 | remuneracoes_sal_ce   | 1.076,9     | 988,4           | 91,8%     |
| 2018 | contrib_imputadas     | 96,8        | 19,1            | 19,7%     |
| 2019 | contrib_imputadas     | 105,1       | 47,0            | 44,7%     |
| 2020 | contrib_imputadas     | 97,8        | 44,9            | 45,9%     |
| 2021 | contrib_imputadas     | 100,6       | 33,5            | 33,3%     |

Desvios em relação ao artigo:

| Aspecto | Artigo (2015) | Este projeto |
|---------|--------------|--------------|
| Remunerações | Separado: sal. + contrib. efetivas | GND1 sem intra (SICONFI não separa) |
| Contrib. imputadas | Cobertura plena U+E | Parcial: militares 2018–2020, civis 2023+ (União); estados 2021+ |
| Cobertura TRU | 2010–2014 | 2015–2021 (TRU SCN-2021) |

---

## Nowcast — validação e calibração

### Horse race — especificação vencedora (regime completo/parcial)

Protocolo rolling-origin: treina até ano T, prevê todos os 4 trimestres de T+1.
Origens: 2022→2023, 2023→2024, 2024→2025.

| Especificação | MAPE 2023 | MAPE 2024 | MAPE 2025 | **Média** |
|---------------|-----------|-----------|-----------|-----------|
| **CL_ex2020_sbias** ✓ | 2,94% | 1,58% | 2,51% | **2,34%** |
| CL_sbias | 3,38% | 1,49% | 2,74% | 2,54% |
| CL_ex2020 | 3,62% | 1,42% | 3,16% | 2,73% |
| CL (base) | 3,97% | 1,41% | 3,39% | 2,93% |
| FZ_ex2020_sbias | 7,76% | 2,91% | 5,91% | 5,52% |
| FZ_sbias | 8,18% | 3,33% | 6,27% | 5,93% |
| FZ_ex2020 | 8,46% | 3,44% | 6,58% | 6,16% |
| FZ (base) | 8,89% | 3,93% | 6,95% | 6,59% |

CL = Chow-Lin AR(1) MLE; FZ = Fernandez (passeio aleatório); sbias = correção sazonal;
ex2020 = exclui 2020 do treinamento.

Fernandez descartado: MAPE 2–3× maior, com erro sistemático de Q4 de −11% a −18%
(passeio aleatório não acomoda o pico de gasto de dezembro do governo).

### Erros por trimestre — especificação vencedora (CL_ex2020_sbias)

O erro varia por trimestre. **Q2 e Q4 têm incerteza ~2–3× maior que Q1.**

| Ano teste | rho | Q1 | Q2 | Q3 | Q4 | MAPE |
|-----------|-----|----|----|----|----|------|
| 2023 | 0,8445 | +0,14% | −4,00% | −2,11% | −5,53% | 2,94% |
| 2024 | 0,8340 | −2,38% | +1,02% | −0,38% | +2,56% | 1,58% |
| 2025 | 0,8372 | +0,61% | −3,36% | −3,67% | −2,39% | 2,51% |
| **Média** | **0,84** | **−0,54%** | **−2,11%** | **−2,05%** | **−1,79%** | **2,34%** |
| **\|Média\|** | | **1,04%** | **2,79%** | **2,05%** | **3,49%** | |

### Regime projetado — horse race de 4 métodos (A/B/C/D)

Protocolo: stand em junho de cada ano de teste, prevê Q3 e Q4 usando apenas bim1+2.
Janela: 6 anos (2019, 2021–2025); 2020 excluído por COVID; 2016–2018 excluídos por
amostra de treino < 4 anos.

| Método | MAPE Q3 | MAPE Q4 | Combinado | Sinal dos erros |
|--------|---------|---------|-----------|-----------------|
| A — participação sazonal (baseline) | 5,1% | 5,5% | 5,3% | mistos |
| **B — A × multiplicador LOO** ✓ | **2,9%** | **5,0%** | **4,0%** | mistos |
| C — SARIMA(1,1,1)(0,1,1,4) | 4,9% | 5,6% | 5,2% | mistos |
| D — ARIMA não-sazonal ✗ | 5,2% | 8,9% | 7,1% | mistos |

**Por que D foi eliminado:** ARIMA(1,1,2) sem componente sazonal extrapola a tendência
recente e falha no pico de gastos de dezembro (Q4 MAPE = 8,9%, quase 2× pior que B).
O SARIMA com `(P,D,Q,4)` captura o padrão anual; o ARIMA simples não consegue.
Confirmação adicional: D projeta Q3→Q4 jump de +12,3% para 2026, z ≈ −2,5 relativo
à distribuição histórica de 11 anos (ver seção seguinte).

### Calibração de _PROJ_BIAS — razões por ano e trimestre

Razão actual/estimativa-A por ano (base dos multiplicadores LOO):

| Ano | Q3 ratio | Q4 ratio | Nota |
|-----|----------|----------|------|
| 2019 | 0,977 | 0,922 | n_treino=4 — outlier de amostra pequena |
| 2021 | 1,056 | 1,042 | |
| 2022 | 1,084 | 1,072 | |
| 2023 | 1,063 | 1,102 | |
| 2024 | 1,042 | 1,014 | |
| 2025 | 1,057 | 1,034 | |
| **Média (n=6, excl. 2020)** | **1,046** | **1,031** | |
| **Média excl. 2019 (n=5)** | **1,061** | **1,053** | **valores adotados** |

2019 excluído: Q4 ratio = 0,92 (z = −1,94); n_treino=4 é insuficiente para estimativa
estável. Com 2019 incluído, média Q4 cai para 1,031 (−2,1 pp). Valores adotados em
`_PROJ_BIAS = {3: 1.061, 4: 1.053}`. Revisar anualmente com os erros ex-post de
`vintage_nowcast.csv`.

### Padrão Q3 → Q4 — série histórica completa (2015–2025)

O pico de gastos de Q4 é uma estrutura estável do consumo do governo. Nenhum outlier
em |z| > 2,0 nos 11 anos disponíveis (2020 inclusive — COVID não perturbou o padrão).

| Ano | Q3 (R$ bi) | Q4 (R$ bi) | Jump % | z (excl. 2020) |
|-----|-----------|-----------|--------|-----------------|
| 2015 | 287,92 | 341,36 | +18,6% | −0,35 |
| 2016 | 303,26 | 377,53 | +24,5% | +1,73 |
| 2017 | 314,36 | 377,02 | +19,9% | +0,13 |
| 2018 | 338,34 | 397,40 | +17,5% | −0,74 |
| 2019 | 357,18 | 419,12 | +17,3% | −0,78 |
| 2020 | 366,84 | 438,60 | +19,6% | ±0,00 (COVID — jump normal) |
| 2021 | 408,39 | 491,76 | +20,4% | +0,30 |
| 2022 | 462,23 | 550,52 | +19,1% | −0,16 |
| 2023 | 506,85 | 630,48 | +24,4% | +1,70 |
| 2024 | 546,46 | 637,98 | +16,7% | −0,98 |
| 2025 | 607,07 | 710,81 | +17,1% | −0,86 |
| **Média excl. 2020** | | | **19,6%** | — |
| **Std excl. 2020** | | | **2,85 pp** | — |

Method B projeta +18,3% para 2026 (z = −0,4 — normal). Method D projeta +12,3%
(z ≈ −2,5 — fora do intervalo histórico; confirma inadequação do ARIMA não-sazonal).

### Atenção: erros pseudo-OOS vs erros em tempo real

Todos os erros acima foram medidos em retrospecto com dados revisados. Erros reais
podem diferir por revisões do SICONFI e sazonalidades atípicas. `vintage_nowcast.csv`
é o registro autoritativo da acurácia real.

---

## Tentativa de retropolação pré-2015

*Seção a preencher.* A API SICONFI não disponibiliza dados RREO anteriores a 2015.
Tentativas de backfill com dados estaduais (MG/RS como piloto) via fontes alternativas
(FINBRA, portais estaduais) esbarraram em heterogeneidade de formato e ausência de
dados sistematizados equivalentes ao Anexo 1. Registrar aqui os resultados de futuras
tentativas.
