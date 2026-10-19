# Soil Moisture Memory Timescale (t<sub>SMM</sub>) 산정 방법론 비교 연구

## 1. 연구 배경
토양수분 기억(soil moisture memory, SMM)은 토양수분 아노말리가 몇 주에서 몇 달까지 지속되는 성질이다.
이 지속성은 가뭄·폭염 예측, 지면-대기 결합(land-atmosphere coupling) 해석, 계절 예측의 기초가 된다.
SMM의 크기는 보통 시간규모(t<sub>SMM</sub>)로 표현하지만, t<sub>SMM</sub>을 계산하는 방법은 여러 가지이고
같은 자료에서도 방법에 따라 값이 크게 달라질 수 있다.

Rahmati et al. (2024)은 이러한 방법들을 정리하면서, 여러 지표를 체계적으로 비교한 연구가
사실상 McColl, Alemohammad, et al. (2017) 하나뿐(6개 지표)이라고 지적하고
전체 지표를 비교하는 후속 연구를 요구했다. 또한 전처리(deseasonalization·detrending),
sampling frequency, data source, measurement depth에 따라 t<sub>SMM</sub>이 달라진다고 보고했다.

- **기준 논문:** Rahmati et al. (2024), *Soil Moisture Memory: State-Of-The-Art and the Way Forward*, Reviews of Geophysics, 62, e2023RG000828

## 2. 연구 목적
같은 토양수분 시계열에 여러 t<sub>SMM</sub> 산정 방법을 적용해 값을 비교하고, 방법 간 차이가 어디서 오는지 분석한다.

**연구 질문**
1. 같은 자료에 서로 다른 방법을 적용하면 t<sub>SMM</sub>은 얼마나 달라지는가?
2. 그 차이는 방법의 정의·가정에서 오는가, 자료 특성(길이, 해상도, 잡음, 깊이)에서 오는가?
3. 자료 조건별로 어떤 방법이 참값에 가깝고 안정적인가?

## 3. 비교 대상 방법론

| Method | Definition | Key assumption / caveat | Data requirement |
|---|---|---|---|
| e-folding lag | first lag where r(τ) ≤ 1/e | red noise (AR(1)) | regular time series |
| Zero-crossing lag | first lag where r(τ) ≤ 0 | sensitive to noise in r(τ) tail | regular time series |
| Significance-threshold lag | first lag where r(τ) < 95% threshold | depends on sample size | regular time series |
| Integral timescale | ∫ r(τ) dτ | equal to variance spectrum method; sensitive to detrending | regular time series |
| Decorrelation time | (1+ρ₁)/(1−ρ₁) | uses lag-1 only; ≈ 2τ for AR(1) | regular time series |
| Two-timescale decomposition (Entin et al., 2000) | slope of ln r(τ) → atmospheric timescale | short surface + long atmospheric timescale | daily, multi-month lags |
| Interannual autocorrelation (Koster & Suarez, 2001) | largest lag with significant interannual correlation | needs many years | daily, ≥ 5 (ideally ≥ 20) years |
| Soil moisture drydown (SMD) fitting | median τ of exponential fits to drydowns | evapotranspiration-dominated drying | daily or finer, m³/m³ |
| Hybrid stochastic-deterministic model (McColl et al., 2019) | separate short-term (t^S) and long-term (t^L) memory | needs precipitation occurrence | SM + precipitation |
| Anomaly persistence of soil moisture (APSM) | duration above/below a threshold | depends on threshold choice | SM + threshold |

## 4. 자료
- **Synthetic time series (참값을 아는 자료):** AR(1) process (참 τ 지정), stochastic bucket model (참 drydown τ 지정), hybrid model simulation
- **실제 자료 (확정 예정):** 현장 관측(예: ISMN), 위성(예: SMAP L3/L4, ESA CCI), 재분석(예: ERA5-Land)
- **대상 지역 (확정 예정):** 예) 동아시아/한반도

## 5. 분석 방법
1. **기준 계산:** 각 자료에 모든 방법을 같은 전처리로 적용해 t<sub>SMM</sub> 비교표를 만든다.
   계산은 저장소의 스킬(`.agents/skills/smm-timescale-compare/`) 스크립트로 수행해 재현성을 확보한다.
