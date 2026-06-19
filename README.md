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

## O que este projeto NÃO é

Este projeto testa a **metodologia** de Santos et al. (2015) sobre dados 2015–2025.
**Não reproduz numericamente** o Anexo I do artigo nem a Tabela 2: os dados são
diferentes (SICONFI vs Finbra/EOE, 2015–2025 vs 2010–2014). Qualquer
correspondência numérica com os resultados originais é coincidência, não validação.

## Desvios e limitações em relação ao artigo original

| Aspecto | Artigo (2015) | Este projeto |
|---------|--------------|--------------|
| Cobertura temporal | 2010–2014 | 2015–2025 |
| Base fiscal subnacional | Finbra + EOE (pesos para RP) | SICONFI RREO (simplificado) |
| Restos a Pagar | Pesos Finbra/EOE por esfera | RP Processados Pagos (SICONFI direto) |
| Granularidade de despesas | Elemento (319011 etc., via SIAFI) | GND apenas (ver nota abaixo) |
| Consumo intermediário | Pesos Finbra + tradutor IBGE(2008b) | GND3 total (teto) |
| Municípios | Capitais com ponderação | Capitais sem ponderação (OFF por padrão) |

**Granularidade SICONFI — limitação fundamental:** O SICONFI RREO Anexo 1
retorna somente o nível GND (Grupo de Natureza de Despesa). Os códigos de
elemento de natureza de despesa (319011, 319012, 319013, 319113, 339030, …)
que o artigo usou existem apenas no SIAFI e em planos de trabalho estaduais,
acessados pelos autores via SIGA Brasil. O SICONFI bulk API não expõe esse
nível — verificado empiricamente: zero linhas com códigos de elemento em 3 710
linhas de SP (Anexo 1, bim. 1/2023) e 4 308 linhas da União. A comparação
elemento-vs-GND proposta no artigo **não é replicável a partir desta fonte**.
O proxy de salários é o total GND1 ("PESSOAL E ENCARGOS SOCIAIS").

