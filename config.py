"""
Configurações centrais do projeto — consumo nominal do governo, método Santos et al. (2015).

Edite aqui para adicionar/remover candidatos, entidades ou horizonte temporal.
"""
from pathlib import Path

# ── Diretórios ────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
DATA_RAW  = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
OUTPUT    = ROOT / "output"

for _d in [DATA_RAW, DATA_PROC, OUTPUT]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Horizonte temporal ────────────────────────────────────────────────────────
# SICONFI RREO disponível desde 2015; CNT usada como benchmark anual.
# Este projeto replica a metodologia sobre dados 2015–2025, não os números
# da Tabela 2 do artigo original (que cobria 2010–2014 com outra base).
YEAR_START = 2015
YEAR_END   = 2025

# ── Controle de esferas ───────────────────────────────────────────────────────
# Municípios (capitais) representam ~27% da cobertura fiscal subnacional.
# Mantenha False em primeiras execuções; True ativa os candidatos "munic_*".
INCLUDE_MUNICIPIOS = False

# ── Estados da federação ──────────────────────────────────────────────────────
TODOS_ESTADOS = {
    "AC": "12", "AL": "27", "AM": "13", "AP": "16", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MG": "31", "MS": "50", "MT": "51", "PA": "15", "PB": "25",
    "PE": "26", "PI": "22", "PR": "41", "RJ": "33", "RN": "24",
    "RO": "11", "RR": "14", "RS": "43", "SC": "42", "SE": "28",
    "SP": "35", "TO": "17",
}

# None = todos os 27 estados; ex.: ["SP", "RJ", "MG"] para subconjunto rápido.
ESTADOS_SUBSET = None

# ── Municípios (capitais) ─────────────────────────────────────────────────────
# Códigos IBGE das 26 capitais estaduais + Brasília (DF).
CAPITAIS = {
    "Rio Branco":      "1200401",
    "Maceió":          "2704302",
    "Manaus":          "1302603",
    "Macapá":          "1600303",
    "Salvador":        "2927408",
    "Fortaleza":       "2304400",
    "Brasília":        "5300108",
    "Vitória":         "3205309",
    "Goiânia":         "5208707",
    "São Luís":        "2111300",
    "Belo Horizonte":  "3106200",
    "Campo Grande":    "5002704",
    "Cuiabá":          "5103403",
    "Belém":           "1501402",
    "João Pessoa":     "2507507",
    "Recife":          "2611606",
    "Teresina":        "2211001",
    "Curitiba":        "4106902",
    "Rio de Janeiro":  "3304557",
    "Natal":           "2408102",
    "Porto Velho":     "1100205",
    "Boa Vista":       "1400100",
    "Porto Alegre":    "4314902",
    "Florianópolis":   "4205407",
    "Aracaju":         "2800308",
    "São Paulo":       "3550308",
    "Palmas":          "1721000",
}

# ── Códigos de natureza de despesa (elemento) ─────────────────────────────────
# Usados no filtro "element" para salários + contribuições efetivas.
# Fonte: Santos et al. (2015), Anexo I — portaria SOF/MF natureza 3190xx/3191xx.
CODES_SALARIOS_CE = [
    "319011",  # Vencimentos e vantagens fixas — pessoal civil
    "319012",  # Vencimentos e vantagens fixas — pessoal militar
    "319013",  # Obrigações patronais (contribuições efetivas)
    "319113",  # Obrigações patronais — intra-orçamentárias
]

# Usados no filtro "element" para consumo intermediário.
# O artigo mapeava via tradutor IBGE(2008b) + pesos Finbra/EOE — não replicável.
# Estes códigos são a aproximação mais próxima disponível só com SICONFI.
# (a) consumo_intermediario_elem  usa estes códigos — tende a subestimar CI.
# (b) consumo_intermediario_gnd3  usa total GND3   — tende a superestimar CI.
# A Série 13 vencedora do artigo exclui CI; estes candidatos existem para
# completar o espaço de busca, não porque se espere que ganhem.
CODES_CONSUMO_INT = [
    "339030",  # Material de consumo
    "339036",  # Outros serviços de terceiros — pessoa física
    "339039",  # Outros serviços de terceiros — pessoa jurídica
]

