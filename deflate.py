"""
deflate.py — série real: deflator implícito CNT + crescimento a/a.

Lê:
  output/tabela2_desvios.csv         — estimado_bilhoes (série nominal Denton)
  data/processed/cnt_benchmark.csv   — volume_idx_1995 (índice de volume CNT)

Escreve:
  output/serie_real.csv   — schema: periodo, ano, trimestre,
                             estimado_bilhoes, deflator_implicito,
                             real_idx_1995, variacao_aa_pct

O deflator implícito é calculado diretamente da CNT:
  deflator = consumo_governo_bilhoes / volume_idx_1995

A série real do indicador é então:
  real_idx = estimado_bilhoes / deflator

Variação a/a = (real_idx_t / real_idx_t-4 − 1) × 100

Uso:
  python deflate.py
"""
import sys

import numpy as np
import pandas as pd

from config import DATA_PROC, OUTPUT, YEAR_END, YEAR_START


def build_serie_real() -> pd.DataFrame:
    tab2_path = OUTPUT / "tabela2_desvios.csv"
    if not tab2_path.exists():
        sys.exit(
            "ERROR: output/tabela2_desvios.csv não encontrado. "
            "Execute python replicate.py primeiro."
        )
    tab2 = pd.read_csv(tab2_path)

    cnt_path = DATA_PROC / "cnt_benchmark.csv"
    if not cnt_path.exists():
        sys.exit(
            "ERROR: data/processed/cnt_benchmark.csv não encontrado. "
            "Execute python build_indicators.py primeiro."
        )
    cnt = pd.read_csv(cnt_path)
    cnt = cnt[cnt["ano"].between(YEAR_START, YEAR_END)].copy()

    df = (
        tab2[["periodo", "ano", "trimestre", "estimado_bilhoes"]]
        .merge(
            cnt[["ano", "trimestre", "consumo_governo_bilhoes", "volume_idx_1995"]],
            on=["ano", "trimestre"],
            how="inner",
        )
        .sort_values(["ano", "trimestre"])
        .reset_index(drop=True)
    )

    if df.empty:
        sys.exit("ERROR: merge nominal × CNT produziu DataFrame vazio")

    # Implicit price deflator from CNT: current values / volume index
    vol = df["volume_idx_1995"].replace(0, np.nan)
    df["deflator_implicito"] = df["consumo_governo_bilhoes"] / vol

    # Deflate the estimated series
    defl = df["deflator_implicito"].replace(0, np.nan)
    df["real_idx_1995"] = df["estimado_bilhoes"] / defl

    # Year-over-year growth rate
    df["variacao_aa_pct"] = (df["real_idx_1995"] / df["real_idx_1995"].shift(4) - 1) * 100

    return df[[
        "periodo", "ano", "trimestre",
        "estimado_bilhoes",
        "deflator_implicito",
        "real_idx_1995",
        "variacao_aa_pct",
    ]]


def main() -> None:
    print("=== deflate.py ===")
    df = build_serie_real()
    out = OUTPUT / "serie_real.csv"
    df.to_csv(out, index=False)
    print(f"  serie_real.csv: {len(df)} trimestres -> {out}")

    recent = df.dropna(subset=["variacao_aa_pct"]).tail(8)
    if not recent.empty:
        print("\n  Últimos trimestres (variação a/a %):")
        print(
            recent[["periodo", "real_idx_1995", "variacao_aa_pct"]]
            .round(2)
            .to_string(index=False)
        )
    print("=== concluído ===")


if __name__ == "__main__":
    main()
