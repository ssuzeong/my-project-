---
name: smm-timescale-compare
description: ERA5 월별 일자료 한 달(/land1/ERA5/daily/land/YYYYMM_land.nc)과 위경도 1개 지점으로 토양수분 기억 시간규모(tSMM)를 10개 방법별(e-folding, zero-crossing, significance-threshold, integral, decorrelation time, Entin, interannual, drydown, hybrid, APSM)로 계산하고, 신뢰도가 포함된 비교표와 해석을 results/에 저장한다. "YYYYMM, 위도 X, 경도 Y로 tSMM 비교", "토양수분 메모리 길이를 방법별로 계산" 같은 요청에 쓴다. 여러 달·여러 해 자료, 여러 지점·지도, 합성 자료 실험, swvl1이 아닌 변수, 문헌 조사에는 쓰지 않는다.
---

# smm-timescale-compare

방법 정의, 신뢰도 규칙, 임의로 정한 기준값, 해석 점검 항목, 숫자 검증 코드는 `references/research.md`에 있다. 작업 전에 읽는다.

README §5 "반복 작업"(기준 계산 1번)만 다룬다. 장기 자료 분석과 합성 자료 실험(2–4번)은 범위 밖이다.

## 입력
- 분석 연월 `YYYYMM`, 위도, 경도 (각 1개)
- 자료 경로: `/land1/ERA5/daily/land/YYYYMM_land.nc`
- 변수: `swvl1`(0–7 cm, m³/m³)로 고정. 강수(`mtpr`)와 해양 격자 판별용 `sst`도 읽는다.

## 지켜야 할 규칙
0. 연월이나 위경도가 없으면 추정하지 말고 묻는다. 해당 연월 파일이 없으면 없음을 알리고 멈춘다.
1. 원본 nc 파일은 수정하지 않는다. 읽기 전용으로 열고, 실행 전후에 크기와 수정 시각(`stat -c '%s %Y'`)이 같은지 확인한다.
2. 계산은 고정 스크립트 `.claude/skills/smm-timescale-compare/scripts/compute_tsmm.py`로만 한다. 즉석에서 계산 코드를 새로 쓰지 않는다. 방법 정의는 references/research.md를 따른다.
3. 원문 식을 확인하지 못한 방법은 계산하지 않는다. 임의로 단순화한 식으로 값을 내지 않는다.
   - Hybrid(McColl et al., 2019)는 현재 표에 "계산 안 함"과 이유만 적는다.
   - 원문 식을 사용자가 제공하거나 확인한 뒤에만 구현한다.
4. 비교표는 10개 방법을 한 줄씩 보여 준다.
   - Entin과 Interannual은 별도 행으로 둔다.
   - 적용할 수 없는 방법(N/A)과 계산하지 않은 방법("계산 안 함")은 구분해서 표시한다.
   - 사용자에게 요약할 때도 행을 합치지 않는다.
5. 각 방법에 `신뢰도`와 `신뢰도 근거` 칸을 둔다.
   - 등급(높음/중간/낮음/-)은 스크립트에 고정한 규칙으로만 정한다. 즉석에서 판단하지 않는다.
   - 이 등급은 "그 달 자료 안에서 값이 얼마나 안정적인가"를 뜻하며, 기후학적 메모리의 정확도가 아니다.
6. 해석에 쓰는 숫자는 모두 스크립트가 계산한 값을 그대로 인용한다.
   - 근거는 "해석용 수치" 표의 D 키나 비교표 값으로 단다. 손으로 계산하거나 반올림을 바꾸지 않는다.
   - 필요한 숫자가 표에 없으면 스크립트의 `derived_quantities()`에 추가한 뒤 다시 실행한다.
7. 자료로 확인하지 않은 정성적 주장은 쓰지 않는다. 예를 들어 "장마 시작" 대신 계산된 연속 습윤 구간(D25 등)을 인용한다. 어느 방법이 맞다고 결론 내지 않는다.

## 작업 순서
1. **입력 확인.** 파일이 있는지 확인하고, 원본의 크기와 수정 시각을 기록한다.
   ```bash
   ls -la /land1/ERA5/daily/land/YYYYMM_land.nc
   stat -c '%s %Y' /land1/ERA5/daily/land/YYYYMM_land.nc
   ```
2. **스크립트 실행** (저장소 최상위에서):
   ```bash
   python .claude/skills/smm-timescale-compare/scripts/compute_tsmm.py YYYYMM LAT LON --outdir results
   ```
   출력: `results/tsmm_YYYYMM_<lat>N_<lon>E` 의 `.md`(보고서), `.csv`(비교표), `_derived.csv`(해석용 수치, D 키), `_timeseries.csv`(지점 시계열)
3. **출력 점검.**
   - 사용한 격자와 요청 지점의 거리를 본다. 위경도 각각 가장 가까운 0.25° 격자를 쓴다.
   - 그 격자가 육지인지 본다(보고서에 `land: yes, sst is NaN`). 해안 지점이면 주변 격자가 바다일 수 있으니 결과에 함께 적는다.
   - 비교표가 10행인지, 보고서 표의 열 개수가 맞는지 본다. 근거 문장의 `|` 문자는 Markdown 표를 깨므로 `abs(r)`처럼 쓴다.
4. **해석 작성.** 보고서 끝에 `## 해석` 절을 붙이고, 모든 숫자 뒤에 근거(D 키 또는 비교표 값)를 괄호로 단다. 다룰 항목은 references/research.md의 "해석 점검 항목"을 따르고, 결론에 한 달 자료의 한계(기후학적 메모리 길이로 쓰지 않음)를 적는다. 스크립트를 다시 실행하면 해석 절이 지워지므로 마지막 실행 뒤에 붙인다.
5. **숫자 검증.** references/research.md의 "숫자 검증 코드"로 해석의 숫자와 D 키가 출력에 있는지 확인한다.
6. **원본 확인.** 원본의 크기와 수정 시각이 1단계 기록과 같은지 본다.
7. **보고.** 다음 순서로 알린다.
   - 사용한 격자와 육지 여부
   - 10행 비교표 (값, 신뢰도, 근거 요약)
   - 해석의 핵심
   - 사용자가 확인해야 할 가정 (references/research.md의 "임의로 정한 기준값")
   - 원본 파일이 바뀌지 않았다는 확인
   - 생성 파일 경로

커밋은 사용자가 요청할 때만 한다.
