"""
build_indicators.py — constrói séries trimestrais por bloco atômico.

Lê:
  data/raw/rreo_uniao.csv, rreo_estados.csv [, rreo_municipios.csv]
  data/raw/cnt_trimestral.csv

Escreve em data/processed/:
  {spec_name}.csv     — schema: ano,trimestre,valor_bilhoes
  cnt_benchmark.csv   — schema: ano,trimestre,consumo_governo_bilhoes,volume_idx_1995

Uso:
  python build_indicators.py
"""
import sys

import numpy as np
import pandas as pd

from config import (
    DATA_PROC,
    DATA_RAW,
    INCLUDE_MUNICIPIOS,
    YEAR_END,
    YEAR_START,
    active_specs,
)

# ── Bim → quarter mapping ─────────────────────────────────────────────────────
# Q1 = bim1 + 0.5*bim2
# Q2 = 0.5*bim2 + bim3
# Q3 = bim4 + 0.5*bim5
# Q4 = 0.5*bim5 + bim6
BIM_WEIGHTS: dict[int, dict[int, float]] = {
    1: {1: 1.0},
    2: {1: 0.5, 2: 0.5},
    3: {2: 1.0},
    4: {3: 1.0},
    5: {3: 0.5, 4: 0.5},
    6: {4: 1.0},
}

# ── Verified SICONFI coluna labels ────────────────────────────────────────────
_LIQ       = "DESPESAS LIQUIDADAS NO BIMESTRE"
_RP        = "RESTOS A PAGAR PROCESSADOS PAGOS (b)"
_PAT       = "RECEITAS REALIZADAS ATÉ O BIMESTRE (b)"    # cumulative YTD (estados patronal)
_ACUM_DESP = "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (acum)" # cumulative YTD (União RPPS Resultado)

