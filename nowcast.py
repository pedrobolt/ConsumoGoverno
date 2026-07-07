"""
nowcast.py — Chow-Lin AR(1) extrapolation for quarters with no published CNT.

Winner spec from pseudo-OOS horse race (mean MAPE 2.34%, 3 test years):
  Chow-Lin AR(1) with MLE rho, training excludes 2020 (COVID outlier),
  ex-post seasonal bias correction from Denton in-sample desvios.

Regimes per quarter:
  - Year has complete annual CNT → Denton (replicate.py, untouched)
  - Quarter has published quarterly CNT but year incomplete → official value
    used; Chow-Lin prediction logged in vintage_nowcast.csv for tracking
  - Quarter has no CNT at all → Chow-Lin extrapolation (actual nowcast)

Reads:
  data/processed/estados_lef_sal_sem_intra.csv  — quarterly indicator (winner)
  data/processed/cnt_benchmark.csv              — quarterly CNT
  data/raw/rreo_estados.csv                     — bimestral raw data (partial check)
  output/tabela2_desvios.csv                    — Denton desvios (seasonal correction)

Writes:
  output/nowcast.csv           — current estimates, overwritten each run
  output/vintage_nowcast.csv   — append-only run log; never overwrite past rows

Usage:
  python nowcast.py

To nowcast a new year: re-run download.py and build_indicators.py, then run
this script. YEAR_END in config.py is derived from the current calendar year
automatically.
"""
import sys
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from build_indicators import BIM_WEIGHTS, COMPONENT_FILTER, _bim_to_quarterly, _filter_sum
from config import DATA_PROC, DATA_RAW, OUTPUT

_EXCL_YEAR  = 2020          # excluded from training (COVID structural break)
_INDICATOR  = "estados_lef_sal_sem_intra"
_SANITY_PCT = 15.0          # warn if estimate differs > ±15% from same-Q last year

# Quarter → contributing bimesters (from BIM_WEIGHTS)
_Q_BIMS = {1: [1, 2], 2: [2, 3], 3: [4, 5], 4: [5, 6]}


# ── Chow-Lin AR(1) MLE ────────────────────────────────────────────────────────

def _build_C(n):
    C = np.zeros((n, n * 4))
    for i in range(n):
        C[i, i * 4:(i + 1) * 4] = 1.0
    return C


def _ar1_omega(n, rho):
    i = np.arange(n)
    return rho ** np.abs(i[:, None] - i[None, :]) / (1 - rho ** 2)


def _cl_gls(x, y_ann, omega):
    """Chow-Lin GLS disaggregation. Returns (y_hat, beta)."""
    n = len(y_ann)
    X, C = x[:, None], _build_C(n)
    M_inv = np.linalg.inv(C @ omega @ C.T + np.eye(n) * 1e-10)
    CX = C @ X
    beta = np.linalg.solve(CX.T @ M_inv @ CX, CX.T @ M_inv @ y_ann[:, None]).ravel()
    u = y_ann - CX @ beta
    return (X @ beta).ravel() + omega @ C.T @ M_inv @ u, beta


def _mle_rho(x, y_ann):
    """Profile log-likelihood MLE for AR(1) rho."""
    n = len(y_ann)
    C, X = _build_C(n), x[:, None]
    CX = C @ X

    def neg_ll(rho):
        M = C @ _ar1_omega(len(x), rho) @ C.T + np.eye(n) * 1e-10
        try:
            M_inv = np.linalg.inv(M)
            sign, ldet = np.linalg.slogdet(M)
            if sign <= 0:
                return 1e10
        except Exception:
            return 1e10
        beta = np.linalg.solve(CX.T @ M_inv @ CX, CX.T @ M_inv @ y_ann)
        u = y_ann - (CX @ beta).ravel()
        s2 = float(u @ M_inv @ u) / n
        return 1e10 if s2 <= 0 else 0.5 * ldet + 0.5 * n * np.log(s2)

    return float(minimize_scalar(neg_ll, bounds=(0.05, 0.995), method="bounded").x)


# ── Seasonal bias (ex-post correction) ───────────────────────────────────────

def _seasonal_bias(tab2, year_limit):
    """Mean Denton desvio_pct by quarter, using only rows with ano <= year_limit."""
    t = tab2[tab2["ano"] <= year_limit].copy()
    t["pct"] = t["desvio_pct"].str.rstrip("%").str.replace(",", ".").astype(float)
    return t.groupby("trimestre")["pct"].mean().to_dict()


# ── Bimestral flows + partial-quarter scaling ─────────────────────────────────

