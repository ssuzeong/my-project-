#!/usr/bin/env python3
"""Compute soil-moisture-memory timescales (tSMM) with the 10 methods listed in README §3
for one monthly ERA5 daily file and one grid point, and write a comparison table.

Usage:
    python .claude/skills/smm-timescale-compare/scripts/compute_tsmm.py YYYYMM LAT LON [--outdir results]

Input  : /land1/ERA5/daily/land/YYYYMM_land.nc  (opened read-only, never modified)
         swvl1 (0-7 cm, m3/m3), mtpr (kg m-2 s-1 -> mm/day)
Output : <outdir>/tsmm_YYYYMM_<lat>N_<lon>E.csv          method table
         <outdir>/tsmm_YYYYMM_<lat>N_<lon>E_timeseries.csv  point series
         <outdir>/tsmm_YYYYMM_<lat>N_<lon>E.md           report

All timescales are in days (dt = 1 day). Deterministic: no random numbers.
"""
import argparse
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xarray as xr
from scipy.optimize import curve_fit

DATA_TMPL = "/land1/ERA5/daily/land/{ym}_land.nc"
DT = 1.0                 # days
WET_DAY_MM = 1.0         # wet-day threshold for precipitation occurrence (mm/day)
MIN_DRYDOWN_LEN = 4      # minimum number of points in a drydown


# ---------------------------------------------------------------- data
def load_point(ym, lat, lon):
    path = DATA_TMPL.format(ym=ym)
    with xr.open_dataset(path) as ds:      # read-only access
        p = ds[["swvl1", "mtpr"]].sel(latitude=lat, longitude=lon, method="nearest").load()
        sst_mean = float(ds["sst"].sel(latitude=lat, longitude=lon, method="nearest").mean())
    df = pd.DataFrame({
        "date": pd.to_datetime(p["time"].values),
        "swvl1": p["swvl1"].values.astype(float),
        "precip_mm_day": p["mtpr"].values.astype(float) * 86400.0,
    })
    info = {"path": path, "grid_lat": float(p.latitude), "grid_lon": float(p.longitude),
            "land": bool(np.isnan(sst_mean))}
    return df, info


# ---------------------------------------------------------------- ACF helpers
def acf(x, max_lag):
    """Biased sample autocorrelation r(k) = sum x_t x_{t+k} / sum x_t^2 of an anomaly series."""
    x = np.asarray(x, float)
    x = x - x.mean()
    den = np.sum(x * x)
    return np.array([np.sum(x[: len(x) - k] * x[k:]) / den for k in range(max_lag + 1)])


def first_crossing(r, thr, strict=False):
    """First lag where r <= thr (or r < thr if strict); linear interpolation between lags.
    Returns (interpolated lag, integer lag) or (nan, None) if never reached."""
    for k in range(1, len(r)):
        hit = r[k] < thr if strict else r[k] <= thr
        if hit:
            frac = (r[k - 1] - thr) / (r[k - 1] - r[k]) if r[k - 1] != r[k] else 1.0
            return (k - 1 + frac) * DT, k
    return math.nan, None


def integral_timescale(r):
    """Trapezoidal integral of r(tau) from lag 0 up to the first zero crossing."""
    t0, k0 = first_crossing(r, 0.0)
    if k0 is None:
        return np.trapezoid(r, dx=DT), len(r) - 1
    seg = list(r[:k0])                      # lags 0..k0-1 (all > 0)
    area = np.trapezoid(seg, dx=DT) if len(seg) > 1 else 0.0
    area += 0.5 * r[k0 - 1] * (t0 - (k0 - 1) * DT)   # last partial triangle to r = 0
    return area, t0


# ---------------------------------------------------------------- drydowns
def find_drydowns(sm, p):
    """Runs of strictly decreasing SM of >= MIN_DRYDOWN_LEN points, starting at a local max.
    Rain on the start day is allowed (it creates the peak). A decreasing run already implies
    infiltration < losses; runs whose later days have P >= 5*WET_DAY_MM are dropped
    (a sizeable storm that did not raise SM makes the pure-decay assumption doubtful)."""
    out, n, i = [], len(sm), 0
    while i < n - 1:
        if sm[i + 1] < sm[i]:
            j = i
            while j < n - 1 and sm[j + 1] < sm[j]:
                j += 1
            if j - i + 1 >= MIN_DRYDOWN_LEN and np.all(p[i + 1: j + 1] < 5 * WET_DAY_MM):
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def expdecay(t, theta_w, dtheta, tau):
    return theta_w + dtheta * np.exp(-t / tau)


