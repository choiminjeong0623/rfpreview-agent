## 1. 공통 부품

- [x] 1.1 `ui/Toasts.tsx`·`toastContext.ts`: `done(text, link?)` 동작 결과 알림(아래 가운데 하나, 4초, 바꿔 끼움), `ui.css` 모양·행동 줄 피하기, 부품 견본에 단추

## 2. 화면

- [x] 2.1 동작 결과를 `done`으로: 위험 조건 탭, 판정 상세, 판정 탭, 모두 확정, 상신 취소, 홈 다시 시도, 협조 요청, 데이터시트, 채점, 분석 실패. 오류는 `show(…, 'error')`
- [x] 2.2 e2e: Scenario "동작 결과는 아래 가운데", 기존 알림 위치를 보던 테스트 고침

## 3. 마무리

- [x] 3.1 검사(lint·check:api·build·openspec validate), 화면 확인
- [x] 3.2 archive, AGENTS.md 표, `npm run sync-main`
