# Tasks

## 1. 명세

- [x] 1.1 `docs/screens/_디자인.md` (목업 CSS 쓰는 법, 토큰, 공통 부품)
- [x] 1.2 `docs/screens/SCR-00-앱틀.md` (메뉴, 화면 주소, 동작, 수용 기준)
- [x] 1.3 `docs/screens/SCR-00_공유.md` (목업과 다르게 만든 것)

## 2. 구현

- [x] 2.1 목업 Main CSS(`src/mockup/Main.css`), Pretendard 글꼴·로고(`public/`), 아이콘 글꼴 링크(`index.html`)
- [x] 2.2 예전 화면 CSS를 `.legacy` 아래로 가두기
- [x] 2.3 화면 주소(`shell/router.ts`), 메뉴 정의(`shell/menu.ts`)
- [x] 2.4 사용자 context(`shell/session.tsx`, `shell/useSession.ts`)
- [x] 2.5 앱 틀(`shell/Shell.tsx`): 왼쪽 메뉴, 머리글, 검색, 알림(예시), 사용자 바꾸기
- [x] 2.6 `App.tsx`: 주소 → 화면. 예전 화면은 RFP 검토·협조 요청으로 옮기고 나머지는 "아직 만들지 않음" 안내

## 3. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 3.1 `e2e/shell.spec.ts`: 메뉴로 화면 이동 / 메뉴 접기 / 사용자 바꾸기 / 알림은 예시로 보인다
- [x] 3.2 `e2e/review.spec.ts`: 새 주소(`#/reviews`)와 사용자 칩으로 바꿈

## 4. 마무리

- [x] 4.1 `ruff`, `pytest`, `npm run lint`, `npm run build` 통과
- [x] 4.2 `openspec validate update-app-shell --strict` 통과 후 archive