**Consumo Intermediário:** O artigo extraía CI do GND3 usando pesos Finbra/EOE
e o tradutor IBGE(2008b). Este projeto usa o total GND3 ("OUTRAS DESPESAS
CORRENTES"), que é um teto: inclui transferências, juros e outros itens que não
são CI. O artigo encontrou a série vencedora excluindo CI inteiramente;
o GND3 existe como diagnóstico, não como candidato esperado.

**Restos a Pagar:** Usa `RESTOS A PAGAR PROCESSADOS PAGOS` do Anexo 1 (coluna
`RREO6PessoalEEncargosSociais`), sem os pesos Finbra/EOE que o artigo aplicava
para distribuir RP entre esferas. Impacto visível no ranking de MSE.

**Municípios (capitais):** desativados por padrão (`INCLUDE_MUNICIPIOS = False`).
Testados empiricamente sobre 2015-2025: os 27 municípios-capital adicionam
**+5,1 pp de representatividade** (de 29,3% para 34,4% da CNT, estável em todos
os anos), o que é economicamente relevante — SP sozinho soma ~R$ 33 bi/ano em
pessoal. Porém, o critério de seleção do artigo é o **MSE vs CNT**, e incluir
as capitais *piora* o ajuste: `estados_munic` (RMSE = 13,9) fica atrás de
`estados_only` (RMSE = 13,6) e ambos atrás do vencedor `estados_only_lef`
(RMSE = 12,0). O motivo provável é a temporização diferente dos Restos a
Pagar municipais. **Lacuna conhecida:** as capitais foram testadas apenas
contra `liquidado`; a interação com `liq_efetiva` não foi testada. Para
ativá-las: `INCLUDE_MUNICIPIOS = True` em `config.py`.

## Intra-orçamentárias: com ou sem?

`PessoalEEncargosSociaisIntra` representa as contribuições patronais pagas
pelo ente ao próprio RPPS, registradas como despesa intra-orçamentária
(~12% do GND1 para estados em 2023). O artigo (Tabela 1) lista CE e CI como
componentes separados (R$63 bi vs R$50 bi em 2010), o que sugere que incluir
a intra não é automaticamente dupla contagem com o Anexo 4.

Porém, se a intra-orçamentária e a contribuição imputada (Anexo 4) medem o
mesmo fluxo de obrigação previdenciária, o composite `com_intra` sistematicamente
sobrestimará o consumo. Este projeto constrói os dois indicadores e deixa o
ranking de MSE decidir: `estados_only` usa sem intra; `estados_only_com_intra`
usa com intra. A série com menor MSE é a versão mais próxima da CNT.

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
| `output/ranking.csv` | Composites ordenados por MSE vs CNT |
| `output/diagnostico_blocos.csv` | Blocos atômicos individuais — diagnóstico, não replicação |
| `output/tabela2_desvios.csv` | Melhor série vs CNT, desvios trimestrais (Tabela 2) |
| `output/tabela3_repres.csv` | Representatividade dos componentes vs TRU anual (Tabela 3) |
| `output/serie_real.csv` | Série deflacionada + crescimento real a/a |
| `output/fig_serie.png` | Melhor série vs CNT — linha (Gráfico 1) |

## Fontes de dados

- **CNT (benchmark):** IBGE, Tab_Compl_CNT.zip — coluna "Consumo do Governo",
  valores correntes e índice de volume (base 2010=100).
- **SICONFI RREO:** Tesouro Nacional, apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo
  — Anexo 1 (Pessoal/GND, `no_co_tipo_demonstrativo="RREO - Anexo 1"`) e
  Anexo 4 (RPPS/contrib. imputadas, `no_co_tipo_demonstrativo="RREO - Anexo 4"`).
- **TRU (denominador Tabela 3):** IBGE, SCN edicao 2021,
  `TRU_resumo_2000_2021_xls.zip` — coluna "Administracao publica" (detectada
  dinamicamente via linha de contribuicoes imputadas dos empregadores).
  Linhas utilizadas: 54 = Remuneracoes dos empregados; 59 = Contribuicoes
  imputadas dos empregadores. Unidade no arquivo: R$ 1 milhao (verificado
  empiricamente; GDP 2021 bate R$9 T); convertido para R$ bilhoes (/ 1000).
  Cobertura: 2000-2021; edicao 2021 e a ultima com decomposicao nao-nula por
  componente de governo. Anos 2022+ sao omitidos da Tabela 3.

## Grade de indicadores

**Blocos atômicos** (`CANDIDATE_SPECS` em `config.py`): 17 séries trimestrais,
uma por combinação de esfera × estágio × componente. Alimentam os composites e
o diagnóstico de blocos individuais.

**Séries compostas** (`COMPOSITES` em `config.py`): 10 séries (7 ativas por
padrão), cada uma somando blocos atômicos antes do Denton.

| Série | Esferas | Componentes | Estágio |
|-------|---------|-------------|---------|
| uniao_only | U | sal+CE(sem intra)+contrib.imp+CI | liquidado |
| estados_only | E | sal+CE sem intra | liquidado |
| estados_only_com_intra | E | sal+CE com intra | liquidado |
| uniao_estados | U+E | sal+CE sem intra | liquidado |
| uniao_estados_ci | U+E | sal+CE sem intra + contrib.imp | liquidado |
| estados_only_lef | E | sal+CE sem intra | liq_efetiva |
| uniao_estados_lef | U+E | sal+CE sem intra | liq_efetiva |
| estados_munic* | E+M | sal+CE sem intra | liquidado |
| uniao_estados_munic* | U+E+M | sal+CE sem intra | liquidado |
| uniao_estados_munic_ci* | U+E+M | sal+CE sem intra + contrib.imp | liquidado |

\* Ativadas com `INCLUDE_MUNICIPIOS = True`.

**Assimetria entre esferas:** `uniao_only` inclui contribuições imputadas
(RPPS federal, extraídas do Anexo 4), porque a União reporta esses dados
diretamente nesse anexo e são parte das remunerações na CNT. Os composites
de Estados usam o Anexo 4 estadual somente em `uniao_estados_ci`, onde o
efeito pode ser testado diretamente contra a versão sem contrib.imputadas.

**Resultado empírico (2015-2025, 44 trimestres, INCLUDE_MUNICIPIOS=False):**

| Rank | Série | RMSE | MAPE | Corr |
|------|-------|------|------|------|
| 1 | `estados_only_lef` | 12,0 | 2,40% | 0,994 |
| 2 | `estados_only` | 13,6 | 2,67% | 0,992 |
| 3 | `estados_only_com_intra` | 13,9 | 2,57% | 0,992 |
| 4 | `uniao_estados_lef` | 14,0 | 2,69% | 0,992 |
| 5 | `uniao_estados_ci` | 15,5 | 2,70% | 0,990 |
| 6 | `uniao_estados` | 15,9 | 2,75% | 0,989 |
| 7 | `uniao_only` | 65,3 | 9,13% | 0,835 |

A série selecionada (`estados_only_lef`) usa GND1 sem intra-orçamentárias,
estágio `liq_efetiva` (liquidado + RP Processados Pagos), esfera estados.
`tabela2_desvios.csv` e `fig_serie.png` correspondem a esta série.

O ranking por MSE vs CNT revela qual combinação melhor aproxima o consumo
do governo trimestral. O diagnóstico de blocos individuais
(`output/diagnostico_blocos.csv`) é útil, mas não é o objeto de replicação.

**Resultado empírico — Tabela 3 (representatividade vs TRU, INCLUDE_MUNICIPIOS=False):**

A Tabela 3 divide cada componente da amostra SICONFI pelo total do mesmo componente
na TRU "governo geral" (coluna Administração Pública). O numerador usa
`estados_lef_sal_sem_intra` para remunerações (GND1 sem intra, liq_efetiva).

| Ano  | Componente            | TRU (R$ bi) | Amostra (R$ bi) | Repr. (%) |
|------|-----------------------|-------------|-----------------|-----------|
| 2015 | remuneracoes_sal_ce   | 797,9       | 583,7           | 73,2%     |
| 2016 | remuneracoes_sal_ce   | 847,0       | 619,6           | 73,2%     |
| 2017 | remuneracoes_sal_ce   | 897,7       | 681,3           | 75,9%     |
| 2018 | remuneracoes_sal_ce   | 938,5       | 819,0           | 87,3%     |
| 2019 | remuneracoes_sal_ce   | 990,2       | 953,3           | 96,3%     |
| 2020 | remuneracoes_sal_ce   | 1.028,9     | 960,9           | 93,4%     |
| 2021 | remuneracoes_sal_ce   | 1.076,9     | 988,4           | 91,8%     |
| 2021 | contrib_imputadas     | 100,6       | 33,5            | 33,3%     |

Desvios em relação ao artigo original na Tabela 3:

| Aspecto | Artigo (2015) | Este projeto |
|---------|--------------|--------------|
| Remunerações | Separado: sal. + contrib. efetivas | GND1 sem intra (SICONFI não separa) |
| Contrib. imputadas | Cobertura plena U+E | Só estados, só 2021 (União não reporta no SICONFI; estados só a partir de 2021) |
| Cobertura TRU | 2010-2014 | 2015-2021 (TRU SCN-2021) |

**Lacuna RP Processados Pagos (2015-2017):** A representatividade de
2015-2017 (~73-76%) subestima a cobertura real em ~20 pp porque o SICONFI
nao reportava Restos a Pagar Processados Pagos para estados antes de 2018.
A partir de 2018, com RP disponivel, a cobertura sobe para ~87-96%,
consistente com a participacao dos 27 estados nas remuneracoes nacionais.
O Denton nao e afetado por essa lacuna (MAPE sem quebra estrutural
pre/pos-2018) porque usa apenas o perfil sazonal, nao o nivel.
As linhas de 2015-2017 em `tabela3_repres.csv` trazem a nota
"RP indisponivel no SICONFI" na coluna `nota`.

**Lacuna contrib_imputadas:** SICONFI Anexo 4 nao retorna dados de
`ReceitaDeContribuicoesPatronalFinanceiro` para a Uniao nem para estados
antes de 2021. A cobertura de 33,3% em 2021 reflete apenas os estados
(sem Uniao), que e a maior componente das contribuicoes imputadas.