def fit_drydown(seg):
    t = np.arange(len(seg)) * DT
    lo, hi = [0.0, 0.0, 0.1], [seg.min(), 1.0, 365.0]
    p0 = [0.9 * seg.min(), seg[0] - 0.9 * seg.min(), 5.0]
    popt, _ = curve_fit(expdecay, t, seg, p0=p0, bounds=(lo, hi), maxfev=20000)
    resid = seg - expdecay(t, *popt)
    r2 = 1 - np.sum(resid ** 2) / np.sum((seg - seg.mean()) ** 2)
    return popt, r2


# ---------------------------------------------------------------- APSM
def run_lengths(anom, thr):
    """Lengths of runs where anom > thr (positive) or anom < -thr (negative)."""
    state = np.where(anom > thr, 1, np.where(anom < -thr, -1, 0))
    runs, cur, length = [], 0, 0
    for s in state:
        if s != 0 and s == cur:
            length += 1
        else:
            if cur != 0:
                runs.append(length)
            cur, length = s, (1 if s != 0 else 0)
    if cur != 0:
        runs.append(length)
    return runs


# ---------------------------------------------------------------- main
def compute(df, detrend=False):
    sm = df["swvl1"].values
    n = len(sm)
    t = np.arange(n)
    if detrend:
        anom = sm - np.polyval(np.polyfit(t, sm, 1), t)
    else:
        anom = sm - sm.mean()
    r = acf(anom, n - 1)
    thr95 = 1.96 / math.sqrt(n)
    res = {}
    res["e-folding lag"] = first_crossing(r, 1 / math.e)[0]
    res["Zero-crossing lag"] = first_crossing(r, 0.0)[0]
    res["Significance-threshold lag"] = first_crossing(r, thr95, strict=True)[0]
    res["Integral timescale"] = integral_timescale(r)[0]
    rho1 = r[1]
    res["Decorrelation time"] = (1 + rho1) / (1 - rho1) * DT
    return res, r, anom, thr95


# ---------------------------------------------------------------- reliability
# Fixed rules (same input -> same grade). Grades: 높음 / 중간 / 낮음 / "-" (값 없음).
# One month of data cannot be deseasonalized and SE(r) ~ 1/sqrt(N) is large, so
# ACF-based methods are capped at 중간.
GOOD_DD_MIN_LEN, GOOD_DD_MIN_R2 = 6, 0.95


