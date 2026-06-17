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

O ranking por MSE vs CNT revela qual combinação melhor aproxima o consumo
do governo trimestral. O diagnóstico de blocos individuais
(`output/diagnostico_blocos.csv`) é útil, mas não é o objeto de replicação.

