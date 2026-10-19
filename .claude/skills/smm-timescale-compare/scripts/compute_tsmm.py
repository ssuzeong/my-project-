"""Compute soil moisture memory timescales (t_SMM) with the README methods for one grid point.

Input is limited to one netCDF file of daily data covering a single month and
one grid point (lat/lon). The file is opened read-only. Results are written to
the repository's top-level results/ directory (not the skill folder) as a CSV
table, a Markdown table (with the preprocessing notes), and the extracted point
time series.

Example (from the repository root):
    python .claude/skills/smm-timescale-compare/scripts/compute_tsmm.py \
        /land1/ERA5/daily/land/202306_land.nc --lat 35.13 --lon 129.10
"""
import argparse
import csv
import os
from datetime import date

import netCDF4
import numpy as np
from scipy import optimize

# <repo>/.claude/skills/smm-timescale-compare/scripts/compute_tsmm.py -> <repo>
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *[os.pardir] * 4))
DEFAULT_OUTDIR = os.path.join(REPO_ROOT, 'results')

PREPS = ['mean-removed', 'linear-detrended']
PREP_LABELS = {'mean-removed': '평균 제거', 'linear-detrended': '선형 추세 제거'}


# ---------------------------------------------------------------- data ----

def great_circle_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    d = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * np.arcsin(np.sqrt(d))


def load_point(path, tlat, tlon, var, pvar, search_deg=1.0):
    """Nearest land grid point: sst NaN (no lsm in file) and var finite and > 0."""
    ds = netCDF4.Dataset(path, 'r')
    lat = ds['latitude'][:].data
    lon = ds['longitude'][:].data
    tlon_mod = tlon % 360 if lon.min() >= 0 else tlon
    ii = np.where(abs(lat - tlat) <= search_deg)[0]
    jj = np.where(abs(lon - tlon_mod) <= search_deg)[0]
    cands = []
    for i in ii:
        for j in jj:
            if 'sst' in ds.variables and np.isfinite(np.ma.filled(ds['sst'][0, i, j], np.nan)):
                continue
            sm = np.ma.filled(ds[var][:, i, j], np.nan)
            if np.all(np.isfinite(sm)) and sm.min() > 0:
                cands.append((great_circle_km(tlat, tlon_mod, lat[i], lon[j]), i, j))
    if not cands:
        ds.close()
        raise SystemExit(f'no land grid point within {search_deg} deg')
    dist, i, j = min(cands)
    t = ds['time']
    info = {
        'lat': float(lat[i]), 'lon': float(lon[j]), 'dist_km': float(dist),
        'units': ds[var].units,
        'dates': [d.strftime('%Y-%m-%d') for d in netCDF4.num2date(t[:], t.units, getattr(t, 'calendar', 'standard'))],
    }
    sm = np.ma.filled(ds[var][:, i, j], np.nan).astype(float)
    pr = None
    if pvar in ds.variables:
        pr = np.ma.filled(ds[pvar][:, i, j], np.nan).astype(float) * 86400  # kg m-2 s-1 -> mm/day
    ds.close()
    check_one_month_daily(info['dates'])
    return sm, pr, info


def check_one_month_daily(dates):
    """Input must be consecutive daily values within a single calendar month."""
    days = [date.fromisoformat(d) for d in dates]
    if len({(d.year, d.month) for d in days}) != 1:
        raise SystemExit(f'input spans more than one month: {dates[0]} ~ {dates[-1]}')
    if any((b - a).days != 1 for a, b in zip(days, days[1:])):
        raise SystemExit('input is not a consecutive daily series')


# ------------------------------------------------------------- helpers ----

def preprocess(sm, prep):
    t = np.arange(len(sm))
    if prep == 'mean-removed':
        return sm - sm.mean()
    return sm - np.polyval(np.polyfit(t, sm, 1), t)


