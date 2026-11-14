# Tasks

## 1. 규칙·백엔드 (최민정)

- [x] 1.1 `data/seed/type_rules.csv`에 비용 영향 규칙 추가(우선순위 25, 영어·한국어). BOM·줄바꿈 그대로
- [x] 1.2 `pipeline/cost_conditions.py`: COST 유형 줄 모으기, 종류·부담·위험 표시, 같은 조건 묶기, 협조 요청 상태
- [x] 1.3 상업 영향: 손실 환산 가산액, 일탈 후보
- [x] 1.4 `api/schemas.py` 응답 모델, `api/runs.py` `GET /runs/{run_id}/cost-conditions`, `npm run gen:api`
- [x] 1.5 테스트: 각 Scenario (지체상금 규칙, 시험 입회 보조 유형, 종류 묶기, 원문 위치 없는 줄 빠짐, 부담 표시, 책임 한도 꼬리표, 값 원문 그대로, 손실 가산액 팀 가정, 일탈 영향, 묶음 C 문서 포함)

## 2. 화면·문서 (최민정)

- [x] 2.1 `views/detail/CommTab.tsx`: 실제 데이터, 종류 칩, 예시 띠 지우기, 빈 상태
- [x] 2.2 `DetailBody.tsx`: 실행 번호 넘기기
- [x] 2.3 `docs/screens/SCR-08-6-상업조건.md`·`SCR-08-6_공유.md` 고치기
- [x] 2.4 e2e: 상업 조건 탭에 비용 조건 줄과 원문 위치, 협조 요청 건수 기대값 확인
- [x] 2.5 판정 규칙 화면 담당(나송주 님)에게 규칙 추가 알림 (나송주 구역 스레드에서 직접 진행, PR 설명에 적음)
