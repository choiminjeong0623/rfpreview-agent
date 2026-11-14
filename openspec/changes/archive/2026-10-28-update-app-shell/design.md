# Design

## Context

목업 v4.57은 한 HTML에 24개 화면이 있고, 화면마다 CSS 전체를 따로 갖는다. 모든 화면의 바깥 틀(왼쪽 메뉴 `aside.sb`, 머리글 `header.hd`, 본문 `.ws`)은 같다.
지금 프런트는 React 19 + Vite이고 라우터가 없다. `App.tsx` 한 파일에 사용자 고르기, 검토 시작, 실행 목록, 결과 탭이 모여 있다.

## Decisions

### 1. 목업 CSS를 그대로 쓴다
- 목업 Main 화면의 CSS를 `frontend/src/mockup/Main.css`로 그대로 옮겨 기본으로 불러오고, 마크업은 목업과 같은 클래스 이름을 쓴다.
- 대안: 디자인 토큰만 뽑아 새 CSS를 쓴다 → 목업과 픽셀 단위로 맞추기 어렵고, 목업이 바뀌면 다시 옮겨야 한다.
- 화면별 CSS가 Main과 다른 화면은 그 화면이 보일 때만 그 CSS를 붙인다(`_디자인.md` 1장). 이번 change에서는 Main만 쓴다.
- 예전 화면의 CSS(`index.css`)는 `.legacy` 아래로 가둬 목업 클래스(`.layout`, `.tabs`, `.card`)와 부딪치지 않게 한다.

### 2. 화면 주소는 `#/…`
- `window.location.hash`와 `hashchange`만 쓰는 작은 함수(`shell/router.ts`). 목업도 `#화면키`로 화면을 연다.
- 대안: react-router 추가 → 화면 20여 개의 단순한 주소에 비해 의존성이 크고, 정적 파일로 띄울 때 서버 설정(모든 경로 → index.html)이 필요하다.
- 주소 표는 `SCR-00-앱틀.md` 1·2장. 모르는 주소는 홈.

### 3. 사용자 고르기
- 로그인이 없으므로 머리글 사용자 칩을 누르면 사용자 목록 겹창이 열린다(목업은 로그인 화면으로 감). 고른 사용자 id는 `localStorage`(`s2w.user`)에 둔다.
- 사용자는 React context(`SessionProvider`, `useSession`)로 모든 화면에 준다. 예전 화면에 넘기던 `user` prop은 여기서 꺼내 그대로 넘긴다.

### 4. 머리글 검색과 알림
- 검색: 겹창을 처음 열 때 `GET /api/runs`를 한 번 불러 화면에서 거른다(실행 수십 개 규모). 검토 번호가 같거나 파일 이름에 검색어가 든 실행.
- 알림: API가 없어 목업의 알림 6건을 예시 데이터(`examples/header.ts`)로 보이고 "예시" 꼬리표를 붙인다. 읽음 표시는 화면 안에서만 바뀐다.

## Risks / Trade-offs

- 목업 CSS를 통째로 쓰므로 쓰지 않는 규칙도 함께 실린다(약 33 KB, gzip 8 KB) → 허용.
- 예전 화면은 새 틀 안에서 목업과 모양이 다르다 → 화면별 change에서 바로 바꾼다. `SCR-00_공유.md` 7번.
- Material Symbols를 Google Fonts에서 받으므로 인터넷이 없으면 아이콘 자리에 글자가 보인다 → 시연 환경은 인터넷이 있다. 필요하면 글꼴 파일을 `public/`에 둔다.
