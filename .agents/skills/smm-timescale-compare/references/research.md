# smm-timescale-compare 참고: 방법 정의와 기준값

## 방법별 처리 요약 (스크립트 구현 기준)
- **전처리:** 한 달 자료라 계절주기를 제거할 수 없으므로 월평균만 뺀다(주 결과). 월 안의 선형 추세 제거는 민감도 열로 따로 낸다.
- **자기상관(ACF):** 편향 추정량을 쓰고, 교차 지점은 lag 사이를 선형 보간한다.
- **방법별:**

| # | 방법 | 구현 |
|---:|---|---|
| 1 | e-folding | 첫 r ≤ 1/e |
| 2 | Zero-crossing | 첫 r ≤ 0 |
| 3 | Significance-threshold | 첫 r < 1.96/√N |
| 4 | Integral | lag 0부터 첫 zero crossing까지 사다리꼴 적분 |
| 5 | Decorrelation | (1+ρ₁)/(1−ρ₁) |
| 6 | Entin | N/A (수개월 lag 필요) |
| 7 | Interannual | N/A (5년 이상 필요) |
| 8 | SMD | SM이 연속으로 감소한 구간(4점 이상, 이후 강수 < 5 mm/day)에 3-매개변수 지수함수(θw, Δθ, τ)를 맞추고 τ의 중앙값을 쓴다 |
| 9 | Hybrid | 계산 안 함 (SKILL.md 규칙 3) |
| 10 | APSM | 아노말리 부호가 같은 run의 평균 길이(임계값 0). 0.5σ·1σ 결과는 민감도로 함께 낸다 |

## 신뢰도 규칙 (스크립트에 고정)
- **ACF 계열(e-folding, Integral):** 값 ≤ N/4이고 선형 추세 제거 시 변화 < 10%이면 중간, 아니면 낮음. 계절주기를 제거할 수 없어 최고 등급은 '중간'이다.
- **Zero-crossing, 유의수준 lag:** 항상 낮음. 근거로 abs(r) < SE(r)인 lag 범위와, 임계값과 1/e의 차이를 적는다.
- **Decorrelation:** ρ₁로 계산한 AR(1) e-folding과 관측 e-folding의 차이가 < 25%이면 중간, 아니면 낮음.
- **SMD:** 기준(6점 이상, R² 0.95 이상)을 충족한 drydown이 3개 이상이면 높음, 1–2개면 중간, 0개면 낮음.
- **APSM:** 임계값 0/0.5/1σ 사이 변동이 < 30%이면 중간, 아니면 낮음.
- **값 없음(Entin, Interannual, Hybrid):** '-'로 표시하고 이유를 적는다.

## 임의로 정한 기준값 (사용자 확인 필요)
- 강수 관련: 습윤일 1 mm/day, drydown 최소 4점, drydown 중 강수 상한 5 mm/day
- 신뢰도 기준: N/4, 선형 추세 제거 시 변화 10%, AR(1)과의 차이 25%, APSM 변동 30%, 좋은 drydown 6점·R² 0.95
- 바꾸려면 스크립트 상수와 이 문서를 함께 고친다.

## 입력 변수
- `swvl1`: 0–7 cm 체적 토양수분 (m³/m³)
- `mtpr`: 강수율 (kg m⁻² s⁻¹ → mm/day로 환산)
- `sst`: 해양 격자 판별용 (NaN이면 육지)
- 격자: 0.25°, 위경도 각각 가장 가까운 격자를 쓴다.

## 해석 점검 항목
- 값이 나온 방법 수와 신뢰도 분포
- '중간' 방법들 사이의 차이와 원인 (정의 차이: 아노말리 ACF vs 물리적 감쇠)
- decorrelation time과 AR(1) 기대값의 비교
- 유의수준 lag와 e-folding이 겹치는지 (N=30이면 95% 임계값 ≈ 1/e)
- zero-crossing과 강수 이벤트의 관계
- APSM 임계값 민감도, SMD 맞춤 품질, 선형 추세 제거 민감도
- 결론: 한 달 자료이므로 방법 간 차이만 보여 주며, 기후학적 메모리 길이로 쓰지 않는다 (README §7).
- 해석은 마지막 실행 뒤에 붙인다. 스크립트를 다시 실행하면 해석 절이 지워진다.

## 숫자 검증
숫자 검증은 `scripts/check_result.py`가 한다(`interp` 항목). 해석의 숫자가 모두 스크립트 출력에 있는지, 인용한 D 키가 모두 `_derived.csv`에 있는지 확인한다. `(D15, D16, D17)`처럼 괄호 하나에 키를 여러 개 쓴 경우도 키마다 본다. 사용법과 재시도 규칙은 SKILL.md `## 검증`을 따른다.

