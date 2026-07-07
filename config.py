"""
Configurações centrais do projeto — consumo nominal do governo, método Santos et al. (2015).

Edite aqui para adicionar/remover candidatos, entidades ou horizonte temporal.
"""
from datetime import date as _date
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
YEAR_START = 2015
YEAR_END   = _date.today().year  # auto-advances each calendar year; no manual edit needed

# União RPPS (Anexo 04.2 civis + 04.3 militares) indisponível em 2015 no
# SICONFI (verificado: API retorna 0 rows para an_exercicio=2015). Dados
# existem a partir de 2016. Para 2015 contrib_imputadas reflete apenas estados.
RPPS_UNIAO_START_YEAR = 2016

# Sub-anexos do RPPS União a baixar. Quando o SICONFI adicionar novos sub-anexos
# (ex.: 04.5), basta incluí-los aqui — nenhuma outra alteração necessária.
RPPS_UNIAO_ANEXOS = ["RREO-Anexo 04.2", "RREO-Anexo 04.3"]

# ── TRU (Tabela de Recursos e Usos) ───────────────────────────────────────────
# SCN 2021 edition = last with non-zero component decomposition for govt.
# When IBGE publishes the ref-2021 TRU, update TRU_EDITION and TRU_ZIP_URL here.
# Unit in raw files: R$ 1 milhao (verified empirically -- divide by 1000 to R$ bi).
TRU_EDITION = 2021
TRU_ZIP_URL = (
    "https://ftp.ibge.gov.br/Contas_Nacionais/Sistema_de_Contas_Nacionais/"
    "2021/tabelas_xls/tabelas_de_recursos_e_usos/"
    "TRU_resumo_2000_2021_xls.zip"
)

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

# ── Nota sobre granularidade dos dados SICONFI ────────────────────────────────
# SICONFI RREO Anexo 1 retorna somente o nível GND (Grupo de Natureza de
# Despesa). Códigos de elemento (319011, 319012, 319013, 319113, 339030, …)
# existem apenas no SIAFI/SIAFEM e em planos de trabalho estaduais — fontes
# que o artigo original acessou via SIGA Brasil, mas que o SICONFI bulk API
# não expõe. Portanto, a comparação elemento-vs-GND que o artigo propõe
# NÃO É REPLICÁVEL a partir desta fonte. O proxy de salários é o total GND1.

# ── Campos SICONFI relevantes (verificados via API em 2024) ──────────────────
# Resposta Anexo 1: conta, cod_conta, coluna, valor (+ exercicio, periodo, …)
# GND1 liquidado : cod_conta == 'PessoalEEncargosSociais'
#                  coluna    == 'DESPESAS LIQUIDADAS NO BIMESTRE'
# GND1 intra liq : cod_conta == 'PessoalEEncargosSociaisIntra'   (mesma coluna)
# GND1 RP pagos  : cod_conta == 'RREO6PessoalEEncargosSociais'
#                  coluna    == 'RESTOS A PAGAR PROCESSADOS PAGOS (b)'
# GND3 liquidado : cod_conta == 'OutrasDespesasCorrentes'
#                  coluna    == 'DESPESAS LIQUIDADAS NO BIMESTRE'
# GND3 RP pagos  : cod_conta == 'RREO6OutrasDespesasCorrentes'
#                  coluna    == 'RESTOS A PAGAR PROCESSADOS PAGOS (b)'
# Pré-2018 União : coluna == 'No Bimestre' (duas linhas por conta);
#                  liquidado = linha onde a PRÓXIMA linha tem coluna ∋ 'Bimestre (h)'