def acf(x, maxlag):
    """Biased estimator (divide by N)."""
    x = x - x.mean()
    c0 = np.dot(x, x) / len(x)
    return np.array([np.dot(x[:len(x) - k], x[k:]) / len(x) / c0 for k in range(maxlag + 1)])


def first_lag(r, thr):
    """First lag where r <= thr, linearly interpolated between lags (None if never)."""
    for k in range(1, len(r)):
        if r[k] <= thr:
            return k - 1 + (r[k - 1] - thr) / (r[k - 1] - r[k])
    return None


def run_lengths(mask):
    runs, n = [], 0
    for m in mask:
        if m:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    return runs


# ------------------------------------------------------------- methods ----

def acf_methods(x):
    n = len(x)
    r = acf(x, n - 1)
    sig = 1.96 / np.sqrt(n)
    out = {'acf': r, 'sig_thr': sig, 'rho1': r[1]}
    out['efold'] = first_lag(r, 1 / np.e)
    out['zero'] = first_lag(r, 0.0)
    out['sig'] = first_lag(r, sig)
    out['integral'] = None
    if out['zero'] is not None:
        k0 = int(np.floor(out['zero']))
        out['integral'] = np.trapezoid(r[:k0 + 1]) + 0.5 * r[k0] * (out['zero'] - k0)
    out['decorr'] = (1 + r[1]) / (1 - r[1])
    # Entin et al. (2000)-style slope of ln r over significant lags >= 2
    upper = out['sig'] if out['sig'] is not None else n - 1
    ks = np.array([k for k in range(2, n) if r[k] > sig and k < upper])
    out['entin_nlags'] = len(ks)
    out['entin'] = None
    if len(ks) >= 3:
        slope = np.polyfit(ks, np.log(r[ks]), 1)[0]
        out['entin'] = -1 / slope if slope < 0 else None
    return out


def apsm(x):
    sd = x.std()
    return {
        'above_mean': float(np.mean(run_lengths(x > 0))),
        'below_mean': float(np.mean(run_lengths(x < 0))),
        'above_half_sd': run_lengths(x > 0.5 * sd),
        'below_half_sd': run_lengths(x < -0.5 * sd),
    }


def drydowns(sm, pr, rain_thr=2.0, min_len=4):
    """Fit theta = theta_w + a*exp(-t/tau) to runs of decreasing SM with little rain."""
    n = len(sm)
    dec = np.diff(sm) < 0
    dry = np.ones(n, bool) if pr is None else pr < rain_thr
    segs, start = [], None
    for t in range(n - 1):
        ok = dec[t] and dry[t + 1]
        if ok and start is None:
            start = t
        if (not ok or t == n - 2) and start is not None:
            end = t + 1 if ok else t
            if end - start + 1 >= min_len:
                segs.append((start, end))
            start = None
    fits = []
    for s, e in segs:
        y = sm[s:e + 1]
        t = np.arange(len(y), dtype=float)
        f = lambda t, tw, a, tau: tw + a * np.exp(-t / tau)
        try:
            p, _ = optimize.curve_fit(f, t, y, p0=[y.min() - 0.01, y[0] - y.min() + 0.01, 3.0],
                                      bounds=([0, 0, 0.1], [y.min(), 1, 100]), maxfev=20000)
        except RuntimeError:
            continue
        r2 = 1 - np.sum((y - f(t, *p)) ** 2) / np.sum((y - y.mean()) ** 2)
        fits.append({'start': s, 'end': e, 'theta_w': p[0], 'a': p[1], 'tau': p[2], 'r2': r2})
    return fits


# -------------------------------------------------------------- output ----

def fmt(v, nd=2):
    return '' if v is None else f'{v:.{nd}f}'


