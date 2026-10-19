# t<sub>SMM</sub> 배경, 용어, 방법 정의

SKILL.md의 작업 순서에서 참고하는 자료입니다. 연구 전체 계획은 저장소 `README.md`를 따릅니다.

## 1. 배경

- 토양수분 기억(soil moisture memory, SMM)은 토양수분 아노말리가 몇 주에서 몇 달까지 지속되는 성질입니다.
  가뭄·폭염 예측, 지면-대기 결합 해석, 계절 예측의 기초가 됩니다.
- SMM의 크기는 시간규모 t<sub>SMM</sub>(단위: 일)으로 나타냅니다. 같은 자료라도 계산 방법에 따라 값이 크게 다릅니다.
- Rahmati et al. (2024, *Reviews of Geophysics*, 62, e2023RG000828)은 여러 지표를 체계적으로 비교한 연구가
  McColl, Alemohammad, et al. (2017) 하나뿐이라고 지적했습니다. 또한 전처리(deseasonalization·detrending),
  sampling frequency, 자료원, 측정 깊이에 따라 t<sub>SMM</sub>이 달라진다고 보고했습니다.

## 2. 용어

| 용어 | 뜻 |
|---|---|
| swvl1 | ERA5/ERA5-Land의 1층(0–7 cm) 체적 토양수분. 단위 m³ m⁻³ (파일 표기 `m**3 m**-3`) |
| mtpr | Mean total precipitation rate. 단위 kg m⁻² s⁻¹이며 86400을 곱하면 mm/일 |
| 아노말리 | 기준값(평균, 추세, 기후값)을 뺀 값 |
| deseasonalization | day-of-year나 월별 기후값을 빼서 계절 주기를 없애는 것. 여러 해 자료가 필요합니다 |
| ACF, r(τ) | lag τ일의 자기상관. 이 스킬에서는 분모가 N인 편향 추정량을 씁니다 |
| ρ₁ | lag-1 자기상관 |
| drydown | 강수가 없을 때 토양수분이 계속 줄어드는 구간 |
| θ_w | drydown 지수 모형의 하한(잔류 수분) |
| AR(1) | 1차 자기회귀(red noise) 과정. r(τ) = ρ₁^τ |

## 3. 방법 정의와 이 스킬의 구현

| 방법 | 정의 | 이 스킬의 구현 | 자료 요구조건 |
|---|---|---|---|
| e-folding lag | r(τ) ≤ 1/e가 되는 첫 lag | 이웃 lag 사이 선형 보간 | 규칙적인 시계열 |
| Zero-crossing lag | r(τ) ≤ 0이 되는 첫 lag | 선형 보간 | 규칙적인 시계열 |
| Significance-threshold lag | r(τ)가 95% 기준선 아래로 내려가는 첫 lag | 기준선 1.96/√N, 선형 보간 | 규칙적인 시계열 |
| Integral timescale | ∫ r(τ) dτ | 첫 0 교차(보간 위치)까지 사다리꼴 적분 | 규칙적인 시계열 |
| Decorrelation time | (1+ρ₁)/(1−ρ₁) | 그대로 계산. AR(1)이면 e-folding의 약 2배 | 규칙적인 시계열 |
| Two-timescale (Entin et al., 2000) | ln r(τ) 기울기로 긴(대기) 시간규모 추정 | lag ≥ 2이고 기준선보다 큰 lag가 3개 이상일 때만 기울기를 맞춤. 아니면 "계산 불가" | 일자료, 몇 달 lag |
| Interannual autocorrelation (Koster & Suarez, 2001) | 해를 건너 유의한 상관이 남는 가장 긴 lag | 월 1개 입력에서는 항상 "적용 불가" | ≥ 5년(권장 ≥ 20년) |
| Drydown (SMD) fitting | drydown마다 지수 모형을 맞춘 τ의 중앙값 | 강수 < 2 mm/일이고 4일 이상 계속 감소한 구간에 θ = θ_w + a·e^(−t/τ)를 맞춤. 원자료(전처리 없음) 사용 | 일자료 이상, m³ m⁻³ |
| Hybrid stochastic-deterministic (McColl et al., 2019) | 단기(t<sup>S</sup>)와 장기(t<sup>L</sup>) 기억을 분리 | 계산하지 않음. 정의를 원문으로 확인하기 전에는 추측으로 만들지 않습니다 | 토양수분 + 강수 |
| APSM | 기준값보다 높거나 낮은 상태가 이어지는 기간 | 아노말리에 기준 0(평균 지속기간)과 ±0.5σ(각 사건 길이) 적용 | 토양수분 + 기준값 |

## 4. 한 달(약 30일) 자료의 한계

- ACF 표본 편향: 대략 −(1+4ρ)/N입니다. N = 30이면 약 −0.1 ~ −0.15라서 ACF 기반 t<sub>SMM</sub>이 과소추정되기 쉽습니다.
- 95% 기준선 1.96/√30 = 0.358이 1/e = 0.368과 거의 같아서 significance-threshold lag ≈ e-folding lag가 됩니다.
  이는 우연이지 두 방법이 같은 것을 재는 게 아닙니다.
- deseasonalization을 할 수 없어 "월평균 제거"는 기후값 기준 아노말리가 아닙니다.
- 장마 시작처럼 한 달 안에 마르다가 다시 젖는 모양이 있으면 선형 추세 제거로는 비정상성이 거의 줄지 않습니다.
- drydown 구간과 APSM 사건이 몇 개뿐이라 중앙값·평균이 불안정합니다.

## 5. 입력 자료 관련 주의

- `/land1/ERA5/daily/land/*_land.nc`는 경로에 `land`가 있지만 0.25° 격자(1440×721)이고 `cape`, `cbh`, `sst`, `msl` 같은
  대기 변수가 들어 있습니다. ERA5-Land의 원래 해상도는 0.1°이므로 ERA5 단일 레벨 자료이거나 재격자화된 자료일 가능성이 높습니다.
  전역 속성이 비어 있어 파일 안에서는 출처를 확인할 수 없습니다.
- 이 파일에는 `lsm` 변수가 없습니다. 그래서 `sst`가 NaN이고 토양수분이 유효하며 0보다 큰 격자를 육지로 판정합니다.
  해안 혼합 격자(sst 값이 있으면서 swvl1이 작은 격자)는 이 기준으로 빠집니다.
- 경도는 0–360°로 저장되어 있습니다. 스크립트는 음수 경도를 받으면 자동으로 0–360°로 바꿉니다.

## 6. 참고문헌

- Rahmati, M., et al. (2024). Soil moisture memory: State-of-the-art and the way forward. *Reviews of Geophysics*, 62, e2023RG000828.
- McColl, K. A., Alemohammad, S. H., et al. (2017). The global distribution and dynamics of surface soil moisture. *Nature Geoscience*, 10(2), 100–104.
- McColl, K. A., He, Q., Lu, H., & Entekhabi, D. (2019). Short-term and long-term surface soil moisture memory time scales are spatially anticorrelated at global scales. *Journal of Hydrometeorology*, 20(6), 1165–1182.
- Entin, J. K., et al. (2000). Temporal and spatial scales of observed soil moisture variations in the extratropics. *JGR*, 105(D9), 11865–11877.
- Koster, R. D., & Suarez, M. J. (2001). Soil moisture memory in climate models. *Journal of Hydrometeorology*, 2(6), 558–570.
