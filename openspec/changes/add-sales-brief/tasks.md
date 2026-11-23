## 1. 백엔드

- [ ] 1.1 `pipeline/sales_brief.py`: `sales_brief`(이미 있는 결과 모음, 일탈 10·질의 5 자르기, 원문 위치 없는 줄 뺌)
- [ ] 1.2 `sales_brief_docx`: Word 한 장(머리·숫자·표 3개·남은 일·바닥 안내)
- [ ] 1.3 `sales_handoff.build_package`: zip 첫 파일, 목록 파일·메일 본문 "먼저 볼 파일"
- [ ] 1.4 API `GET /runs/{id}/sales-brief`, `/sales-brief/docx`, `schemas.SalesBrief`, 처리 중·실패 409
- [ ] 1.5 pytest: Scenario "영업 요약 만들기", "일탈이 많으면 자름", "같은 입력 같은 요약", "처리 중 영업 요약 거절", "패키지 내려받기"

## 2. 화면

- [ ] 2.1 `npm run gen:api`, `api.salesBrief`·`downloadSalesBrief`
- [ ] 2.2 `ReviewHead` 내보내기 ▾ "영업 요약 (Word)"
- [ ] 2.3 `PackagePreview` 첫 탭 "영업 요약"
- [ ] 2.4 화면 문서 SCR-08·SCR-08-8에 줄, 테스트(vitest·e2e): "내보내기에서 영업 요약 받기", "미리 보기 첫 탭 영업 요약"

## 3. 마무리

- [ ] 3.1 검사(ruff·pytest·lint·test·check:api·check:trace·build), `openspec validate --strict`
- [ ] 3.2 archive, AGENTS.md 표, `npm run trace`, `npm run sync-main -- --push`