def build_rows(sm, pr, info):
    n = len(sm)
    res = {p: acf_methods(preprocess(sm, p)) for p in PREPS}
    ap = {p: apsm(preprocess(sm, p)) for p in PREPS}
    dd = drydowns(sm, pr)
    dates = info['dates']
    short = f'{n}일 자료'

    def acf_row(name, key, note):
        return [name, fmt(res[PREPS[0]][key]), fmt(res[PREPS[1]][key]), note]

    rows = [
        acf_row('e-folding lag', 'efold',
                f'낮음: {short}의 ACF는 음의 편향(≈ −(1+4ρ)/N)이 커서 과소추정 가능'),
        acf_row('Zero-crossing lag', 'zero', '낮음: ACF 꼬리 잡음과 시계열의 비정상성에 민감'),
        acf_row('Significance-threshold lag', 'sig',
                f'낮음: 95% 기준선 1.96/√{n} = {res[PREPS[0]]["sig_thr"]:.3f}, 표본 수에 의존'),
        acf_row('Integral timescale', 'integral', '낮음: 첫 0 교차까지 사다리꼴 적분, 적분 구간·추세 제거에 민감'),
        [ 'Decorrelation time', fmt(res[PREPS[0]]['decorr']), fmt(res[PREPS[1]]['decorr']),
          f'낮음~중간: lag-1만 사용 (ρ₁ = {res[PREPS[0]]["rho1"]:.3f} / {res[PREPS[1]]["rho1"]:.3f}), AR(1)이면 ≈ 2τ'],
    ]
    if res[PREPS[0]]['entin'] is None:
        rows.append(['Two-timescale (Entin et al., 2000)', '계산 불가', '계산 불가',
                     f'lag ≥ 2인 유의 상관 {res[PREPS[0]]["entin_nlags"]}개뿐, 수개월 lag 필요'])
    else:
        rows.append(acf_row('Two-timescale (Entin et al., 2000)', 'entin', '낮음: 수개월 lag 필요'))
    nyears = len({d[:4] for d in dates})
    rows.append(['Interannual autocorrelation (Koster & Suarez, 2001)', '적용 불가', '적용 불가',
                 f'≥ 5년(권장 ≥ 20년) 필요, 자료 {nyears}년'])
    if dd:
        med = np.median([f['tau'] for f in dd])
        segs = '; '.join(f'{dates[f["start"]][5:]}~{dates[f["end"]][5:]} τ={f["tau"]:.2f} θ_w={f["theta_w"]:.3f} R²={f["r2"]:.3f}'
                         for f in dd)
        rows.append(['Drydown (SMD) fitting', f'{med:.2f} (중앙값, {len(dd)}구간)', '해당 없음 (원자료 사용)',
                     f'중간: 구간 수 적음 [{segs}]'])
    else:
        rows.append(['Drydown (SMD) fitting', '계산 불가', '해당 없음', 'drydown 구간 없음'])
    nrain = '?' if pr is None else int((pr >= 1).sum())
    rows.append(['Hybrid stochastic-deterministic (McColl et al., 2019)', '계산 안 함', '해당 없음',
                 f'강수일(≥1 mm) {nrain}일, 강수 발생 통계·t^L 추정에 부족'])
    a0, a1 = ap[PREPS[0]], ap[PREPS[1]]
    rows.append(['APSM', f'평균보다 높음 {a0["above_mean"]:.1f} / 낮음 {a0["below_mean"]:.1f}',
                 f'평균보다 높음 {a1["above_mean"]:.1f} / 낮음 {a1["below_mean"]:.1f}',
                 f'낮음: 기준값에 민감. ±0.5σ 지속기간 높음 {a0["above_half_sd"]}/{a1["above_half_sd"]}, '
                 f'낮음 {a0["below_half_sd"]}/{a1["below_half_sd"]}'])
    return rows, res


