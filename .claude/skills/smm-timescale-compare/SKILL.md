---
name: smm-timescale-compare
description: 토양수분 기억 시간규모(tSMM, soil moisture memory timescale)를 10개 방법(e-folding, zero-crossing, significance-threshold, integral, decorrelation time, Entin two-timescale, Koster-Suarez interannual, drydown fitting, McColl hybrid, APSM)으로 계산해 비교표를 만든다. 월 단위 일자료 netCDF 파일 1개와 위경도 1개 지점으로 토양수분 메모리 길이를 방법별로 비교하라는 요청에 쓴다. 여러 달·여러 해 자료, 여러 격자·지도, 합성 자료 실험, 토양수분이 아닌 변수, netCDF가 아닌 입력에는 쓰지 않는다.
---

# SMM timescale compare (월 일자료 1개 · 격자 1개)

방법 정의, 한 달 자료의 한계, 스크립트 세부 동작은 `references/research.md`에 있다. 계산 전에 읽는다.

## 규칙
1. 파일 경로, 위경도, 토양층(swvl1~4) 중 하나라도 없으면 추정하지 말고 질문한다. 기본값(swvl1)을 말없이 쓰지 않는다.
2. 입력이 한 달치 연속 일자료·격자 1개 범위를 벗어나면 스크립트를 고치지 말고 사용자에게 확인한다.
3. 원본 nc 파일은 수정하지 않는다. 결과는 저장소 최상위 `results/`에만 저장한다.
4. 보고하는 숫자는 스크립트 출력에서 그대로 가져온다. 직접 계산하지 않는다.
5. 적용 불가·신뢰도가 낮은 방법도 표에서 빼지 않고 이유를 적는다. 정의를 원문으로 확인하지 못한 방법은 공식을 지어내지 않고 "계산 안 함"으로 둔다.
6. 어느 방법이 맞다고 결론 내지 않는다. 방법 간 차이의 원인만 해석한다.

## 작업 순서
1. `ncdump -h <file.nc> | head -80`으로 토양수분 변수·단위, time 길이, 격자 간격을 확인한다. 자료 이름과 맞지 않는 점(예: ERA5-Land인데 0.25° 격자)이 있으면 보고에 적는다.
2. 저장소 최상위에서 실행한다.
   `python .claude/skills/smm-timescale-compare/scripts/compute_tsmm.py <file.nc> --lat <위도> --lon <경도> --var <토양층>`
3. 다음 순서로 보고한다.
   [입력 요약(격자 실제 위경도·요청 지점과의 거리·층·단위·기간·N) / 입력 자료 주의 / 전처리(한 것: 평균 제거·선형 추세 제거, 안 한 것: deseasonalization) / 비교표(방법 | 평균 제거 | 선형 추세 제거 | 신뢰도와 이유, 10개 모두) / 해석(방법 간 차이, 추세 제거 영향, 사용 가능 범위) / 결과 파일 경로]
