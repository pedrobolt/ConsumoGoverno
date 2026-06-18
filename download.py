"""
download.py — baixa dados brutos necessários para a replicação.

Saídas em data/raw/:
  rreo_uniao.csv       schema: ano,bimestre,cod_ibge,uf,coluna,cod_conta,conta,valor
  rreo_estados.csv     idem
  rreo_municipios.csv  idem (só quando INCLUDE_MUNICIPIOS=True)
  cnt_trimestral.csv   schema: ano,trimestre,consumo_governo_bilhoes,volume_idx_1995

Uso:
  python download.py                 # baixa tudo (pula o que já foi baixado)
  python download.py --force         # re-baixa tudo do zero
"""
import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from config import (
    CAPITAIS,
    DATA_RAW,
    INCLUDE_MUNICIPIOS,
    ESTADOS_SUBSET,
    TODOS_ESTADOS,
    YEAR_END,
    YEAR_START,
)

# ── SICONFI ───────────────────────────────────────────────────────────────────
SICONFI_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"

# Verified cod_conta values (live API probes, 2024/2025)
KEEP_CONTAS = {
    "PessoalEEncargosSociais",           # GND1 sem intra
    "PessoalEEncargosSociaisIntra",      # GND1 intra
    "OutrasDespesasCorrentes",           # GND3
    "RREO6PessoalEEncargosSociais",      # RP GND1
    "RREO6OutrasDespesasCorrentes",      # RP GND3
    "ReceitaDeContribuicoesPatronalFinanceiro",  # RPPS patronal (cumulative YTD)
}
# Verified coluna values (post-normalisation)
KEEP_COLUNAS = {
    "DESPESAS LIQUIDADAS NO BIMESTRE",
    "RESTOS A PAGAR PROCESSADOS PAGOS (b)",
    "RECEITAS REALIZADAS ATÉ O BIMESTRE (b)",
}

# ── CNT ───────────────────────────────────────────────────────────────────────
CNT_ZIP_URL = (
    "https://ftp.ibge.gov.br/Contas_Nacionais/"
    "Contas_Nacionais_Trimestrais/Tabelas_Completas/Tab_Compl_CNT.zip"
)
# Sheet names verified by inspection of Tab_Compl_CNT_1T26.xls
CNT_SHEET_CORRENTES = "Valores Correntes"
CNT_SHEET_VOLUME    = "Série Encadeada"
# Column index of "Consumo do Governo" (0-based, verified at row 2 col 19)
CNT_COL_GOVERNO = 19
CNT_COL_PERIODO = 0

# delay between API calls (keeps us below Tesouro rate limits)
CALL_DELAY = 0.35


# ─────────────────────────────────────────────────────────────────────────────
# Standalone reusable function — fetch one bimestre for one entity
# ─────────────────────────────────────────────────────────────────────────────

def fetch_rreo_bimestre(
    id_ente: str,
    year: int,
    bimestre: int,
    timeout: int = 30,
) -> list[dict]:
    """
    Fetch RREO rows for a single entity × year × bimestre from SICONFI.

    Reusable independently of the full-pull loop — no side-effects, no file I/O.
    Returns filtered + normalised rows ready for appending to the raw CSV.

    Pre-2018 União dual-row format ('No Bimestre') is resolved internally:
    liquidado = the row whose next row's coluna contains 'Bimestre (h)'.

    Parameters
    ----------
    id_ente   : IBGE entity code as string ('1' for União, '35' for SP, etc.)
    year      : calendar year
    bimestre  : 1–6

    Returns
    -------
    list of dicts with keys: ano, bimestre, cod_ibge, uf, coluna, cod_conta,
                              conta, valor
    """
    params = {
        "an_exercicio": year,
        "nr_periodo": bimestre,
        "co_tipo_demonstrativo": "RREO",
        "id_ente": id_ente,
    }
    url = SICONFI_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})

    items: list[dict] = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                items = json.loads(r.read()).get("items", [])
            break
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"SICONFI fetch failed: id_ente={id_ente} {year}B{bimestre}"
                ) from exc
            time.sleep(2 ** attempt)

    # Pre-2018 União has two 'No Bimestre' rows per account; normalise first
    if str(id_ente) == "1" and year < 2018:
        items = _normalise_uniao_pre2018(items)

    rows = []
    for item in items:
        if (
            item.get("cod_conta") in KEEP_CONTAS
            and item.get("coluna") in KEEP_COLUNAS
        ):
            rows.append(
                {
                    "ano": year,
                    "bimestre": bimestre,
                    "cod_ibge": str(item.get("cod_ibge", id_ente)),
                    "uf": item.get("uf", ""),
                    "coluna": item["coluna"],
                    "cod_conta": item["cod_conta"],
                    "conta": item.get("conta", ""),
                    "valor": float(item.get("valor") or 0),
                }
            )
    return rows