# ── Grade declarativa de candidatos (Anexo I do artigo) ──────────────────────
#
# Cada dicionário define uma série candidata independente.
#
# sphere    : "uniao" | "estados" | "municipios"
#
# stage     : "liquidado"       — Despesas Liquidadas no bimestre
#             "restos_a_pagar"  — Restos a Pagar Pagos (simplificado, só SICONFI;
#                                 o artigo usava pesos Finbra/EOE que não replicamos)
#             "liq_efetiva"     — liquidado + restos_a_pagar
#
# component : "salarios_ce_element"        — filtra pelos CODES_SALARIOS_CE acima
#             "salarios_ce_gnd1"           — total GND1 "PESSOAL E ENCARGOS SOCIAIS"
#             "contrib_imputadas"          — contrib. previdenciárias imputadas (Anexo 4)
#             "consumo_intermediario_gnd3" — total GND3 (teto: inclui itens não-CI)
#             "consumo_intermediario_elem" — filtra pelos CODES_CONSUMO_INT acima
#                                           (piso: pode excluir itens que o tradutor
#                                            IBGE(2008b) incluiria via Finbra/EOE)
#
# Para salários e consumo intermediário, as duas variantes de isolamento são
# candidatos separados; o ranking por MSE revela qual se aproxima mais da CNT.
#
# Para adicionar um candidato: insira um dicionário. Para remover: comente a linha.
# Candidatos "municipios" só são processados quando INCLUDE_MUNICIPIOS = True.
#
CANDIDATE_SPECS = [
    # ── União ─────────────────────────────────────────────────────────────────
    {
        "name": "uniao_liq_sal_elem",
        "sphere": "uniao", "stage": "liquidado",
        "component": "salarios_ce_element",
    },
    {
        "name": "uniao_liq_sal_gnd1",
        "sphere": "uniao", "stage": "liquidado",
        "component": "salarios_ce_gnd1",
    },
    {
        "name": "uniao_liq_contrib",
        "sphere": "uniao", "stage": "liquidado",
        "component": "contrib_imputadas",
    },
    {
        "name": "uniao_liq_cons_int_gnd3",
        "sphere": "uniao", "stage": "liquidado",
        "component": "consumo_intermediario_gnd3",
    },
    {
        "name": "uniao_liq_cons_int_elem",
        "sphere": "uniao", "stage": "liquidado",
        "component": "consumo_intermediario_elem",
    },
    {
        "name": "uniao_lef_sal_elem",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "salarios_ce_element",
    },
    {
        "name": "uniao_lef_sal_gnd1",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "salarios_ce_gnd1",
    },
    {
        "name": "uniao_lef_cons_int_gnd3",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "consumo_intermediario_gnd3",
    },
    {
        "name": "uniao_lef_cons_int_elem",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "consumo_intermediario_elem",
    },
    # ── Estados ───────────────────────────────────────────────────────────────
    {
        "name": "estados_liq_sal_elem",
        "sphere": "estados", "stage": "liquidado",
        "component": "salarios_ce_element",
    },
    {
        "name": "estados_liq_sal_gnd1",
        "sphere": "estados", "stage": "liquidado",
        "component": "salarios_ce_gnd1",
    },
    {
        "name": "estados_liq_contrib",
        "sphere": "estados", "stage": "liquidado",
        "component": "contrib_imputadas",
    },
    {
        "name": "estados_liq_cons_int_gnd3",
        "sphere": "estados", "stage": "liquidado",
        "component": "consumo_intermediario_gnd3",
    },
    {
        "name": "estados_liq_cons_int_elem",
        "sphere": "estados", "stage": "liquidado",
        "component": "consumo_intermediario_elem",
    },
    {
        "name": "estados_lef_sal_elem",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "salarios_ce_element",
    },
    {
        "name": "estados_lef_sal_gnd1",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "salarios_ce_gnd1",
    },
    {
        "name": "estados_lef_cons_int_gnd3",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "consumo_intermediario_gnd3",
    },
    {
        "name": "estados_lef_cons_int_elem",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "consumo_intermediario_elem",
    },
    # ── Municípios (capitais) — só com INCLUDE_MUNICIPIOS = True ──────────────
    {
        "name": "munic_liq_sal_elem",
        "sphere": "municipios", "stage": "liquidado",
        "component": "salarios_ce_element",
    },
    {
        "name": "munic_liq_sal_gnd1",
        "sphere": "municipios", "stage": "liquidado",
        "component": "salarios_ce_gnd1",
    },
    {
        "name": "munic_liq_cons_int_gnd3",
        "sphere": "municipios", "stage": "liquidado",
        "component": "consumo_intermediario_gnd3",
    },
    {
        "name": "munic_liq_cons_int_elem",
        "sphere": "municipios", "stage": "liquidado",
        "component": "consumo_intermediario_elem",
    },
]


