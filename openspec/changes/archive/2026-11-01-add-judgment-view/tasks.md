## 1. 원문 줄 범위 API

- [x] 1.1 `pipeline/source_lines.py`: 분석과 같은 줄 번호로 파일 다시 읽기(캐시 8개), 파일이 없으면 DB 줄만(`partial`)
- [x] 1.2 `GET /runs/{id}/documents/{file_no}/lines` + `DocumentLines` 스키마, 범위 검사(400)·없는 파일(404)
- [x] 1.3 백엔드 테스트 `tests/test_judgment_view.py` (Scenario마다)

## 2. 판정 상세 화면 (SCR-08-12)

- [x] 2.1 `npm run gen:api`, `api.documentLines`
- [x] 2.2 `mockup/JudgeView.css`(v4.96 규칙만), `PageKey`
- [x] 2.3 `views/JudgeView.tsx`: 원문(위치 탭·앞뒤 줄·표 한 줄), 비교·판정 근거·출처·신뢰도, 질의 초안 꼬리표, 목록 문장, 보증값, 아래 줄, 판정 바꾸기 창, ↑↓·Esc
- [x] 2.4 `App.tsx` 경로·이동 경로, 판정 탭 줄 누르기 → 이 화면, 주소 거르기로 판정 탭 열기, `JudgmentDialog` 지움, 판정 규칙 `#/rules?q=`
- [x] 2.5 e2e `judgment-view.spec.ts`(Scenario마다), 판정 창을 쓰던 e2e 고침

## 3. 마무리

- [x] 3.1 SCR-08-12 "구현됨", `SCR-08-12_공유.md`(목업과 다른 곳), AGENTS.md 표
- [x] 3.2 검사 통과, archive