# ── Filters: (cod_conta, coluna) pairs per component × flow-type ──────────────
COMPONENT_FILTER: dict[str, dict] = {
    "salarios_ce_sem_intra": {
        "liquidado": [("PessoalEEncargosSociais", _LIQ)],
        "rp":        [("RREO6PessoalEEncargosSociais", _RP)],
    },
    "salarios_ce_com_intra": {
        "liquidado": [
            ("PessoalEEncargosSociais",      _LIQ),
            ("PessoalEEncargosSociaisIntra", _LIQ),
        ],
        "rp": [("RREO6PessoalEEncargosSociais", _RP)],
    },
    "consumo_int_gnd3": {
        "liquidado": [("OutrasDespesasCorrentes", _LIQ)],
        "rp":        [("RREO6OutrasDespesasCorrentes", _RP)],
    },
    "contrib_imputadas": {
        # Estados: patronal receipts as proxy (cumulative YTD).
        "patronal_ytd": [
            ("ReceitaDeContribuicoesPatronalFinanceiro",    _PAT),
            ("ReceitaDeContribuicoesPatronalPrevidenciario", _PAT),
        ],
        # União: Resultado rows from rreo_rpps_uniao.csv (cumulative YTD).
        # Resultado = receitas − despesas; typically negative (deficit).
        # contrib_imputada = −Resultado → negate before _ytd_to_flow().
        "resultado_ytd": [
            ("RREO4ResultadoRPPSPrevidenciario", _ACUM_DESP),  # 04.2 civis
            ("ResultadoRPPSPrevidenciarioFCDF",  _ACUM_DESP),  # 04.2 FCDF
            ("RREO4ResultadoRPPSFinanceiro",     _ACUM_DESP),  # 04.3 pensões militares
            ("ResultadoInativosMilitares",        _ACUM_DESP),  # 04.3 inativos militares
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Raw data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_raw(sphere: str) -> pd.DataFrame:
    path = DATA_RAW / f"rreo_{sphere}.csv"
    if not path.exists():
        sys.exit(
            f"ERROR: {path} não encontrado. Execute python download.py primeiro."
        )
    return pd.read_csv(path, dtype={"cod_ibge": str})


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _filter_sum(
    df: pd.DataFrame,
    pairs: list[tuple[str, str]],
) -> pd.DataFrame:
    """
    Keep rows matching any (cod_conta, coluna) pair; sum valor by (ano, bimestre).
    Returns DataFrame: ano, bimestre, valor.
    """
    if df.empty:
        return pd.DataFrame(columns=["ano", "bimestre", "valor"])

    masks = [(df["cod_conta"] == cod) & (df["coluna"] == col) for cod, col in pairs]
    mask = masks[0]
    for m in masks[1:]:
        mask = mask | m

    return (
        df[mask]
        .groupby(["ano", "bimestre"], as_index=False)["valor"]
        .sum()
        .sort_values(["ano", "bimestre"])
        .reset_index(drop=True)
    )


def _ytd_to_flow(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert cumulative year-to-date bimestral values to bimestral flows.
    Within each year: flow[bim1] = ytd[bim1]; flow[bimN] = ytd[bimN] - ytd[bimN-1].
    Negative flows (data revisions) are floored at zero.
    """
    rows = []
    for ano, grp in df.groupby("ano", sort=True):
        ytd = (
            grp.set_index("bimestre")["valor"]
            .reindex(range(1, 7), fill_value=0.0)
        )
        flows = np.concatenate([[ytd.iloc[0]], np.diff(ytd.values)])
        for bim, v in zip(range(1, 7), flows):
            rows.append({"ano": int(ano), "bimestre": bim, "valor": max(float(v), 0.0)})
    return pd.DataFrame(rows, columns=["ano", "bimestre", "valor"])


def _bim_to_quarterly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert bimestral flows to quarterly values.
    Returns DataFrame: ano, trimestre, valor.
    """
    if df.empty:
        return pd.DataFrame(columns=["ano", "trimestre", "valor"])

    pivot = (
        df.pivot_table(index="ano", columns="bimestre", values="valor", aggfunc="sum")
        .reindex(columns=range(1, 7), fill_value=0.0)
    )

    q_series: dict[int, pd.Series] = {}
    for bim, weights in BIM_WEIGHTS.items():
        for q, w in weights.items():
            if q not in q_series:
                q_series[q] = pd.Series(0.0, index=pivot.index)
            q_series[q] = q_series[q] + w * pivot[bim]

    rows = []
    for q in sorted(q_series):
        for ano, val in q_series[q].items():
            rows.append({"ano": int(ano), "trimestre": q, "valor": float(val)})
    return (
        pd.DataFrame(rows, columns=["ano", "trimestre", "valor"])
        .sort_values(["ano", "trimestre"])
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-spec builder
# ─────────────────────────────────────────────────────────────────────────────

def _extract_bimestral(
    df_raw: pd.DataFrame,
    component: str,
    stage: str,
    sphere: str = "",
) -> pd.DataFrame:
    """
    Extract a bimestral flow series for one (component, stage, sphere).
    Returns DataFrame: ano, bimestre, valor (sum across all entities in df_raw).
    """
    spec_map = COMPONENT_FILTER[component]

    if component == "contrib_imputadas":
        if sphere == "uniao":
            # df_raw is rreo_rpps_uniao.csv — sum Resultado rows, negate (deficit→positive)
            ytd = _filter_sum(df_raw, spec_map["resultado_ytd"])
            if not ytd.empty:
                ytd = ytd.copy()
                ytd["valor"] = -ytd["valor"]
            return _ytd_to_flow(ytd)
        # estados/municipios: use patronal receipts as proxy
        ytd = _filter_sum(df_raw, spec_map["patronal_ytd"])
        return _ytd_to_flow(ytd)

    liq = _filter_sum(df_raw, spec_map["liquidado"])

    if stage == "liquidado":
        return liq

    # liq_efetiva = liquidado + RP processados pagos
    rp = _filter_sum(df_raw, spec_map["rp"])
    merged = liq.merge(
        rp, on=["ano", "bimestre"], how="outer", suffixes=("_liq", "_rp")
    ).fillna(0.0)
    merged["valor"] = merged["valor_liq"] + merged["valor_rp"]
    return (
        merged[["ano", "bimestre", "valor"]]
        .sort_values(["ano", "bimestre"])
        .reset_index(drop=True)
    )


def build_block(spec: dict, df_raw: pd.DataFrame, sphere: str = "") -> pd.DataFrame:
    """
    Build the quarterly indicator series for one atomic block spec.

    Returns DataFrame: ano, trimestre, valor_bilhoes (R$ bilhões).
    Values are converted from R$ (raw SICONFI) to R$ bilhões to match CNT units.
    """
    bim = _extract_bimestral(df_raw, spec["component"], spec["stage"], sphere=sphere)
    bim = bim[bim["ano"].between(YEAR_START, YEAR_END)]
    qtly = _bim_to_quarterly(bim)
    qtly["valor_bilhoes"] = qtly["valor"] / 1e9
    return qtly[["ano", "trimestre", "valor_bilhoes"]].copy()


# ─────────────────────────────────────────────────────────────────────────────
# CNT benchmark pass-through
# ─────────────────────────────────────────────────────────────────────────────

def build_cnt_benchmark() -> None:
    """Trim the raw CNT series to [YEAR_START, YEAR_END] and copy to processed/."""
    src = DATA_RAW / "cnt_trimestral.csv"
    if not src.exists():
        sys.exit(
            "ERROR: data/raw/cnt_trimestral.csv não encontrado. "
            "Execute python download.py primeiro."
        )
    df = pd.read_csv(src)
    df = df[df["ano"].between(YEAR_START, YEAR_END)].copy()
    out = DATA_PROC / "cnt_benchmark.csv"
    df.to_csv(out, index=False)
    print(f"  cnt_benchmark: {len(df)} trimestres -> {out.name}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== build_indicators.py ===")

    raw: dict[str, pd.DataFrame] = {
        "uniao":      _load_raw("uniao"),
        "estados":    _load_raw("estados"),
        "municipios": _load_raw("municipios") if INCLUDE_MUNICIPIOS else pd.DataFrame(),
    }

    # Load União RPPS Resultado data (Anexo 04.2 + 04.3); optional — if absent,
    # uniao contrib_imputadas falls back to empty (zero) as before.
    rpps_uniao_path = DATA_RAW / "rreo_rpps_uniao.csv"
    if rpps_uniao_path.exists():
        raw["uniao_rpps"] = pd.read_csv(rpps_uniao_path, dtype={"cod_ibge": str})
        print(f"  rreo_rpps_uniao.csv: {len(raw['uniao_rpps'])} linhas carregadas")
    else:
        raw["uniao_rpps"] = pd.DataFrame()
        print("  WARN: rreo_rpps_uniao.csv nao encontrado — "
              "execute python download.py para baixar RPPS União")

    specs = active_specs()
    print(f"  {len(specs)} blocos atômicos ativos")

    for spec in specs:
        sphere = spec["sphere"]

        # Route uniao contrib_imputadas to the dedicated RPPS file
        if sphere == "uniao" and spec["component"] == "contrib_imputadas":
            df_raw = raw.get("uniao_rpps", pd.DataFrame())
        else:
            df_raw = raw.get(sphere, pd.DataFrame())

        if df_raw.empty:
            print(f"  SKIP {spec['name']} — sem dados para esfera '{sphere}'")
            continue

        try:
            quarterly = build_block(spec, df_raw, sphere=sphere)
        except Exception as exc:
            print(f"  ERRO {spec['name']}: {exc}", file=sys.stderr)
            continue

        if quarterly.empty or quarterly["valor_bilhoes"].sum() == 0:
            print(f"  WARN {spec['name']}: série vazia — verifique os dados brutos")

        out_path = DATA_PROC / f"{spec['name']}.csv"
        quarterly.to_csv(out_path, index=False)
        total = quarterly["valor_bilhoes"].sum()
        print(f"  {spec['name']}: {len(quarterly)} trimestres, soma={total:,.1f} B R$")

    build_cnt_benchmark()
    print("=== concluído ===")


if __name__ == "__main__":
    main()
