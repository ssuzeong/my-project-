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

## 숫자 검증 코드
해석의 숫자가 모두 스크립트 출력에 있는지, 인용한 D 키가 모두 수치 CSV에 있는지 확인한다.

```python
import re, pandas as pd
md = open(MD).read(); body, interp = md.split("\n## 해석\n", 1)
src = set(re.findall(r'\d+(?:\.\d+)?', body))
bad = [x for x in re.findall(r'(?<![D§\w.])\d+(?:\.\d+)?', interp) if x not in src]
keys = set(pd.read_csv(DERIVED)["key"])
missing = [k for k in re.findall(r'\((D[\d.]+)\)', interp) if k not in keys]
assert not bad and not missing, (bad, missing)
```

이 검사는 숫자가 출력 어딘가에 있는지만 본다. 각 숫자가 괄호 속 키의 값과 같은지는 따로 대조한다.