def reliability(n, r, base, dtr, thr95, dd_rows, apsm_mean, apsm_runs):
    se = 1 / math.sqrt(n)
    out = {}

    def rel_change(a, b):
        return abs(a - b) / a if a and not math.isnan(a) and not math.isnan(b) else math.nan

    def acf_grade(name, extra):
        v, vd = base[name], dtr[name]
        lag_ok = v <= n / 4
        dch = rel_change(v, vd)
        grade = "중간" if (lag_ok and dch < 0.10) else "낮음"
        why = (f"N={n}, SE(r)≈{se:.2f}; 값 {v:.1f}일 {'≤' if lag_ok else '>'} N/4={n/4:.1f}일; "
               f"detrend 변화 {dch*100:.0f}%; {extra}")
        return grade, why

    out["e-folding lag"] = acf_grade("e-folding lag", "계절주기 제거 불가로 상한 '중간'")
    out["Integral timescale"] = acf_grade(
        "Integral timescale", "적분 상한(첫 zero crossing) 선택에 의존, 상한 '중간'")

    near0 = [k for k in range(1, len(r)) if abs(r[k]) < se]
    span = f"{near0[0]}–{near0[-1]}" if near0 else "없음"
    out["Zero-crossing lag"] = ("낮음",
        f"abs(r)<SE(r)={se:.2f}인 lag가 {len(near0)}개(lag {span}) → 교차 위치가 잡음에 좌우됨; "
        "한 달 안의 습윤–건조 순환이 음의 tail을 만듦")
    out["Significance-threshold lag"] = ("낮음",
        f"임계값 1.96/√N={thr95:.3f}이 N만으로 정해짐; 1/e={1/math.e:.3f}와 차이 "
        f"{abs(thr95-1/math.e):.3f}로 e-folding과 독립적인 정보가 거의 없음")

    rho1 = r[1]
    ef_ar1 = -1 / math.log(rho1) if 0 < rho1 < 1 else math.nan
    ef = base["e-folding lag"]
    dev = rel_change(ef, ef_ar1)
    out["Decorrelation time"] = (("중간" if dev < 0.25 else "낮음"),
        f"lag-1만 사용하고 AR(1)을 가정; ρ₁={rho1:.2f}의 AR(1) e-folding {ef_ar1:.1f}일 vs 관측 "
        f"{ef:.1f}일(차이 {dev*100:.0f}%, 기준 25%); r₂={r[2]:.2f} vs ρ₁²={rho1**2:.2f}")

    out["Two-timescale decomposition (Entin)"] = ("-", "30일 자료로는 수개월 lag의 ln r(τ) 기울기를 구할 수 없음")
    out["Interannual autocorrelation (Koster & Suarez)"] = ("-", "5년 이상(이상적으로 20년) 자료가 필요함")
    out["Hybrid stochastic-deterministic model (McColl et al., 2019)"] = ("-", "원문 식 미확인으로 계산 안 함")

    good = [d for d in dd_rows if d["n"] >= GOOD_DD_MIN_LEN and d["r2"] >= GOOD_DD_MIN_R2]
    taus = [d["tau"] for d in dd_rows]
    g = "높음" if len(good) >= 3 else ("중간" if good else "낮음")
    out["SMD fitting (median tau)"] = (g,
        f"drydown {len(dd_rows)}개 중 기준(≥{GOOD_DD_MIN_LEN}점, R²≥{GOOD_DD_MIN_R2}) 충족 {len(good)}개; "
        + (f"τ 범위 {min(taus):.1f}–{max(taus):.1f}일; " if taus else "")
        + "짧은 구간은 매개변수 3개 대비 점이 적어 θw·τ가 불안정")

    vals = [v for v in apsm_mean.values() if not math.isnan(v)]
    spread = (max(vals) - min(vals)) / apsm_mean[0.0] if vals and apsm_mean[0.0] else math.nan
    runs0 = apsm_runs[0.0]
    out["APSM (threshold 0)"] = (("중간" if spread < 0.30 else "낮음"),
        f"임계값(0/0.5/1σ)에 따라 {min(vals):.1f}–{max(vals):.1f}일(변동 {spread*100:.0f}%, 기준 30%); "
        f"run {len(runs0)}개뿐이고 첫·마지막 run은 월 경계에서 잘림")
    return out


# ---------------------------------------------------------------- derived numbers for interpretation
def wet_spells(dates, p):
    """Consecutive wet days (P >= WET_DAY_MM): list of (start, end, n_days, total_mm)."""
    out, i, n = [], 0, len(p)
    while i < n:
        if p[i] >= WET_DAY_MM:
            j = i
            while j + 1 < n and p[j + 1] >= WET_DAY_MM:
                j += 1
            out.append((dates[i], dates[j], j - i + 1, float(p[i: j + 1].sum())))
            i = j + 1
        else:
            i += 1
    return out