def active_specs():
    """Retorna candidatos ativos conforme INCLUDE_MUNICIPIOS."""
    return [
        s for s in CANDIDATE_SPECS
        if s["sphere"] != "municipios" or INCLUDE_MUNICIPIOS
    ]


# ── Grade de séries compostas (input real do Denton) ─────────────────────────
#
# Cada série composta é a SOMA de um conjunto de blocos atômicos de CANDIDATE_SPECS,
# agregados trimestralmente antes de entrar em denton_proportional().
#
# Séries 01–13: reconstrução do Anexo I do artigo. Os exemplos do usuário fixam
# serie_01, serie_03 e serie_13; as demais seguem a progressão metodológica
# implícita (esfera mínima → expansão de esfera → expansão de componente →
# liq_efetiva → cobertura total). Corrijam conforme o Anexo I original.
#
# Séries ext_*: extensões não presentes no artigo — testam os variantes GND1/GND3
# que o artigo não precisava distinguir (usava Finbra/EOE para CI e elemento-level
# direto para salários). O ranking de MSE revelará se fazem diferença.
#
# Composites que referenciam blocos "municipios" ficam inativos quando
# INCLUDE_MUNICIPIOS = False (active_composites() filtra automaticamente).
#
# Para adicionar uma série: insira um dicionário. Para remover: comente a linha.
#
COMPOSITES = [
    # ── Anexo I — séries 01 a 13 (reconstrução; serie_01/03/13 fixadas pelo artigo) ──

    # Série 01 — União: sal_ce + contrib_imp, liquidado
    {"name": "serie_01",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib"]},

    # Série 02 — União: sal_ce + contrib_imp + CI_elem, liquidado
    {"name": "serie_02",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "uniao_liq_cons_int_elem"]},

    # Série 03 — União+Estados: sal_ce+contrib (U) + sal_ce (E), liquidado
    {"name": "serie_03",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem"]},

    # Série 04 — União+Estados: sal_ce+contrib ambos, liquidado
    {"name": "serie_04",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem", "estados_liq_contrib"]},

    # Série 05 — União+Estados: sal_ce+contrib (U+E) + CI_elem (U), liquidado
    {"name": "serie_05",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem",
                "uniao_liq_cons_int_elem"]},

    # Série 06 — União+Estados: todos os componentes, liquidado
    {"name": "serie_06",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem", "estados_liq_contrib",
                "uniao_liq_cons_int_elem", "estados_liq_cons_int_elem"]},

    # Série 07 — União: sal_ce + contrib, liq_efetiva (sal), liquidado (contrib)
    {"name": "serie_07",
     "blocks": ["uniao_lef_sal_elem", "uniao_liq_contrib"]},

    # Série 08 — União+Estados: sal_ce lef + contrib liq (U); sal_ce lef (E)
    {"name": "serie_08",
     "blocks": ["uniao_lef_sal_elem", "uniao_liq_contrib",
                "estados_lef_sal_elem"]},

    # Série 09 — União+Estados: sal_ce lef + contrib liq, ambas esferas
    {"name": "serie_09",
     "blocks": ["uniao_lef_sal_elem", "uniao_liq_contrib",
                "estados_lef_sal_elem", "estados_liq_contrib"]},

    # Série 10 — Estados: sal_ce apenas, liquidado
    {"name": "serie_10",
     "blocks": ["estados_liq_sal_elem"]},

    # Série 11 — Estados: sal_ce + contrib, liquidado
    {"name": "serie_11",
     "blocks": ["estados_liq_sal_elem", "estados_liq_contrib"]},

    # Série 12 — União+Estados+Municípios: sal_ce+contrib (U+E) + sal_ce (M)
    {"name": "serie_12",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem", "estados_liq_contrib",
                "munic_liq_sal_elem"]},

    # Série 13 — União+Estados+Municípios: sal_ce+contrib (U) + sal_ce (E+M)  ← VENCEDORA
    {"name": "serie_13",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem",
                "munic_liq_sal_elem"]},

    # ── Extensões: variantes GND1 para salários ───────────────────────────────
    # Espelham as séries 01, 03, 10, 11, 13 com GND1 em vez de element-level.

    {"name": "ext_01_gnd1",
     "blocks": ["uniao_liq_sal_gnd1", "uniao_liq_contrib"]},

    {"name": "ext_03_gnd1",
     "blocks": ["uniao_liq_sal_gnd1", "uniao_liq_contrib",
                "estados_liq_sal_gnd1"]},

    {"name": "ext_10_gnd1",
     "blocks": ["estados_liq_sal_gnd1"]},

    {"name": "ext_11_gnd1",
     "blocks": ["estados_liq_sal_gnd1", "estados_liq_contrib"]},

    {"name": "ext_13_gnd1",
     "blocks": ["uniao_liq_sal_gnd1", "uniao_liq_contrib",
                "estados_liq_sal_gnd1",
                "munic_liq_sal_gnd1"]},

    # ── Extensões: variantes com CI via GND3 (teto) ───────────────────────────

    {"name": "ext_02_ci_gnd3",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "uniao_liq_cons_int_gnd3"]},

    {"name": "ext_06_ci_gnd3",
     "blocks": ["uniao_liq_sal_elem", "uniao_liq_contrib",
                "estados_liq_sal_elem", "estados_liq_contrib",
                "uniao_liq_cons_int_gnd3", "estados_liq_cons_int_gnd3"]},

    # ── Extensões: liq_efetiva com GND1 ──────────────────────────────────────

    {"name": "ext_07_gnd1_lef",
     "blocks": ["uniao_lef_sal_gnd1", "uniao_liq_contrib"]},

    {"name": "ext_08_gnd1_lef",
     "blocks": ["uniao_lef_sal_gnd1", "uniao_liq_contrib",
                "estados_lef_sal_gnd1"]},

    # liq_efetiva variant of serie_13
    {"name": "ext_13_lef",
     "blocks": ["uniao_lef_sal_elem", "uniao_liq_contrib",
                "estados_lef_sal_elem",
                "munic_liq_sal_elem"]},
]


def active_composites():
    """
    Retorna composites cujos blocos estão todos disponíveis.
    Composites com blocos "municipios" ficam inativos quando INCLUDE_MUNICIPIOS=False.
    """
    available = {s["name"] for s in active_specs()}
    return [
        c for c in COMPOSITES
        if all(b in available for b in c["blocks"])
    ]