이 검사는 숫자가 출력 어딘가에 있는지만 본다. 각 숫자가 괄호 속 키의 값과 같은지는 따로 대조한다(SKILL.md `## 서브에이전트`).

## 시험용 입력 (`--input`, 시험 전용)
`compute_tsmm.py --input PATH`는 원본 ERA5 대신 같은 변수(`swvl1`, `mtpr`, `sst`)를 가진 **시험용** nc를 읽는다. "일부러 틀린 입력"에 `check_result.py`가 걸리는지 확인할 때만 쓰고, 실제 분석에는 쓰지 않는다.
- `PATH`가 `/land1` 아래면 스크립트가 거부한다.
- `--outdir`이 저장소의 `results/`면 스크립트가 거부한다.
- 보고서 `File:` 줄에 `TEST INPUT (--input)`이 붙는다.
- 시험 파일은 저장소 밖 `~/compare/testdata/`에, 시험 결과는 `~/compare/testdata/out/`에 둔다. `/land1`과 저장소 안에는 만들지 않는다.
- 시험 파일을 만드는 스크립트는 자료와 섞이지 않게 `~/compare/make_test_nc.py`에 둔다.

**결측을 섞은 시험 파일 만들기.**
- 원본에서 지점 주변 ±1°만 읽기 전용으로 잘라 온다.
- 아래 스크립트를 `~/compare/make_test_nc.py`로 저장해 실행한다.
- 실행 전후에 원본의 `stat -c '%s %Y'`가 같은지 확인한다.

```python
# make_test_nc.py SRC OUTDIR LAT LON
import sys, numpy as np, xarray as xr
src, out, lat, lon = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
assert not out.startswith("/land1"), "test files must not go under /land1"
with xr.open_dataset(src) as ds:                       # original opened read-only
    sub = ds[["swvl1", "mtpr", "sst"]].sel(latitude=slice(lat + 1, lat - 1),
                                           longitude=slice(lon - 1, lon + 1)).load()
pt = dict(latitude=sub.latitude.sel(latitude=lat, method="nearest"),
          longitude=sub.longitude.sel(longitude=lon, method="nearest"))
sub.to_netcdf(f"{out}/clean.nc")                                   # 결측 없음
a = sub.copy(deep=True); a["mtpr"].loc[dict(time=a.time[[3, 4, 17]], **pt)] = np.nan
a.to_netcdf(f"{out}/precip_nan.nc")                                # 강수 3일 결측
sub.isel(time=[i for i in range(sub.sizes["time"]) if i != 14]).to_netcdf(f"{out}/dropday.nc")  # 15일째 빠짐
b = sub.copy(deep=True); b["swvl1"].loc[dict(time=b.time[[10]], **pt)] = np.nan
b.to_netcdf(f"{out}/swvl1_nan.nc")                                 # swvl1 1일 결측
```

```bash
T=~/compare/testdata
mkdir -p $T
python -I ~/compare/make_test_nc.py /land1/ERA5/daily/land/202306_land.nc $T 35.13 129.10
python .claude/skills/smm-timescale-compare/scripts/compute_tsmm.py 202306 35.13 129.10 --input $T/precip_nan.nc --outdir $T/out
python .claude/skills/smm-timescale-compare/scripts/check_result.py $T/out/tsmm_202306_35.13N_129.10E --expect-stat "$(stat -c '%s %Y' $T/precip_nan.nc)"
```

기대 결과 (202306, 35.13N 129.10E로 확인함):

| 시험 파일 | compute_tsmm.py | check_result.py |
|---|---|---|
| `clean.nc` | 종료 코드 0. CSV 3개가 원본으로 계산한 결과와 같음 | 해석이 없으면 `interp`만 걸림. 해석을 붙이면 `OK` |
| `precip_nan.nc` | 종료 코드 0 | `timeseries`: precip_mm_day 결측 3개 |
| `dropday.nc` | 종료 코드 0 | `timeseries`: 06/14→06/16 날짜 끊김, 29일 |
| `swvl1_nan.nc` | 종료 코드 1, swvl1 결측으로 계산 거부 | 출력 파일이 없어 실행하지 않음 |

비교표, 신뢰도, 해석, stat 항목은 결과 파일 사본을 고쳐서 시험한다. 예: CSV 한 행 지우기, 신뢰도를 `보통`으로 바꾸기, 해석에 출력에 없는 숫자나 `D99` 넣기, `--expect-stat`의 수정 시각을 1 늘리기.