def _load_bim_flows(raw_estados):
    """liq_efetiva bimestral flows (liquidado + RP) for the indicator accounts."""
    spec = COMPONENT_FILTER["salarios_ce_sem_intra"]
    liq = _filter_sum(raw_estados, spec["liquidado"])
    rp  = _filter_sum(raw_estados, spec["rp"])
    m = (liq.merge(rp, on=["ano", "bimestre"], how="outer", suffixes=("_liq", "_rp"))
           .fillna(0.0))
    m["valor"] = m["valor_liq"] + m["valor_rp"]
    return m[["ano", "bimestre", "valor"]].sort_values(["ano", "bimestre"]).reset_index(drop=True)


def _partial_scale_factors(bim_flows, training_years):
    """
    For each (quarter, partial_bims_tuple): mean(full_quarter / partial_value)
    over training years. Used to upscale indicator when trailing bimesters are
    not yet published.
    """
    bv = {
        y: grp.set_index("bimestre")["valor"].to_dict()
        for y, grp in bim_flows[bim_flows["ano"].isin(training_years)].groupby("ano")
    }
    bw_q = {q: {b: BIM_WEIGHTS[b].get(q, 0) for b in bims} for q, bims in _Q_BIMS.items()}

    factors = {}
    for q, bims in _Q_BIMS.items():
        bw = bw_q[q]
        for n in range(1, len(bims)):
            avail = bims[:n]
            ratios = [
                sum(bw[b] * bv[y].get(b, 0.0) for b in bims) /
                sum(bw[b] * bv[y].get(b, 0.0) for b in avail)
                for y in training_years
                if sum(bw[b] * bv.get(y, {}).get(b, 0.0) for b in avail) > 1e-9
            ]
            if ratios:
                factors[(q, tuple(avail))] = float(np.mean(ratios))
    return factors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== nowcast.py ===")
    today = date.today().isoformat()

    required = [
        (DATA_PROC / f"{_INDICATOR}.csv", "build_indicators.py"),
        (DATA_PROC / "cnt_benchmark.csv", "build_indicators.py"),
        (OUTPUT    / "tabela2_desvios.csv", "replicate.py"),
        (DATA_RAW  / "rreo_estados.csv", "download.py"),
    ]
    for path, script in required:
        if not path.exists():
            sys.exit(f"ERROR: {path.name} não encontrado. Execute {script} primeiro.")

    ind  = pd.read_csv(DATA_PROC / f"{_INDICATOR}.csv").sort_values(["ano", "trimestre"])
    cnt  = pd.read_csv(DATA_PROC / "cnt_benchmark.csv").sort_values(["ano", "trimestre"])
    tab2 = pd.read_csv(OUTPUT / "tabela2_desvios.csv", sep=";", decimal=",")
    raw  = pd.read_csv(DATA_RAW / "rreo_estados.csv", dtype={"cod_ibge": str})

    # ── Year regimes ──────────────────────────────────────────────────────────
    complete_cnt  = set(cnt.groupby("ano").size().pipe(lambda s: s[s == 4]).index)
    last_complete = max(complete_cnt) if complete_cnt else 0
    nowcast_year  = last_complete + 1

    # Detect available bimesters for the nowcast year directly from raw data.
    # This is intentionally independent of YEAR_END / ind_years: as long as
    # download.py has fetched at least one bimestre for nowcast_year, this works.
    # (ind is still used below for training-year quarterly values.)
    bim_flows     = _load_bim_flows(raw)
    ny_avail      = set(bim_flows[bim_flows["ano"] == nowcast_year]["bimestre"].unique())

    if not ny_avail:
        print(f"  Nenhum dado SICONFI para {nowcast_year} em rreo_estados.csv.")
        print(f"  Execute: python download.py (YEAR_END é derivado automaticamente = {nowcast_year})")
        print("=== concluído ===")
        return

    print(f"  Nowcast year: {nowcast_year} | bimestres disponíveis: {sorted(ny_avail)}")

    # Compute quarterly indicator for nowcast_year from raw bimestral data.
    # _bim_to_quarterly applies BIM_WEIGHTS; output has ano, trimestre, valor.
    ny_bim  = bim_flows[bim_flows["ano"] == nowcast_year].copy()
    ny_qtly = _bim_to_quarterly(ny_bim)
    ny_qtly["valor_bilhoes"] = ny_qtly["valor"] / 1e9
    ny_ind  = ny_qtly.set_index("trimestre")["valor_bilhoes"].to_dict()

    # ── Training ──────────────────────────────────────────────────────────────
    # Require all 4 indicator quarters — guards against years where CNT is complete
    # but SICONFI bimestral is still partially lagged (bim 5/6 published ~Feb+1).
    ind_complete_years = set(
        ind.groupby("ano").size().pipe(lambda s: s[s >= 4]).index
    )
    training_years = sorted((complete_cnt & ind_complete_years) - {_EXCL_YEAR})
    annual_cnt = (
        cnt[cnt["ano"].isin(training_years)]
        .groupby("ano")["consumo_governo_bilhoes"].sum()
    )
    x_train = (
        ind[ind["ano"].isin(training_years)]
        .sort_values(["ano", "trimestre"])["valor_bilhoes"]
        .values.astype(float)
    )
    y_annual = annual_cnt.values.astype(float)

    rho = _mle_rho(x_train, y_annual)
    y_hat_train, beta = _cl_gls(x_train, y_annual, _ar1_omega(len(x_train), rho))
    u_last = float((y_hat_train - x_train * beta[0])[-1])
    print(f"  Chow-Lin: rho={rho:.4f}, beta={beta[0]:.4f}, "
          f"n_train={len(training_years)} anos (excl. {_EXCL_YEAR})")

    bias = _seasonal_bias(tab2, max(training_years))

    # ── Partial-quarter scaling ───────────────────────────────────────────────
    # bim_flows already loaded; compute scale factors from training years only.
    scale_factors = _partial_scale_factors(bim_flows, training_years)

    # Sanity reference: same-quarter CNT in last complete training year
    ref = cnt[cnt["ano"] == max(training_years)].set_index("trimestre")["consumo_governo_bilhoes"]
    cnt_qtly = cnt.set_index(["ano", "trimestre"])["consumo_governo_bilhoes"].to_dict()

    # ── Forecast loop ─────────────────────────────────────────────────────────
    nowcast_out, vintage_out = [], []
    h = 0  # quarters elapsed since end of training (drives AR(1) decay rho^h)

    y = nowcast_year
    for q in range(1, 5):
        h += 1
        periodo = f"{y}Q{q}"

        contributing = _Q_BIMS[q]
        present = sorted(b for b in contributing if b in ny_avail)

        if not present:
            continue  # no bimestral data for this quarter; h still advances correctly

        x_q     = float(ny_ind.get(q, 0.0))
        partial = len(present) < len(contributing)

        if partial:
            sf  = scale_factors.get((q, tuple(present)), 1.0)
            x_q *= sf
            print(f"  PARTIAL {periodo}: bims={present}, scale={sf:.3f}")

        # AR(1) extrapolation + seasonal bias correction
        y_raw = x_q * beta[0] + rho ** h * u_last
        y_est = y_raw / (1.0 + bias.get(q, 0.0) / 100.0)

        bims_str = ",".join(str(b) for b in present)

        vintage_out.append({
            "run_date":            today,
            "target_quarter":      periodo,
            "estimate":            round(y_est, 3),
            "bimestres_available": bims_str,
        })

        # Quarter has published CNT (year incomplete) → log only, don't nowcast
        if (y, q) in cnt_qtly:
            cnt_val = cnt_qtly[(y, q)]
            err = (y_est - cnt_val) / cnt_val * 100
            print(f"  {periodo}: CNT={cnt_val:.2f} bi | CL teria: {y_est:.2f} bi "
                  f"(erro={err:+.1f}%)")
            continue

        # Sanity check vs same quarter in last complete year
        ref_val = float(ref.get(q, np.nan))
        if not np.isnan(ref_val):
            dev = (y_est - ref_val) / ref_val * 100
            if abs(dev) > _SANITY_PCT:
                print(f"  WARNING {periodo}: estimate={y_est:.2f} bi, "
                      f"ref_Q{q}_{max(training_years)}={ref_val:.2f} bi, "
                      f"dev={dev:+.1f}% [salvo, mas fora de ±{_SANITY_PCT}%]")

        nowcast_out.append({
            "periodo":           periodo,
            "ano":               y,
            "trimestre":         q,
            "estimate_R_bi":     round(y_est, 3),
            "method":            "CL_ex2020_sbias",
            "indicador_parcial": partial,
            "bimestres_used":    bims_str,
            "data_estimativa":   today,
        })
        print(f"  {periodo}: {y_est:.2f} R$ bi{' [PARCIAL]' if partial else ''}")

    # ── Write outputs ─────────────────────────────────────────────────────────
    if nowcast_out:
        pd.DataFrame(nowcast_out).to_csv(OUTPUT / "nowcast.csv", sep=";", index=False)
        print(f"\n  nowcast.csv: {len(nowcast_out)} trimestres")
    else:
        print("  nowcast.csv: sem trimestres para nowcastar nesta execução.")

    if vintage_out:
        vf   = OUTPUT / "vintage_nowcast.csv"
        df_v = pd.DataFrame(vintage_out)
        if vf.exists():
            df_v.to_csv(vf, mode="a", header=False, sep=";", index=False)
        else:
            df_v.to_csv(vf, sep=";", index=False)
        print(f"  vintage_nowcast.csv: +{len(vintage_out)} linhas")

    print("=== concluído ===")


if __name__ == "__main__":
    main()
