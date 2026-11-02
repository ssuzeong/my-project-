#!/usr/bin/env python3
"""Check one tSMM result set written by compute_tsmm.py (+ the 해석 section).

Usage:
    python .claude/skills/smm-timescale-compare/scripts/check_result.py STEM --expect-stat "SIZE MTIME"

    STEM         results/tsmm_YYYYMM_<lat>N_<lon>E  (without extension)
    --expect-stat  `stat -c '%s %Y'` of the source nc recorded BEFORE running compute_tsmm.py
                 (the source path is read from the report's "File:" line)

Checks:
    [table]       comparison table has 10 rows (CSV and Markdown), Entin/Interannual separate,
                  every Markdown row has 7 columns
    [reliability] grade in {높음, 중간, 낮음, -}; '-' only and always for rows without a value;
                  reason present and without '|'; N/A vs 계산 안 함 kept distinct; md grade == CSV grade
    [interp]      '## 해석' exists; every number in it appears in the script output above it;
                  every cited D key exists in _derived.csv
    [timeseries]  no missing values; daily dates consecutive, inside YYYYMM, covering the whole month;
                  row count == D03 (N)
    [source]      source nc size and mtime equal --expect-stat

Exit codes: 0 all checks passed, 1 at least one check failed (one 'FAIL [item] reason' line each),
            2 usage error or result file missing. Read-only: never modifies any file.
"""
import argparse
import calendar
import math
import os
import re
import sys

import pandas as pd

GRADES = {"높음", "중간", "낮음"}
MD_COLS = 7


def md_comparison_rows(md):
    lines = md.splitlines()
    try:
        i = next(k for k, l in enumerate(lines) if l.startswith("## Method comparison"))
    except StopIteration:
        return None
    rows = []
    for l in lines[i + 1:]:
        if not l.startswith("|"):
            if rows:
                break
            continue
        rows.append(l)
    # drop header and separator
    return [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows[2:]]


def check_table(csv, md_rows, fails):
    if len(csv) != 10:
        fails.append(("table", f"CSV 비교표가 {len(csv)}행이다 (10행이어야 함)"))
    names = list(csv["method"].astype(str))
    entin = [n for n in names if "Entin" in n]
    inter = [n for n in names if "Interannual" in n]
    if len(entin) != 1 or len(inter) != 1 or (entin and inter and entin[0] == inter[0]):
        fails.append(("table", f"Entin과 Interannual이 각각 별도 1행이 아니다 (Entin {len(entin)}행, Interannual {len(inter)}행)"))
    if md_rows is None:
        fails.append(("table", "보고서에 '## Method comparison' 표가 없다"))
        return
    if len(md_rows) != 10:
        fails.append(("table", f"보고서 비교표가 {len(md_rows)}행이다 (10행이어야 함)"))
    for k, r in enumerate(md_rows, 1):
        if len(r) != MD_COLS:
            fails.append(("table", f"보고서 비교표 {k}번째 행의 열이 {len(r)}개다 ({MD_COLS}개여야 함; 근거의 '|' 확인)"))


def check_reliability(csv, md_rows, fails):
    for k, row in enumerate(csv.itertuples(index=False), 1):
        m, v, g = str(row.method), row.tsmm_days, str(row.reliability).strip()
        why, note = row.reliability_reason, str(row.note)
        has_value = not (isinstance(v, float) and math.isnan(v))
        if g not in GRADES | {"-"}:
            fails.append(("reliability", f"{k}행 {m}: 신뢰도 '{g}'는 허용값(높음/중간/낮음/-)이 아니다"))
        elif has_value and g == "-":
            fails.append(("reliability", f"{k}행 {m}: 값이 있는데 신뢰도가 '-'다"))
        elif not has_value and g != "-":
            fails.append(("reliability", f"{k}행 {m}: 값이 없는데 신뢰도가 '{g}'다 ('-'여야 함)"))
        if not isinstance(why, str) or not why.strip():
            fails.append(("reliability", f"{k}행 {m}: 신뢰도 근거가 비어 있다"))
        elif "|" in why:
            fails.append(("reliability", f"{k}행 {m}: 신뢰도 근거에 '|'가 있어 Markdown 표가 깨진다 (abs(r)처럼 쓸 것)"))
        if not has_value and not (note.startswith("N/A") or note.startswith("계산 안 함")):
            fails.append(("reliability", f"{k}행 {m}: 값이 없는데 note가 'N/A' 또는 '계산 안 함'으로 시작하지 않는다"))
        if "Hybrid" in m and not note.startswith("계산 안 함"):
            fails.append(("reliability", f"{k}행 {m}: Hybrid는 '계산 안 함'이어야 한다 (규칙 3)"))
        if md_rows is not None and k <= len(md_rows) and len(md_rows[k - 1]) == MD_COLS:
            mr = md_rows[k - 1]
            if mr[4] != g:
                fails.append(("reliability", f"{k}행 {m}: 보고서 신뢰도 '{mr[4]}'와 CSV '{g}'가 다르다"))
            if not has_value:
                want = "계산 안 함" if note.startswith("계산 안 함") else "N/A"
                if mr[2] != want:
                    fails.append(("reliability", f"{k}행 {m}: 보고서 값 칸이 '{mr[2]}'다 ('{want}'여야 함; N/A와 계산 안 함 구분)"))


