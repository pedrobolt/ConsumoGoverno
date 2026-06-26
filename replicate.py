"""
replicate.py — roda a grade de composites, rankeia por MSE, gera saídas.

Lê:
  data/processed/{spec_name}.csv      — blocos atômicos (ano, trimestre, valor_bilhoes)
  data/processed/cnt_benchmark.csv    — benchmark CNT (ano, trimestre, consumo_governo_bilhoes)

Escreve em output/:
  ranking.csv              — composites rankeados por MSE vs CNT
  diagnostico_blocos.csv   — blocos atômicos individuais (diagnóstico, não replicação)
  tabela2_desvios.csv      — melhor série vs CNT, desvios trimestrais
  tabela3_repres.csv       — representatividade média do indicador vs CNT anual
  fig_serie.png            — melhor série Denton vs CNT (linha)

Uso:
  python replicate.py
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import (
    DATA_PROC,
    DATA_RAW,
    OUTPUT,
    TRU_EDITION,
    YEAR_END,
    YEAR_START,
    active_composites,
    active_specs,
)
from denton import denton_proportional


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_block(name: str) -> pd.DataFrame | None:
    path = DATA_PROC / f"{name}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df = df[df["ano"].between(YEAR_START, YEAR_END)].copy()
    return df.sort_values(["ano", "trimestre"]).reset_index(drop=True)


def _load_cnt() -> pd.DataFrame:
    path = DATA_PROC / "cnt_benchmark.csv"
    if not path.exists():
        sys.exit(
            "ERROR: data/processed/cnt_benchmark.csv não encontrado. "
            "Execute python build_indicators.py primeiro."
        )
    df = pd.read_csv(path)
    df = df[df["ano"].between(YEAR_START, YEAR_END)].copy()
    return df.sort_values(["ano", "trimestre"]).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Annual benchmarks
# ─────────────────────────────────────────────────────────────────────────────

def _annual_benchmarks(cnt: pd.DataFrame) -> dict[int, float]:
    """Sum quarterly CNT values to annual totals for use as Denton benchmarks."""
    return cnt.groupby("ano")["consumo_governo_bilhoes"].sum().to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Composite indicator (sum of atomic blocks)
# ─────────────────────────────────────────────────────────────────────────────

def _build_composite(block_names: list[str]) -> pd.DataFrame | None:
    """
    Sum quarterly valor_bilhoes across all named atomic blocks.
    Returns DataFrame: ano, trimestre, valor_bilhoes — or None if any block missing.
    """
    frames = []
    for name in block_names:
        df = _load_block(name)
        if df is None:
            print(f"    SKIP: bloco '{name}' não encontrado em data/processed/")
            return None
        frames.append(df.set_index(["ano", "trimestre"])["valor_bilhoes"])

    total = frames[0]
    for f in frames[1:]:
        total = total.add(f, fill_value=0.0)
    return total.reset_index()


# ─────────────────────────────────────────────────────────────────────────────
# Denton wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _run_denton(
    indicator: pd.Series,
    benchmarks: dict[int, float],
    years: list[int],
) -> np.ndarray | None:
    """
    Align indicator to `years`, run proportional Denton against annual benchmarks.
    Returns estimated quarterly array (length 4*m) or None if infeasible.
    """
    m = len(years)
    b = np.array([benchmarks.get(y, np.nan) for y in years])
    if np.any(np.isnan(b)):
        return None

    p = indicator.values.astype(float)
    if len(p) != 4 * m:
        return None

    # Floor non-positive values at a small positive epsilon
    if np.any(p <= 0):
        pos = p[p > 0]
        eps = pos.min() * 0.01 if pos.size > 0 else 1e-3
        p = np.where(p > 0, p, eps)

    try:
        return denton_proportional(p, b)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _metrics(est: np.ndarray, act: np.ndarray) -> dict:
    mse  = float(np.mean((est - act) ** 2))
    rmse = float(np.sqrt(mse))
    mask = act != 0
    mape = float(np.mean(np.abs((est[mask] - act[mask]) / act[mask])) * 100) if mask.any() else np.nan
    corr = float(np.corrcoef(est, act)[0, 1]) if est.std() > 0 and act.std() > 0 else np.nan
    return {"mse": mse, "rmse": rmse, "mape": mape, "corr": corr}


# ─────────────────────────────────────────────────────────────────────────────
# Core ranking routine (shared by rank_composites and rank_blocks_diagnostic)
# ─────────────────────────────────────────────────────────────────────────────

def _rank_one(
    name: str,
    indicator_df: pd.DataFrame,
    cnt: pd.DataFrame,
    benchmarks: dict[int, float],
) -> dict | None:
    """
    Align indicator to CNT index, run Denton, compute metrics.
    indicator_df : DataFrame with columns ano, trimestre, valor_bilhoes
    Returns metrics dict or None.
    """
    merged = cnt[["ano", "trimestre", "consumo_governo_bilhoes"]].merge(
        indicator_df, on=["ano", "trimestre"], how="left"
    )
    merged["valor_bilhoes"] = merged["valor_bilhoes"].fillna(0.0)

    years = sorted(merged["ano"].unique())
    # Keep only complete years (4 quarters each)
    complete = [y for y in years if (merged["ano"] == y).sum() == 4]
    if not complete:
        return None
    merged = merged[merged["ano"].isin(complete)].copy()

    indicator = merged["valor_bilhoes"]
    cnt_arr   = merged["consumo_governo_bilhoes"].values
    estimated = _run_denton(indicator, benchmarks, complete)
    if estimated is None:
        return None

    n = min(len(estimated), len(cnt_arr))
    m = _metrics(estimated[:n], cnt_arr[:n])
    m["n_quarters"] = n
    m["name"] = name
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Rank composites (paper-replication ranking)
# ─────────────────────────────────────────────────────────────────────────────

def rank_composites(cnt: pd.DataFrame) -> pd.DataFrame:
    benchmarks = _annual_benchmarks(cnt)
    records = []
    composites = active_composites()
    print(f"  {len(composites)} composites ativos")

    for comp in composites:
        composite_df = _build_composite(comp["blocks"])
        if composite_df is None:
            continue
        m = _rank_one(comp["name"], composite_df, cnt, benchmarks)
        if m is None:
            print(f"    SKIP {comp['name']}: Denton infeasível")
            continue
        records.append(
            {
                "composite":   comp["name"],
                "description": comp.get("description", ""),
                "blocks":      "|".join(comp["blocks"]),
                "mse":         m["mse"],
                "rmse":        m["rmse"],
                "mape":        m["mape"],
                "corr":        m["corr"],
                "n_quarters":  m["n_quarters"],
            }
        )
        print(f"    {comp['name']}: RMSE={m['rmse']:,.1f} MAPE={m['mape']:.2f}%")

    df = pd.DataFrame(records).sort_values("mse").reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Rank individual blocks (diagnostic — NOT the paper ranking)
# ─────────────────────────────────────────────────────────────────────────────

def rank_blocks_diagnostic(cnt: pd.DataFrame) -> pd.DataFrame:
    """
    Rank each atomic block individually through Denton vs CNT.
    Diagnostic only — the paper-replication ranking is in ranking.csv.
    """
    benchmarks = _annual_benchmarks(cnt)
    records = []
    for spec in active_specs():
        df = _load_block(spec["name"])
        if df is None:
            continue
        m = _rank_one(spec["name"], df, cnt, benchmarks)
        if m is None:
            continue
        records.append(
            {
                "bloco":     spec["name"],
                "sphere":    spec["sphere"],
                "stage":     spec["stage"],
                "component": spec["component"],
                "mse":       m["mse"],
                "rmse":      m["rmse"],
                "mape":      m["mape"],
                "corr":      m["corr"],
            }
        )
    return pd.DataFrame(records).sort_values("mse").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tabela 2 — desvios trimestrais da melhor série
# ─────────────────────────────────────────────────────────────────────────────

def build_tabela2(best_comp: dict, cnt: pd.DataFrame) -> pd.DataFrame:
    benchmarks = _annual_benchmarks(cnt)
    composite_df = _build_composite(best_comp["blocks"])
    if composite_df is None:
        return pd.DataFrame()

    merged = cnt[["ano", "trimestre", "consumo_governo_bilhoes"]].merge(
        composite_df, on=["ano", "trimestre"], how="left"
    )
    merged["valor_bilhoes"] = merged["valor_bilhoes"].fillna(0.0)
    years = sorted(merged["ano"].unique())
    complete = [y for y in years if (merged["ano"] == y).sum() == 4]
    merged = merged[merged["ano"].isin(complete)].copy()

    estimated = _run_denton(merged["valor_bilhoes"], benchmarks, complete)
    if estimated is None:
        return pd.DataFrame()

    n = min(len(estimated), len(merged))
    df = merged.iloc[:n].copy()
    df["estimado_bilhoes"] = estimated[:n]
    df["desvio_bilhoes"] = df["estimado_bilhoes"] - df["consumo_governo_bilhoes"]
    df["desvio_pct"] = (
        df["desvio_bilhoes"]
        / df["consumo_governo_bilhoes"].replace(0, np.nan)
        * 100
    )
    df["periodo"] = df["ano"].astype(str) + "Q" + df["trimestre"].astype(str)
    return df[
        ["periodo", "ano", "trimestre",
         "consumo_governo_bilhoes", "estimado_bilhoes",
         "desvio_bilhoes", "desvio_pct"]
    ].reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tabela 3 — representatividade por componente vs TRU (SCN anual)
# ─────────────────────────────────────────────────────────────────────────────

def _load_tru() -> pd.DataFrame:
    """Load parsed TRU government components from data/raw/tru_governo.csv."""
    path = DATA_RAW / "tru_governo.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _tru_numerators() -> dict[str, pd.Series]:
    """
    Build annual numerator series per TRU component, summing atomic blocks
    across all active spheres.

    remuneracoes_sal_ce : all salarios_ce_sem_intra blocks, preferring liq_efetiva
                          stage when both stages exist for a sphere.
    contrib_imputadas   : all contrib_imputadas blocks (liquidado only).
    """
    specs = active_specs()

    # sal: prefer lef over liq for each sphere
    sal_by_sphere: dict[str, str] = {}
    for s in specs:
        if s["component"] == "salarios_ce_sem_intra":
            sphere = s["sphere"]
            if sphere not in sal_by_sphere or s["stage"] == "liq_efetiva":
                sal_by_sphere[sphere] = s["name"]

    ci_blocks = [s["name"] for s in specs if s["component"] == "contrib_imputadas"]

    result: dict[str, pd.Series] = {}
    for comp_key, block_names in [
        ("remuneracoes_sal_ce", list(sal_by_sphere.values())),
        ("contrib_imputadas",   ci_blocks),
    ]:
        frames = []
        for name in block_names:
            df = _load_block(name)
            if df is not None:
                frames.append(df.set_index(["ano", "trimestre"])["valor_bilhoes"])
        if not frames:
            continue
        total = frames[0]
        for f in frames[1:]:
            total = total.add(f, fill_value=0.0)
        result[comp_key] = (
            total.reset_index()
            .groupby("ano")["valor_bilhoes"]
            .sum()
        )

    return result


def build_tabela3() -> pd.DataFrame:
    """
    Representatividade of each indicator component vs TRU government totals.

    Denominator : TRU SCN-2021 (data/raw/tru_governo.csv), years 2015-TRU_EDITION.
    Numerator   : atomic blocks summed across active spheres, by component type.
    Coverage    : years with published TRU only; 2022+ omitted (no TRU data).

    Returns DataFrame: ano, componente, valor_ibge_tru_bilhoes,
                       valor_amostra_bilhoes, representatividade_pct
    """
    tru = _load_tru()
    if tru.empty:
        print("  WARN: data/raw/tru_governo.csv nao encontrado -- "
              "execute python download.py primeiro", flush=True)
        return pd.DataFrame()

    numerators = _tru_numerators()
    if not numerators:
        return pd.DataFrame()

    rows = []
    for _, tru_row in tru.iterrows():
        ano  = int(tru_row["ano"])
        comp = tru_row["componente"]
        tru_val = float(tru_row["governo_bilhoes"])

        if comp not in numerators:
            continue
        num_series = numerators[comp]
        if ano not in num_series.index:
            continue
        num_val = float(num_series.loc[ano])
        if tru_val <= 0 or num_val <= 0:
            continue

        nota = ""
        if comp == "remuneracoes_sal_ce" and ano <= 2017:
            nota = "RP indisponivel no SICONFI"

        rows.append({
            "ano":                    ano,
            "componente":             comp,
            "valor_ibge_tru_bilhoes": round(tru_val, 3),
            "valor_amostra_bilhoes":  round(num_val, 3),
            "representatividade_pct": round(num_val / tru_val * 100, 2),
            "nota":                   nota,
        })

    return (
        pd.DataFrame(rows)
        .sort_values(["ano", "componente"])
        .reset_index(drop=True)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Figure
# ─────────────────────────────────────────────────────────────────────────────

def plot_best_series(tab2: pd.DataFrame) -> None:
    if tab2.empty:
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    x = range(len(tab2))
    ax.plot(x, tab2["consumo_governo_bilhoes"], label="CNT (IBGE)",
            linewidth=1.8, color="steelblue")
    ax.plot(x, tab2["estimado_bilhoes"], label="Estimado (Denton)",
            linewidth=1.4, linestyle="--", color="darkorange")

    q1_idx = tab2.index[tab2["trimestre"] == 1].tolist()
    ax.set_xticks(q1_idx)
    ax.set_xticklabels(tab2.loc[tab2["trimestre"] == 1, "ano"].astype(str), rotation=45)
    ax.set_ylabel("R$ bilhões")
    ax.set_title("Consumo do Governo Nominal — Estimado vs CNT")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = OUTPUT / "fig_serie.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  fig_serie.png -> {out}")


# ─────────────────────────────────────────────────────────────────────────────
# Brazilian-locale CSV writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_br_csv(df: pd.DataFrame, path, col_formats: dict) -> None:
    """
    Write a CSV with Brazilian locale formatting:
      - field separator ";" (Excel BR auto-detects this)
      - decimal separator "," for numeric columns
      - percentage columns stored as "2,36%" strings

    col_formats: {col_name: dp_int | "pct"}
      dp_int → round to dp decimal places, write with "," as decimal
      "pct"  → round to 2dp, append "%" → "2,36%"
    """
    out = df.copy()
    for col, fmt in col_formats.items():
        if col not in out.columns:
            continue
        if fmt == "pct":
            out[col] = out[col].apply(
                lambda x: f"{x:.2f}%".replace(".", ",") if pd.notna(x) else ""
            )
        else:
            dp = int(fmt)
            out[col] = out[col].apply(
                lambda x, dp=dp: f"{x:.{dp}f}".replace(".", ",") if pd.notna(x) else ""
            )
    out.to_csv(path, sep=";", index=False)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== replicate.py ===")

    cnt = _load_cnt()
    if cnt.empty:
        sys.exit("ERROR: cnt_benchmark.csv vazio")
    print(f"  CNT: {len(cnt)} trimestres ({cnt['ano'].min()}–{cnt['ano'].max()})")

    print("Rankeando composites ...")
    ranking = rank_composites(cnt)
    if ranking.empty:
        print("WARN: nenhum composite processado — verifique data/processed/")
    else:
        out = OUTPUT / "ranking.csv"
        _write_br_csv(ranking, out, {"mse": 1, "rmse": 1, "mape": "pct", "corr": 4})
        print(f"\n  ranking.csv ({len(ranking)} composites):")
        print(ranking[["rank", "composite", "rmse", "mape", "corr"]].to_string(index=False))

    print("\nRankeando blocos atômicos (diagnóstico) ...")
    diag = rank_blocks_diagnostic(cnt)
    if not diag.empty:
        out = OUTPUT / "diagnostico_blocos.csv"
        _write_br_csv(diag, out, {"mse": 1, "rmse": 1, "mape": "pct", "corr": 4})
        print(f"  diagnostico_blocos.csv: {len(diag)} blocos")

    if ranking.empty:
        return

    best_name = ranking.iloc[0]["composite"]
    best_comp = next(c for c in active_composites() if c["name"] == best_name)
    print(f"\nMelhor série: {best_name}")

    tab2 = build_tabela2(best_comp, cnt)
    if not tab2.empty:
        out = OUTPUT / "tabela2_desvios.csv"
        _write_br_csv(tab2, out, {
            "consumo_governo_bilhoes": 2, "estimado_bilhoes": 2,
            "desvio_bilhoes": 2, "desvio_pct": "pct",
        })
        print(f"  tabela2_desvios.csv: {len(tab2)} trimestres")

    tab3 = build_tabela3()
    if not tab3.empty:
        out = OUTPUT / "tabela3_repres.csv"
        _write_br_csv(tab3, out, {
            "valor_ibge_tru_bilhoes": 2, "valor_amostra_bilhoes": 2,
            "representatividade_pct": "pct",
        })
        n_years = tab3["ano"].nunique()
        print(f"  tabela3_repres.csv: {len(tab3)} linhas ({n_years} anos, "
              f"TRU {YEAR_START}-{TRU_EDITION})")
        for _, r in tab3.iterrows():
            print(f"    {r['ano']} {r['componente']}: "
                  f"{r['valor_amostra_bilhoes']:.1f} / {r['valor_ibge_tru_bilhoes']:.1f} "
                  f"= {r['representatividade_pct']:.1f}%")

    plot_best_series(tab2)
    print("=== concluído ===")


if __name__ == "__main__":
    main()