def _normalise_uniao_pre2018(items: list[dict]) -> list[dict]:
    """
    Pre-2018 União RREO: each account has two consecutive 'No Bimestre' rows.
    Liquidado is the row whose immediately following row's coluna contains
    'Bimestre (h)' (verified against 2016 União API probe).
    """
    out: list[dict] = []
    n = len(items)
    for i, item in enumerate(items):
        if item.get("coluna") != "No Bimestre":
            out.append(item)
            continue
        next_col = items[i + 1]["coluna"] if i + 1 < n else ""
        if "Bimestre (h)" in next_col:
            item = dict(item)
            item["coluna"] = "DESPESAS LIQUIDADAS NO BIMESTRE"
            out.append(item)
        # else: non-liquidado 'No Bimestre' row — drop
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Full-pull helpers
# ─────────────────────────────────────────────────────────────────────────────

def _already_downloaded(path: Path) -> set[tuple]:
    """Return set of (cod_ibge, ano, bimestre) already in the CSV."""
    if not path.exists() or path.stat().st_size == 0:
        return set()
    df = pd.read_csv(
        path,
        usecols=["ano", "bimestre", "cod_ibge"],
        dtype={"cod_ibge": str},
    )
    return set(zip(df["cod_ibge"], df["ano"], df["bimestre"]))


def _append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    write_header = not path.exists() or path.stat().st_size == 0
    df.to_csv(path, mode="a", header=write_header, index=False)