def write_outputs(outdir, tag, sm, pr, info, rows, res, args):
    os.makedirs(outdir, exist_ok=True)
    header = ['method', f't_SMM_days ({PREPS[0]})', f't_SMM_days ({PREPS[1]})', 'reliability_note']

    csv_path = os.path.join(outdir, f'tsmm_{tag}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    series_path = os.path.join(outdir, f'series_{tag}.csv')
    with open(series_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['date', f'{args.var} ({info["units"]})', 'precip (mm/day)',
                    f'acf lag k ({PREPS[0]})', f'acf lag k ({PREPS[1]})'])
        for k, d in enumerate(info['dates']):
            w.writerow([d, f'{sm[k]:.4f}', '' if pr is None else f'{pr[k]:.2f}',
                        f'{res[PREPS[0]]["acf"][k]:.4f}', f'{res[PREPS[1]]["acf"][k]:.4f}'])

    md_path = os.path.join(outdir, f'tsmm_{tag}.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f'# t_SMM 비교표: {args.var}, {info["dates"][0]} ~ {info["dates"][-1]}\n\n')
        f.write(f'- 입력: `{args.path}` (읽기 전용)\n')
        f.write(f'- 요청 지점: {args.lat}°N, {args.lon}°E\n')
        f.write(f'- 사용 격자: {info["lat"]:.2f}°N, {info["lon"]:.2f}°E (요청 지점에서 {info["dist_km"]:.1f} km); '
                f'육지 판정은 sst NaN이고 {args.var}가 유효한 격자\n')
        f.write(f'- 단위: {info["units"]}, N = {len(sm)}, 평균 {sm.mean():.4f}\n\n')
        f.write('## 전처리\n\n')
        f.write(f'- **{PREP_LABELS[PREPS[0]]}**: 전체 기간 평균({sm.mean():.4f})을 뺌. '
                '기후값 기준 deseasonalization은 하지 않음.\n')
        f.write(f'- **{PREP_LABELS[PREPS[1]]}**: 날짜 번호에 최소제곱 직선을 맞추고 그 직선을 뺌.\n')
        f.write('- 자기상관은 분모가 N인 편향 추정량으로 lag 0 ~ N−1까지 구하고, '
                '기준선을 처음 넘는 lag는 이웃 lag 사이를 선형 보간함.\n')
        f.write(f'- Drydown fitting은 전처리하지 않은 원자료에 적용. '
                f'강수({args.pvar}, mm/일로 환산) < 2 mm/일이고 4일 이상 계속 감소한 구간 사용.\n')
        f.write('- APSM은 각 전처리 후 아노말리에 기준값 0과 ±0.5σ 적용.\n\n')
        f.write('## 결과 (단위: 일)\n\n')
        f.write(f'| 방법 | {PREP_LABELS[PREPS[0]]} | {PREP_LABELS[PREPS[1]]} | 신뢰도와 이유 |\n|---|---|---|---|\n')
        for r in rows:
            f.write('| ' + ' | '.join(str(c).replace('|', '/') for c in r) + ' |\n')
    return csv_path, md_path, series_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path')
    ap.add_argument('--lat', type=float, required=True)
    ap.add_argument('--lon', type=float, required=True)
    ap.add_argument('--var', default='swvl1')
    ap.add_argument('--pvar', default='mtpr', help='precipitation rate variable (kg m-2 s-1)')
    ap.add_argument('--outdir', default=DEFAULT_OUTDIR, help='default: <repo>/results')
    args = ap.parse_args()

    sm, pr, info = load_point(args.path, args.lat, args.lon, args.var, args.pvar)
    rows, res = build_rows(sm, pr, info)
    tag = f'{args.var}_{info["dates"][0][:7].replace("-", "")}_{info["lat"]:.2f}N_{info["lon"]:.2f}E'
    paths = write_outputs(args.outdir, tag, sm, pr, info, rows, res, args)

    print(f'grid {info["lat"]:.2f}N {info["lon"]:.2f}E ({info["dist_km"]:.1f} km), units {info["units"]}, N={len(sm)}')
    for r in rows:
        print(' | '.join(str(c) for c in r))
    print('\nwritten:', *paths, sep='\n  ')


if __name__ == '__main__':
    main()