2. **Synthetic benchmark:** 참값을 아는 합성 시계열에서 방법별 bias와 spread(반복 생성 시 표준편차)를 구한다.
3. **민감도 실험:** 합성 자료를 아래와 같이 변형해 방법별 t<sub>SMM</sub> 변화를 비교한다.
   - Record length: 5 / 10 / 20 / 30년
   - Sampling frequency: daily → 2–3 days(위성 재방문 주기) → monthly
   - Observation noise: white noise 추가(위성 random error 모사)
   - Preprocessing: deseasonalization 방식(day-of-year / monthly / none)
   - Missing data·structural breaks: 결측과 자료 단절 삽입
4. **실제 자료 비교:** 같은 지점에서 자료원(in situ / satellite / reanalysis)과 깊이에 따른 방법별 차이를 비교하고,
   민감도 실험 결과로 그 차이를 해석한다.
5. **평가 기준:** 합성 자료에서는 참값 대비 bias·spread, 실제 자료에서는 inter-metric consistency, inter-dataset consistency, lagged prediction skill.

## 6. 기대효과
- **방법론 가이드 제시:** 자료 조건(길이·해상도·잡음·깊이)별로 어떤 방법이 안정적인지 정리해, t<sub>SMM</sub> 산정 방법 선택의 근거를 제공한다.
- **선행연구 결과의 비교 가능성 향상:** 연구마다 다른 방법으로 보고된 t<sub>SMM</sub> 값을 서로 비교할 때 필요한 해석 기준(예: decorrelation time ≈ 2 × e-folding)을 제시한다.
- **자료원 간 차이 해석:** 위성·재분석·현장 관측 t<sub>SMM</sub> 차이 중 방법론과 자료 특성에서 오는 부분을 구분해, 모델·위성 평가 연구에 활용할 수 있다.
- **재현 가능한 분석 도구:** 방법별 계산 스크립트와 합성 benchmark 자료를 공개해 다른 지역·자료에도 같은 비교를 적용할 수 있게 한다.
- **응용 연구의 기초:** 신뢰할 수 있는 t<sub>SMM</sub> 산정은 가뭄·폭염 예측과 지면-대기 결합 연구의 입력 정보로 이어진다.

## 7. 한계
- 실제 토양수분에는 참 t<sub>SMM</sub>이 없으므로, 합성 자료에서의 결론이 실제 자료에 그대로 적용된다고 보장할 수 없다.
- 합성 자료의 생성 모델에 따라 유리한 방법이 달라질 수 있어, 여러 생성 모델을 함께 사용해야 한다.
- Hybrid model과 APSM은 강수 자료와 임계값 선택이 필요해 다른 방법과 조건을 맞추기 어렵다.

## 8. 저장소 구성
```
my-project/
├── README.md
├── test_inputs/                      # synthetic benchmark 자료
└── .agents/skills/smm-timescale-compare/
    ├── SKILL.md
    ├── references/research.md
    └── scripts/compute_tsmm.py
```

## 9. 주요 참고문헌
- Rahmati, M., et al. (2024). Soil moisture memory: State-of-the-art and the way forward. *Reviews of Geophysics*, 62, e2023RG000828.
- McColl, K. A., Alemohammad, S. H., et al. (2017). The global distribution and dynamics of surface soil moisture. *Nature Geoscience*, 10(2), 100–104.
- McColl, K. A., He, Q., Lu, H., & Entekhabi, D. (2019). Short-term and long-term surface soil moisture memory time scales are spatially anticorrelated at global scales. *Journal of Hydrometeorology*, 20(6), 1165–1182.
- Ghannam, K., et al. (2016). Persistence and memory timescales in root-zone soil moisture dynamics. *Water Resources Research*, 52(2), 1427–1445.
- Entin, J. K., et al. (2000). Temporal and spatial scales of observed soil moisture variations in the extratropics. *Journal of Geophysical Research*, 105(D9), 11865–11877.
- Koster, R. D., & Suarez, M. J. (2001). Soil moisture memory in climate models. *Journal of Hydrometeorology*, 2(6), 558–570.