def check_interp(md, derived, fails):
    if "\n## 해석\n" not in md:
        fails.append(("interp", "보고서에 '## 해석' 절이 없다 (마지막 실행 뒤에 붙였는지 확인)"))
        return
    # same logic as references/research.md "숫자 검증 코드"
    body, interp = md.split("\n## 해석\n", 1)
    if not interp.strip():
        fails.append(("interp", "'## 해석' 절이 비어 있다"))
        return
    src = set(re.findall(r'\d+(?:\.\d+)?', body))
    bad = [x for x in re.findall(r'(?<![D§\w.])\d+(?:\.\d+)?', interp) if x not in src]
    keys = set(derived["key"].astype(str))
    missing = [k for k in re.findall(r'\((D[\d.]+)\)', interp) if k not in keys]
    # keys cited inside a list like "(D08, 2.7배; D09)" or "(D15, D16, D17)"
    for grp in re.findall(r'\(([^)]*)\)', interp):
        for k in re.findall(r'(?<![\w.])(D\d+(?:\.\d+)?)', grp):
            if k not in keys and k not in missing:
                missing.append(k)
    if bad:
        fails.append(("interp", f"해석의 숫자 {sorted(set(bad))}가 스크립트 출력에 없다"))
    if missing:
        fails.append(("interp", f"해석이 인용한 키 {sorted(set(missing))}가 _derived.csv에 없다"))


def check_timeseries(ts, ym, derived, fails):
    na = ts.isna().sum()
    na = na[na > 0]
    if len(na):
        fails.append(("timeseries", "결측값이 있다: " + ", ".join(f"{c} {n}개" for c, n in na.items())))
    try:
        d = pd.to_datetime(ts["date"])
    except Exception as e:  # noqa: BLE001
        fails.append(("timeseries", f"date 열을 날짜로 읽을 수 없다: {e}"))
        return
    if d.isna().any():
        fails.append(("timeseries", f"date 열에 빈 값이 {int(d.isna().sum())}개 있다"))
        d = d.dropna()
    gaps = d.diff().dropna()
    if (gaps != pd.Timedelta(days=1)).any():
        where = [f"{a:%m/%d}→{b:%m/%d}" for a, b, g in zip(d[:-1], d[1:], gaps) if g != pd.Timedelta(days=1)]
        fails.append(("timeseries", f"날짜가 하루 간격으로 이어지지 않는다: {', '.join(where)}"))
    y, m = int(ym[:4]), int(ym[4:])
    out = d[(d.dt.year != y) | (d.dt.month != m)]
    if len(out):
        fails.append(("timeseries", f"{ym} 밖의 날짜가 {len(out)}개 있다"))
    ndays = calendar.monthrange(y, m)[1]
    if len(ts) != ndays:
        fails.append(("timeseries", f"시계열이 {len(ts)}일이다 ({ym}은 {ndays}일; 빠진 날 확인)"))
    n = derived.loc[derived["key"] == "D03", "value"]
    if n.empty:
        fails.append(("timeseries", "_derived.csv에 D03(N)이 없다"))
    elif str(n.iloc[0]).strip() != str(len(ts)):
        fails.append(("timeseries", f"시계열 행 수 {len(ts)}가 D03(N)={n.iloc[0]}과 다르다"))


def check_source(md, expect, fails):
    m = re.search(r"File: `([^`]+)`", md)
    if not m:
        fails.append(("source", "보고서에서 원본 파일 경로(File: 줄)를 찾을 수 없다"))
        return
    path = m.group(1)
    try:
        exp_size, exp_mtime = (int(x) for x in expect.split())
    except ValueError:
        fails.append(("source", f"--expect-stat '{expect}' 형식이 'SIZE MTIME'이 아니다"))
        return
    if not os.path.exists(path):
        fails.append(("source", f"원본 {path}가 없다"))
        return
    st = os.stat(path)
    if st.st_size != exp_size:
        fails.append(("source", f"원본 {path} 크기가 바뀌었다: 기록 {exp_size} → 현재 {st.st_size}"))
    if int(st.st_mtime) != exp_mtime:
        fails.append(("source", f"원본 {path} 수정 시각이 바뀌었다: 기록 {exp_mtime} → 현재 {int(st.st_mtime)}"))


def main():
    ap = argparse.ArgumentParser(description="Check a tSMM result set; exit 1 with reasons if anything fails.")
    ap.add_argument("stem", help="results/tsmm_YYYYMM_<lat>N_<lon>E (no extension)")
    ap.add_argument("--expect-stat", required=True, help="\"SIZE MTIME\" of the source nc recorded before the run")
    a = ap.parse_args()

    stem = a.stem[:-3] if a.stem.endswith(".md") else a.stem
    ym_m = re.search(r"tsmm_(\d{6})_", os.path.basename(stem))
    if not ym_m:
        print(f"ERROR: '{stem}'에서 YYYYMM을 읽을 수 없다 (tsmm_YYYYMM_... 형식이어야 함)")
        return 2
    paths = {k: stem + s for k, s in
             (("md", ".md"), ("csv", ".csv"), ("derived", "_derived.csv"), ("ts", "_timeseries.csv"))}
    missing = [p for p in paths.values() if not os.path.exists(p)]
    if missing:
        print("ERROR: 결과 파일이 없다: " + ", ".join(missing))
        return 2

    md = open(paths["md"], encoding="utf-8").read()
    csv = pd.read_csv(paths["csv"])
    derived = pd.read_csv(paths["derived"], dtype=str)
    ts = pd.read_csv(paths["ts"])

    fails = []
    md_rows = md_comparison_rows(md)
    check_table(csv, md_rows, fails)
    check_reliability(csv, md_rows, fails)
    check_interp(md, derived, fails)
    check_timeseries(ts, ym_m.group(1), derived, fails)
    check_source(md, a.expect_stat, fails)

    for item, why in fails:
        print(f"FAIL [{item}] {why}")
    if fails:
        print(f"{len(fails)}개 문제 — {stem}")
        return 1
    print(f"OK — {stem}: table, reliability, interp, timeseries, source 모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