def derived_quantities(n, r, base, dtr, thr95, rows, dd_rows, apsm_mean, df):
    """Every number quoted in the written interpretation, already rounded as it should be quoted.
    Returns list of (key, description, value_str)."""
    D = []
    add = lambda k, d, v: D.append((k, d, v))
    se = 1 / math.sqrt(n)
    rho1 = r[1]
    ef = base["e-folding lag"]
    it = base["Integral timescale"]
    dc = base["Decorrelation time"]
    zc = base["Zero-crossing lag"]
    smd = next(v for m, v, *_ in rows if m.startswith("SMD"))
    vals = {m: v for m, v, *_ in rows if not math.isnan(v)}
    grades = {m: g for m, _, _, g, *_ in rows}
    mid = {m: vals[m] for m in vals if grades[m] == "중간"}
    ef_ar1 = -1 / math.log(rho1)
    ratio_ar1 = (1 + rho1) / (1 - rho1) / ef_ar1          # exact AR(1) decorrelation / e-folding

    add("D01", "값이 계산된 방법 수 / 전체", f"{len(vals)} / {len(rows)}")
    add("D02", "신뢰도 '높음' 방법 수", f"{sum(g == '높음' for g in grades.values())}")
    add("D03", "N (일)", f"{n}")
    add("D04", "SE(r) = 1/√N", f"{se:.2f}")
    add("D05", "습윤일 수 (P ≥ 1 mm/day)", f"{int((df['precip_mm_day'].values >= WET_DAY_MM).sum())}")
    add("D06", "계산된 값 범위 (일)", f"{min(vals.values()):.1f}–{max(vals.values()):.1f}")
    add("D07", "계산된 값 최대/최소 배수", f"{max(vals.values()) / min(vals.values()):.1f}")
    add("D08", "신뢰도 '중간' 값 범위 (일)", f"{min(mid.values()):.1f}–{max(mid.values()):.1f}" if mid else "N/A")
    add("D09", "신뢰도 '중간' 최대/최소 배수", f"{max(mid.values()) / min(mid.values()):.1f}" if mid else "N/A")
    add("D10", "SMD / e-folding 배수", f"{smd / ef:.1f}")
    add("D11", "SMD / Integral 배수", f"{smd / it:.1f}")
    add("D12", "ρ₁ (lag-1 자기상관)", f"{rho1:.2f}")
    add("D13", "Decorrelation / e-folding 배수 (관측)", f"{dc / ef:.1f}")
    add("D14", "Decorrelation / e-folding 배수 (ρ₁의 AR(1) 기대값)", f"{ratio_ar1:.1f}")
    add("D15", "ρ₁로 계산한 AR(1) e-folding (일)", f"{ef_ar1:.1f}")
    add("D16", "관측 e-folding (일)", f"{ef:.1f}")
    add("D17", "AR(1) e-folding 대비 관측 e-folding 차이 (%)", f"{abs(ef - ef_ar1) / ef * 100:.0f}")
    add("D18", "r₂ (관측)", f"{r[2]:.2f}")
    add("D19", "ρ₁² (r₂의 AR(1) 기대값)", f"{rho1 ** 2:.2f}")
    add("D20", "95% 임계값 1.96/√N", f"{thr95:.3f}")
    add("D21", "1/e", f"{1 / math.e:.3f}")
    add("D22", "유의수준 lag − e-folding (일)", f"{base['Significance-threshold lag'] - ef:.2f}")
    near0 = [k for k in range(1, len(r)) if abs(r[k]) < se]
    add("D23", "abs(r) < SE(r)인 첫 lag", f"{near0[0]}" if near0 else "N/A")
    add("D24", "Zero-crossing lag (일)", f"{zc:.1f}")
    spells = wet_spells([d.date() for d in df["date"]], df["precip_mm_day"].values)
    if spells:
        last = spells[-1]
        add("D25", "마지막 연속 습윤 구간 (기간, 일수, 합계 mm)",
            f"{last[0]:%m/%d}–{last[1]:%m/%d}, {last[2]}일, {last[3]:.1f} mm")
        big = max(spells, key=lambda x: x[3])
        add("D26", "강수 합계 최대 연속 습윤 구간", f"{big[0]:%m/%d}–{big[1]:%m/%d}, {big[2]}일, {big[3]:.1f} mm")
    av = [v for v in apsm_mean.values() if not math.isnan(v)]
    add("D27", "APSM 임계값(0/0.5/1σ)별 값 범위 (일)", f"{min(av):.1f}–{max(av):.1f}" if av else "N/A")
    good = [d for d in dd_rows if d["n"] >= GOOD_DD_MIN_LEN and d["r2"] >= GOOD_DD_MIN_R2]
    add("D28", "기준 충족 drydown 수 / 전체", f"{len(good)} / {len(dd_rows)}")
    for i, d in enumerate(good, 1):
        add(f"D29.{i}", "기준 충족 drydown (기간, 점 수, τ, R²)",
            f"{d['start']:%m/%d}–{d['end']:%m/%d}, {d['n']}점, τ={d['tau']:.1f}일, R²={d['r2']:.3f}")
    for i, d in enumerate([d for d in dd_rows if d not in good], 1):
        add(f"D30.{i}", "기준 미충족 drydown (기간, 점 수, τ, θw)",
            f"{d['start']:%m/%d}–{d['end']:%m/%d}, {d['n']}점, τ={d['tau']:.1f}일, θw={d['theta_w']:.3f}")
    diffs = {m: abs(v - vd) for m, v, vd, *_ in rows if not (math.isnan(v) or math.isnan(vd))}
    mx = max(diffs, key=diffs.get)
    add("D31", "Detrend에 따른 최대 변화 (일, 방법)", f"{diffs[mx]:.2f} ({mx})")
    return D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ym")
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    ap.add_argument("--outdir", default="results")
    a = ap.parse_args()

    df, info = load_point(a.ym, a.lat, a.lon)
    if df["swvl1"].isna().any():
        raise SystemExit("swvl1 has missing values at this grid point (sea or masked cell).")
    sm, p = df["swvl1"].values, df["precip_mm_day"].values
    n = len(sm)

    base, r, anom, thr95 = compute(df, detrend=False)
    dtr, r_dt, _, _ = compute(df, detrend=True)

    # drydowns
    dd = find_drydowns(sm, p)
    dd_rows = []
    for (i, j) in dd:
        popt, r2 = fit_drydown(sm[i: j + 1])
        dd_rows.append({"start": df["date"][i].date(), "end": df["date"][j].date(), "n": j - i + 1,
                        "theta_w": popt[0], "dtheta": popt[1], "tau": popt[2], "r2": r2})
    tau_smd = float(np.median([d["tau"] for d in dd_rows])) if dd_rows else math.nan

    sd = anom.std(ddof=1)
    apsm = {k: run_lengths(anom, k * sd) for k in (0.0, 0.5, 1.0)}
    apsm_mean = {k: (float(np.mean(v)) if v else math.nan) for k, v in apsm.items()}

    rows = [
        ("e-folding lag", base["e-folding lag"], dtr["e-folding lag"], "first lag r<=1/e (interp.)"),
        ("Zero-crossing lag", base["Zero-crossing lag"], dtr["Zero-crossing lag"], "first lag r<=0 (interp.)"),
        ("Significance-threshold lag", base["Significance-threshold lag"], dtr["Significance-threshold lag"],
         f"first lag r<1.96/sqrt(N)={thr95:.3f} (interp.)"),
        ("Integral timescale", base["Integral timescale"], dtr["Integral timescale"],
         "trapezoid of r(tau), lag 0 to first zero crossing"),
        ("Decorrelation time", base["Decorrelation time"], dtr["Decorrelation time"],
         f"(1+rho1)/(1-rho1), rho1={r[1]:.3f} (detrended {r_dt[1]:.3f})"),
        ("Two-timescale decomposition (Entin)", math.nan, math.nan, "N/A: needs multi-month lags"),
        ("Interannual autocorrelation (Koster & Suarez)", math.nan, math.nan, "N/A: needs >=5 years"),
        ("SMD fitting (median tau)", tau_smd, math.nan,
         f"{len(dd_rows)} drydowns (>= {MIN_DRYDOWN_LEN} d), 3-param exp fit; raw SM, no anomaly"),
        ("Hybrid stochastic-deterministic model (McColl et al., 2019)", math.nan, math.nan,
         "계산 안 함: 원문(McColl et al., 2019)의 t^S·t^L 산정식을 확인하지 못함. "
         "임의로 단순화한 식은 다른 방법과 비교할 수 없으므로 값을 내지 않음"),
        ("APSM (threshold 0)", apsm_mean[0.0], math.nan,
         f"mean run length of same-sign anomaly; runs={apsm[0.0]}"),
    ]
    rel = reliability(n, r, base, dtr, thr95, dd_rows, apsm_mean, apsm)
    assert len(rows) == 10 and set(rel) == {m for m, *_ in rows}
    rows = [(m, v, vd, rel[m][0], rel[m][1], note) for m, v, vd, note in rows]
    table = pd.DataFrame(rows, columns=["method", "tsmm_days", "tsmm_days_detrended",
                                        "reliability", "reliability_reason", "note"])

    derived = derived_quantities(n, r, base, dtr, thr95, rows, dd_rows, apsm_mean, df)

    os.makedirs(a.outdir, exist_ok=True)
    stem = os.path.join(a.outdir, f"tsmm_{a.ym}_{a.lat:.2f}N_{a.lon:.2f}E")
    table.to_csv(stem + ".csv", index=False, float_format="%.3f")
    pd.DataFrame(derived, columns=["key", "description", "value"]).to_csv(stem + "_derived.csv", index=False)
    ts = df.copy()
    ts["anomaly"] = anom
    ts["acf_lag_k"] = r
    ts.to_csv(stem + "_timeseries.csv", index=False, float_format="%.5f")

    # ---------------- report
    def f(v):
        return "N/A" if (v is None or (isinstance(v, float) and math.isnan(v))) else f"{v:.2f}"
    L = []
    L.append(f"# tSMM comparison — {a.ym}, requested ({a.lat:.2f}N, {a.lon:.2f}E)\n")
    L.append(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `.claude/skills/smm-timescale-compare/scripts/compute_tsmm.py`.\n")
    L.append("## Grid & data")
    L.append(f"- File: `{info['path']}` (read-only)")
    L.append(f"- Nearest grid cell: **{info['grid_lat']:.2f}N, {info['grid_lon']:.2f}E** "
             f"(land: {'yes, sst is NaN' if info['land'] else 'NO — sst defined, check cell'})")
    L.append(f"- Variable: swvl1 (0–7 cm, m³/m³), N = {n} days "
             f"({df['date'].iloc[0].date()} – {df['date'].iloc[-1].date()}); mtpr → mm/day")
    L.append(f"- swvl1 mean {sm.mean():.4f}, sd {sm.std(ddof=1):.4f}, min {sm.min():.4f}, max {sm.max():.4f}; "
             f"precip total {p.sum():.1f} mm, wet days (≥{WET_DAY_MM} mm) {int((p >= WET_DAY_MM).sum())}\n")
    L.append("## Preprocessing")
    L.append("- Deseasonalization: not possible with one month → **monthly-mean removal only** (main column).")
    L.append("- Sensitivity column: additional linear detrend within the month.")
    L.append("- ACF: biased estimator, lags 0–N−1; crossings linearly interpolated between integer lags.")
    L.append("- SMD uses raw swvl1 (physical decay), not anomalies.\n")
    L.append("## Method comparison (days)")
    L.append("| # | Method | tSMM | tSMM (detrended) | 신뢰도 | 신뢰도 근거 | Note |\n"
             "|---:|---|---:|---:|:---:|---|---|")
    for i, (m, v, vd, g, why, note) in enumerate(rows, 1):
        if note.startswith("계산 안 함"):
            L.append(f"| {i} | {m} | 계산 안 함 | 계산 안 함 | {g} | {why} | {note.split(': ', 1)[1]} |")
        else:
            L.append(f"| {i} | {m} | {f(v)} | {f(vd)} | {g} | {why} | {note} |")
    L.append("\n신뢰도 기준(스크립트에 고정): 이 달 자료 안에서 값이 얼마나 안정적인지에 대한 등급이며, "
             "기후학적 메모리 추정의 정확도가 아니다. ACF 계열은 값 ≤ N/4이고 detrend 변화 <10%이면 중간, "
             "아니면 낮음(계절주기 제거 불가로 상한 중간). Zero-crossing·유의수준 lag는 항상 낮음(근거는 표 참고). "
             "Decorrelation은 AR(1) 함의 e-folding과 관측값 차이 <25%이면 중간. "
             f"SMD는 좋은 drydown(≥{GOOD_DD_MIN_LEN}점, R²≥{GOOD_DD_MIN_R2}) 3개 이상 높음, 1–2개 중간, 0개 낮음. "
             "APSM은 임계값 0/0.5/1σ 간 변동 <30%이면 중간. '-'는 값이 없음.")
    L.append("\n### ACF r(τ), mean-removed")
    L.append("| lag | " + " | ".join(str(k) for k in range(11)) + " |")
    L.append("|---|" + "---:|" * 11)
    L.append("| r | " + " | ".join(f"{x:.2f}" for x in r[:11]) + " |")
    L.append(f"\n95% threshold 1.96/√N = {thr95:.3f}; 1/e = {1/math.e:.3f}.\n")
    L.append("### Drydowns")
    if dd_rows:
        L.append("| start | end | n | θw | Δθ | τ (d) | R² |\n|---|---|---:|---:|---:|---:|---:|")
        for d in dd_rows:
            L.append(f"| {d['start']} | {d['end']} | {d['n']} | {d['theta_w']:.3f} | {d['dtheta']:.3f} | "
                     f"{d['tau']:.2f} | {d['r2']:.3f} |")
    else:
        L.append("No drydown ≥ %d days." % MIN_DRYDOWN_LEN)
    L.append("\n### APSM threshold sensitivity (mean run length, days)")
    for k in (0.0, 0.5, 1.0):
        L.append(f"- ±{k:.1f}σ: {f(apsm_mean[k])} (runs {apsm[k]})")
    L.append("\n## 해석용 수치 (스크립트 계산)")
    L.append("해석에 쓰는 숫자는 모두 이 표에서 그대로 인용한다 (같은 반올림).\n")
    L.append("| key | 항목 | 값 |\n|---|---|---|")
    for k, d, v in derived:
        L.append(f"| {k} | {d} | {v} |")
    L.append("")
    with open(stem + ".md", "w") as fh:
        fh.write("\n".join(L))
    print("\n".join(L))
    print(f"\nWrote {stem}.csv, {stem}_derived.csv, {stem}_timeseries.csv, {stem}.md")


if __name__ == "__main__":
    main()