def _pull_sphere(
    label: str,
    entities: dict[str, str],
    out_path: Path,
    force: bool = False,
) -> None:
    """
    Loop fetch_rreo_bimestre over all entities × years × bimestres.
    Appends new rows immediately; existing rows are skipped (resumable).
    """
    if force and out_path.exists():
        out_path.unlink()

    done = _already_downloaded(out_path)
    years = list(range(YEAR_START, YEAR_END + 1))
    bimestres = list(range(1, 7))
    todo = sum(
        1
        for id_ente in entities.values()
        for y in years
        for b in bimestres
        if (str(id_ente), y, b) not in done
    )
    print(f"  {label}: {todo} chamadas pendentes ({len(done)} ja salvas)", flush=True)

    n = 0
    for uf_label, id_ente in entities.items():
        for year in years:
            for bimestre in bimestres:
                key = (str(id_ente), year, bimestre)
                if key in done:
                    continue
                try:
                    rows = fetch_rreo_bimestre(id_ente, year, bimestre)
                    _append_rows(out_path, rows)
                    done.add(key)
                    n += 1
                    if n % 100 == 0:
                        pct = 100 * n / max(todo, 1)
                        print(f"    {label}: {n}/{todo} ({pct:.0f}%)", flush=True)
                except RuntimeError as exc:
                    print(f"    WARN: {exc} — pulando", file=sys.stderr)
                time.sleep(CALL_DELAY)

    print(f"  {label}: concluido ({n} novas chamadas -> {out_path.name})", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# SICONFI full pull
# ─────────────────────────────────────────────────────────────────────────────

def download_siconfi(force: bool = False) -> None:
    """Download all SICONFI RREO data for active spheres."""
    print("Baixando SICONFI — União ...")
    _pull_sphere("uniao", {"Uniao": "1"}, DATA_RAW / "rreo_uniao.csv", force=force)

    estado_entities = {
        uf: code
        for uf, code in TODOS_ESTADOS.items()
        if ESTADOS_SUBSET is None or uf in ESTADOS_SUBSET
    }
    print("Baixando SICONFI — Estados ...")
    _pull_sphere("estados", estado_entities, DATA_RAW / "rreo_estados.csv", force=force)

    if INCLUDE_MUNICIPIOS:
        print("Baixando SICONFI — Municípios ...")
        _pull_sphere("municipios", CAPITAIS, DATA_RAW / "rreo_municipios.csv", force=force)


# ─────────────────────────────────────────────────────────────────────────────
# CNT download
# ─────────────────────────────────────────────────────────────────────────────

def _parse_cnt_period(val) -> tuple[int, int] | None:
    """
    Parse CNT period cell to (ano, trimestre).
    '2023.I' → (2023, 1), '2023.IV' → (2023, 4).
    Annual summary rows (e.g. '2023') return None.
    """
    quarter_map = {"I": 1, "II": 2, "III": 3, "IV": 4}
    s = str(val).strip()
    if "." in s:
        parts = s.split(".", 1)
        try:
            year = int(parts[0])
            q = quarter_map.get(parts[1])
            if q is not None:
                return (year, q)
        except (ValueError, IndexError):
            pass
    return None


def _read_cnt_sheet(xls: pd.ExcelFile, sheet: str, col_idx: int) -> pd.DataFrame:
    """Read one CNT sheet, return DataFrame: ano, trimestre, valor."""
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    rows = []
    for _, row in df.iterrows():
        period = _parse_cnt_period(row.iloc[CNT_COL_PERIODO])
        if period is None:
            continue
        try:
            val = float(row.iloc[col_idx])
        except (TypeError, ValueError):
            continue
        rows.append({"ano": period[0], "trimestre": period[1], "valor": val})
    return pd.DataFrame(rows, columns=["ano", "trimestre", "valor"])


def download_cnt(force: bool = False) -> None:
    """Download IBGE Tab_Compl_CNT.zip and save cnt_trimestral.csv."""
    out_path = DATA_RAW / "cnt_trimestral.csv"
    if out_path.exists() and not force:
        print(f"  CNT: {out_path.name} já existe — use --force para re-baixar")
        return

    print(f"  CNT: baixando {CNT_ZIP_URL} ...")
    req = urllib.request.Request(CNT_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    print(f"  CNT: {len(raw) // 1024} KB baixados")

    zf = zipfile.ZipFile(io.BytesIO(raw))
    fname = zf.namelist()[0]
    with zf.open(fname) as f:
        xls = pd.ExcelFile(f)

    df_curr = _read_cnt_sheet(xls, CNT_SHEET_CORRENTES, CNT_COL_GOVERNO)
    df_vol  = _read_cnt_sheet(xls, CNT_SHEET_VOLUME,    CNT_COL_GOVERNO)

    df_curr["valor"] = df_curr["valor"] / 1000.0   # CNT milhões → bilhões
    df = df_curr.rename(columns={"valor": "consumo_governo_bilhoes"}).merge(
        df_vol.rename(columns={"valor": "volume_idx_1995"}),
        on=["ano", "trimestre"],
        how="left",
    )
    df = df.sort_values(["ano", "trimestre"]).reset_index(drop=True)
    df.to_csv(out_path, index=False)
    print(f"  CNT: {len(df)} trimestres salvos -> {out_path.name}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baixa CNT (IBGE) e RREO (SICONFI) para a replicação Santos et al. (2015)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-baixa tudo do zero, sobrescrevendo CSVs existentes",
    )
    args = parser.parse_args()

    print("=== download.py ===")
    download_cnt(force=args.force)
    download_siconfi(force=args.force)
    print("=== concluído ===")


if __name__ == "__main__":
    main()