# ── Grade declarativa de blocos atômicos ─────────────────────────────────────
#
# Cada spec define uma série bimestral bruta que build_indicators.py constrói
# a partir do SICONFI. O bloco resultante é somado por composite em
# replicate.py antes de entrar em denton_proportional().
#
# sphere    : "uniao" | "estados" | "municipios"
# stage     : "liquidado"      — DESPESAS LIQUIDADAS NO BIMESTRE
#             "liq_efetiva"    — liquidado + RESTOS A PAGAR PROCESSADOS PAGOS
# component : "salarios_ce_com_intra" — GND1 total (inclui PessoalEEncargosSociaisIntra)
#             "salarios_ce_sem_intra" — GND1 s/ intra (só PessoalEEncargosSociais)
#             "contrib_imputadas"     — RPPS (Anexo 4); só União e Estados
#             "consumo_int_gnd3"      — GND3 total "OUTRAS DESPESAS CORRENTES"
#
# Distinção com/sem intra:
#   PessoalEEncargosSociaisIntra = contribuições patronais pagas ao RPPS próprio,
#   registradas como despesa intra-orçamentária. O artigo (Tabela 1) lista CE e CI
#   como componentes separados (63 bi vs 50 bi em 2010), portanto incluir a intra
#   não é automaticamente dupla contagem — mas pode sobrepor o Anexo 4 se a intra
#   e a contrib.imputada medirem o mesmo fluxo. O ranking de MSE decide.
#
# Composites com "municipios" ficam inativos quando INCLUDE_MUNICIPIOS = False.
# Para adicionar um bloco: insira um dicionário. Para remover: comente a linha.
#
CANDIDATE_SPECS = [
    # ── União, liquidado ──────────────────────────────────────────────────────
    {
        "name": "uniao_liq_sal_com_intra",
        "sphere": "uniao", "stage": "liquidado",
        "component": "salarios_ce_com_intra",
    },
    {
        "name": "uniao_liq_sal_sem_intra",
        "sphere": "uniao", "stage": "liquidado",
        "component": "salarios_ce_sem_intra",
    },
    {
        "name": "uniao_liq_contrib",
        "sphere": "uniao", "stage": "liquidado",
        "component": "contrib_imputadas",
    },
    {
        "name": "uniao_liq_cons_int",
        "sphere": "uniao", "stage": "liquidado",
        "component": "consumo_int_gnd3",
    },
    # ── União, liq_efetiva ────────────────────────────────────────────────────
    {
        "name": "uniao_lef_sal_com_intra",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "salarios_ce_com_intra",
    },
    {
        "name": "uniao_lef_sal_sem_intra",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "salarios_ce_sem_intra",
    },
    {
        "name": "uniao_lef_cons_int",
        "sphere": "uniao", "stage": "liq_efetiva",
        "component": "consumo_int_gnd3",
    },
    # ── Estados, liquidado ────────────────────────────────────────────────────
    {
        "name": "estados_liq_sal_com_intra",
        "sphere": "estados", "stage": "liquidado",
        "component": "salarios_ce_com_intra",
    },
    {
        "name": "estados_liq_sal_sem_intra",
        "sphere": "estados", "stage": "liquidado",
        "component": "salarios_ce_sem_intra",
    },
    {
        "name": "estados_liq_contrib",
        "sphere": "estados", "stage": "liquidado",
        "component": "contrib_imputadas",
    },
    {
        "name": "estados_liq_cons_int",
        "sphere": "estados", "stage": "liquidado",
        "component": "consumo_int_gnd3",
    },
    # ── Estados, liq_efetiva ──────────────────────────────────────────────────
    {
        "name": "estados_lef_sal_com_intra",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "salarios_ce_com_intra",
    },
    {
        "name": "estados_lef_sal_sem_intra",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "salarios_ce_sem_intra",
    },
    {
        "name": "estados_lef_cons_int",
        "sphere": "estados", "stage": "liq_efetiva",
        "component": "consumo_int_gnd3",
    },
    # ── Municípios (capitais) — só com INCLUDE_MUNICIPIOS = True ──────────────
    {
        "name": "munic_liq_sal_com_intra",
        "sphere": "municipios", "stage": "liquidado",
        "component": "salarios_ce_com_intra",
    },
    {
        "name": "munic_liq_sal_sem_intra",
        "sphere": "municipios", "stage": "liquidado",
        "component": "salarios_ce_sem_intra",
    },
    {
        "name": "munic_liq_cons_int",
        "sphere": "municipios", "stage": "liquidado",
        "component": "consumo_int_gnd3",
    },
]


