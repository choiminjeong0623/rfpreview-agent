# Tasks

## 1. 백엔드 (최민정)

- [x] 1.1 `pipeline/queries.py` `run_list`에 가장 최근 상신의 결재 정보(design 1), 취소한 상신은 비움
- [x] 1.2 `api/schemas.py` `RunListItem`에 결재 칸 7개
- [x] 1.3 `cd frontend && npm run gen:api`
- [x] 1.4 테스트: Scenario "상신한 검토의 결재 정보", "취소한 상신", "반려된 검토"

## 2. 화면 (최민정)

- [x] 2.1 `views/ReviewList.tsx` 담당 범위 "내가 올린 결재", 단계 칩 셋과 개수, "결재" 칸
- [x] 2.2 요약 줄 "결재 대기 n" 누르면 단계 거름 바로 적용
- [x] 2.3 `views/Home.tsx` 결재 대기 칸 아래 "목록에서 보기" 링크(박경빈 님에게 알림)
- [x] 2.4 e2e: Scenario "내가 올린 결재 보기", "요약 줄로 결재 대기 거르기"

## 3. 문서·마무리

- [x] 3.1 `docs/screens/SCR-06-검토목록.md`, `SCR-06_공유.md`(목업에 없는 "내가 올린 결재")
- [x] 3.2 AGENTS.md 7장 검사, `openspec archive update-review-list-approval --yes`
