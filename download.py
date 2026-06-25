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
import re
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
    TRU_EDITION,
    TRU_ZIP_URL,
    YEAR_END,
    YEAR_START,
    RPPS_UNIAO_START_YEAR,
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
    "ReceitaDeContribuicoesPatronalFinanceiro",    # RPPS patronal estados (Financeiro plan)
    "ReceitaDeContribuicoesPatronalPrevidenciario", # RPPS patronal União (Previdenciário plan)
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

# ── RPPS União (Anexo 04.2 civis + 04.3 militares) ───────────────────────────
# "Resultado" rows = receitas − despesas; negative when in deficit.
# contrib_imputada = −Resultado (negate so deficit → positive imputed contribution).
# NOTE: 2015 returns 0 rows from SICONFI (verified via API probe); gap documented.
RPPS_UNIAO_ANEXOS = ["RREO-Anexo 04.2", "RREO-Anexo 04.3"]

RPPS_UNIAO_RESULTADO_CONTAS = {
    "RREO4ResultadoRPPSPrevidenciario",   # civis federal (04.2 from 2023+)
    "ResultadoRPPSPrevidenciarioFCDF",    # servidores distritais FCDF (04.2 from 2023+)
    "RREO4ResultadoRPPSFinanceiro",       # pensões militares (04.2 in 2018-2022; 04.3 from 2023+)
    "ResultadoInativosMilitares",         # inativos militares (04.2 in 2019-2022; 04.3 from 2023+)
}

# Pattern for cumulative YTD despesas coluna. The year suffix is captured to
# exclude prior-year comparison columns (e.g. "/ 2017" inside a 2018 report).
_ACUM_DESP_RE   = re.compile(r"DESPESAS LIQUIDADAS.*/\s*(\d{4})$")
_ACUM_DESP_NORM = "DESPESAS LIQUIDADAS ATÉ O BIMESTRE (acum)"

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
        cod_conta = item.get("cod_conta", "")
        # Normalise year-embedded coluna used by União Anexo 04:
        # 'RECEITAS REALIZADAS ATÉ O BIMESTRE / 2023' -> standard '(b)' form.
        coluna = item.get("coluna", "")
        if re.match(r"RECEITAS REALIZADAS.*/\s*\d{4}$", coluna):
            coluna = "RECEITAS REALIZADAS ATÉ O BIMESTRE (b)"

        if cod_conta in KEEP_CONTAS and coluna in KEEP_COLUNAS:
            rows.append(
                {
                    "ano": year,
                    "bimestre": bimestre,
                    "cod_ibge": str(item.get("cod_ibge", id_ente)),
                    "uf": item.get("uf", ""),
                    "coluna": coluna,
                    "cod_conta": cod_conta,
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
# União RPPS (Anexo 04.2 + 04.3) — separate pull, separate file
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_rpps_uniao_bimestre(year: int, bimestre: int, anexo: str) -> list[dict]:
    """
    Fetch Resultado rows from one RPPS União anexo × year × bimestre.
    Keeps only the four Resultado cod_conta values and normalises the
    year-suffixed coluna to a stable key for build_indicators.py.
    """
    params = {
        "an_exercicio": year,
        "nr_periodo":   bimestre,
        "co_tipo_demonstrativo": "RREO",
        "no_anexo":     anexo,
        "id_ente":      "1",
    }
    url = SICONFI_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})

    items: list[dict] = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                items = json.loads(r.read()).get("items", [])
            break
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"SICONFI RPPS fetch failed: {anexo} {year}B{bimestre}"
                ) from exc
            time.sleep(2 ** attempt)

    rows = []
    for item in items:
        cod_conta = item.get("cod_conta", "")
        if cod_conta not in RPPS_UNIAO_RESULTADO_CONTAS:
            continue
        coluna = item.get("coluna", "")
        m = _ACUM_DESP_RE.match(coluna)
        if not m:
            continue  # keep only LIQUIDADAS (drop DOTAÇÃO, EMPENHADAS, PAGAS)
        if int(m.group(1)) != year:
            continue  # skip prior-year comparison column (e.g. "/ 2017" in 2018 report)
        rows.append({
            "ano":       year,
            "bimestre":  bimestre,
            "cod_ibge":  "1",
            "uf":        item.get("uf", "BR"),
            "coluna":    _ACUM_DESP_NORM,
            "cod_conta": cod_conta,
            "conta":     item.get("conta", ""),
            "valor":     float(item.get("valor") or 0),
        })
    return rows