def active_specs():
    """Retorna blocos ativos conforme INCLUDE_MUNICIPIOS."""
    return [
        s for s in CANDIDATE_SPECS
        if s["sphere"] != "municipios" or INCLUDE_MUNICIPIOS
    ]


# ── Séries compostas — input direto do Denton ────────────────────────────────
#
# Cada série composta SOMA blocos atômicos → uma série trimestral → Denton.
# Este conjunto testa a METODOLOGIA de Santos et al. (2015) sobre dados
# SICONFI 2015–2025. NÃO reproduz numericamente o Anexo I do artigo.
#
# Sufixos: _com_intra inclui PessoalEEncargosSociaisIntra (contribuições
#          patronais intra-orçamentárias); _sem_intra exclui.
#          O ranking de MSE revela qual versão rastreia melhor a CNT.
#          Nota: se a intra sobrepõe o que o Anexo 4 já captura como
#          contrib.imputadas, o _com_intra sistematicamente sobrestimará.
#
COMPOSITES = [
    # ── Base: esfera única ou duas esferas ────────────────────────────────────

    # União: sal+CE + contrib.imputadas + CI — cobertura plena União
    {"name": "uniao_only",
     "description": "União: sal+CE(sem_intra)+contrib.imp+CI, liquidado",
     "blocks": ["uniao_liq_sal_sem_intra", "uniao_liq_contrib",
                "uniao_liq_cons_int"]},

    # Estados: sal+CE sem intra — candidato mais simples
    {"name": "estados_only",
     "description": "Estados: sal+CE sem intra, liquidado",
     "blocks": ["estados_liq_sal_sem_intra"]},

    # Estados: sal+CE com intra — comparação direta com estados_only
    {"name": "estados_only_com_intra",
     "description": "Estados: sal+CE com intra, liquidado — compara com estados_only",
     "blocks": ["estados_liq_sal_com_intra"]},

    # União + Estados: sal+CE sem intra
    {"name": "uniao_estados",
     "description": "União+Estados: sal+CE sem intra, liquidado",
     "blocks": ["uniao_liq_sal_sem_intra", "estados_liq_sal_sem_intra"]},

    # União + Estados: sal+CE + contrib.imputadas (remunerações completas)
    {"name": "uniao_estados_ci",
     "description": "União+Estados: sal+CE+contrib.imputadas sem intra, liquidado",
     "blocks": ["uniao_liq_sal_sem_intra", "uniao_liq_contrib",
                "estados_liq_sal_sem_intra", "estados_liq_contrib"]},

    # ── liq_efetiva ───────────────────────────────────────────────────────────

    # Estados: sal+CE sem intra, liq_efetiva
    {"name": "estados_only_lef",
     "description": "Estados: sal+CE sem intra, liq_efetiva (liquidado + RP pagos)",
     "blocks": ["estados_lef_sal_sem_intra"]},

    # União + Estados: sal+CE sem intra, liq_efetiva
    {"name": "uniao_estados_lef",
     "description": "União+Estados: sal+CE sem intra, liq_efetiva",
     "blocks": ["uniao_lef_sal_sem_intra", "estados_lef_sal_sem_intra"]},

    # ── Municípios — ativos apenas com INCLUDE_MUNICIPIOS = True ─────────────

    {"name": "estados_munic",
     "description": "Estados+Municípios(capitais): sal+CE sem intra, liquidado",
     "blocks": ["estados_liq_sal_sem_intra", "munic_liq_sal_sem_intra"]},

    {"name": "uniao_estados_munic",
     "description": "União+Estados+Municípios: sal+CE sem intra, liquidado",
     "blocks": ["uniao_liq_sal_sem_intra", "estados_liq_sal_sem_intra",
                "munic_liq_sal_sem_intra"]},

    {"name": "uniao_estados_munic_ci",
     "description": "União+Estados+Municípios: sal+CE+contrib.imputadas sem intra, liquidado",
     "blocks": ["uniao_liq_sal_sem_intra", "uniao_liq_contrib",
                "estados_liq_sal_sem_intra", "estados_liq_contrib",
                "munic_liq_sal_sem_intra"]},
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