def download_siconfi_rpps_uniao(force: bool = False) -> None:
    """
    Download União RPPS Resultado rows (Anexo 04.2 + 04.3) to
    data/raw/rreo_rpps_uniao.csv.

    Covers RPPS_UNIAO_START_YEAR (2016) through YEAR_END.
    2015 is intentionally excluded — SICONFI returns 0 rows for that year
    (verified by API probe: an_exercicio=2015 → empty for both anexos).
    """
    out_path = DATA_RAW / "rreo_rpps_uniao.csv"
    if force and out_path.exists():
        out_path.unlink()

    done = _already_downloaded(out_path)
    years = list(range(RPPS_UNIAO_START_YEAR, YEAR_END + 1))
    bimestres = list(range(1, 7))

    todo = sum(
        1 for y in years for b in bimestres
        if ("1", y, b) not in done
    )
    print(f"  rpps_uniao: {todo} combinacoes pendentes ({len(done)} ja salvas)", flush=True)

    n = 0
    for year in years:
        for bimestre in bimestres:
            if ("1", year, bimestre) in done:
                continue
            rows: list[dict] = []
            for anexo in RPPS_UNIAO_ANEXOS:
                try:
                    rows.extend(_fetch_rpps_uniao_bimestre(year, bimestre, anexo))
                except RuntimeError as exc:
                    print(f"    WARN: {exc} — pulando", file=sys.stderr)
                time.sleep(CALL_DELAY)
            _append_rows(out_path, rows)
            done.add(("1", year, bimestre))
            n += 1
            if n % 20 == 0:
                pct = 100 * n / max(todo, 1)
                print(f"    rpps_uniao: {n}/{todo} ({pct:.0f}%)", flush=True)

    print(f"  rpps_uniao: concluido ({n} novas chamadas -> {out_path.name})", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# SICONFI full pull
# ─────────────────────────────────────────────────────────────────────────────

def download_siconfi(force: bool = False) -> None:
    """Download all SICONFI RREO data for active spheres."""
    print("Baixando SICONFI — União ...")
    _pull_sphere("uniao", {"Uniao": "1"}, DATA_RAW / "rreo_uniao.csv", force=force)

    print("Baixando SICONFI — União RPPS (Anexo 04.2 + 04.3) ...")
    download_siconfi_rpps_uniao(force=force)

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
# TRU download
# ─────────────────────────────────────────────────────────────────────────────

def _find_tru_govt_col(df: pd.DataFrame) -> int | None:
    """
    Locate the government activity column by finding the row for
    'Contribuicoes sociais imputadas' (only govt has non-zero values there)
    and returning the index of the first positive entry in cols 5-30.
    """
    for i in range(50, 70):
        label = str(df.iloc[i, 0]).strip()
        if "imputada" in label.lower():
            for j in range(5, 30):
                try:
                    if float(df.iloc[i, j]) > 0:
                        return j
                except (TypeError, ValueError):
                    pass
    return None


def download_tru(force: bool = False) -> None:
    """
    Download TRU_resumo_2000_2021_xls.zip from IBGE and parse component values
    for the government activity into data/raw/tru_governo.csv.

    Output schema: ano, componente, governo_bilhoes
      componente in {"remuneracoes", "contrib_imputadas"}
      governo_bilhoes: raw TRU value / 1000 (TRU unit = R$ 1 milhao)

    Covers years max(YEAR_START, 2000) through TRU_EDITION (2015-2021 by default).
    """
    out_path = DATA_RAW / "tru_governo.csv"
    if out_path.exists() and not force:
        print(f"  TRU: {out_path.name} ja existe -- use --force para re-baixar")
        return

    print(f"  TRU: baixando {TRU_ZIP_URL} ...", flush=True)
    req = urllib.request.Request(TRU_ZIP_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    print(f"  TRU: {len(raw) // 1024} KB baixados", flush=True)

    zf = zipfile.ZipFile(io.BytesIO(raw))
    rows: list[dict] = []

    for year in range(max(YEAR_START, 2000), TRU_EDITION + 1):
        fname = f"TRU{year}resumo.xls"
        if fname not in zf.namelist():
            print(f"  TRU {year}: arquivo nao encontrado no ZIP -- pulando", file=sys.stderr)
            continue

        with zf.open(fname) as f:
            df = pd.read_excel(f, sheet_name=0, header=None, engine="xlrd")

        govt_col = _find_tru_govt_col(df)
        if govt_col is None:
            print(f"  TRU {year}: coluna governo nao encontrada -- pulando", file=sys.stderr)
            continue

        for i in range(50, min(70, df.shape[0])):
            label = str(df.iloc[i, 0]).strip()
            try:
                val = float(df.iloc[i, govt_col])
            except (TypeError, ValueError):
                continue

            if "Remunera" in label:
                rows.append({"ano": year, "componente": "remuneracoes_sal_ce", "governo_bilhoes": val / 1000.0})
            elif "imputada" in label.lower():
                rows.append({"ano": year, "componente": "contrib_imputadas", "governo_bilhoes": val / 1000.0})

        print(f"  TRU {year}: ok", flush=True)

    if not rows:
        print("  TRU: nenhum dado extraido -- verifique o ZIP", file=sys.stderr)
        return

    pd.DataFrame(rows).sort_values(["ano", "componente"]).to_csv(out_path, index=False)
    print(f"  TRU: {len(rows)} linhas salvas -> {out_path.name}", flush=True)


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
    download_tru(force=args.force)
    download_siconfi(force=args.force)
    print("=== concluido ===")


if __name__ == "__main__":
    main()
