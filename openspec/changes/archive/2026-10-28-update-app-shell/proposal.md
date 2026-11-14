# Proposal

## Why

화면을 목업 v4.57과 같게 만들기로 했다(2026-10-28, 로드맵 1단계). 지금 화면은 위쪽 탭 몇 개와 왼쪽 실행 목록으로 된 한 장짜리라,
목업의 왼쪽 메뉴·머리글·화면 주소가 없다. 이 틀 없이 기능 화면을 하나씩 만들면 나중에 모두 다시 옮겨야 하므로 틀을 먼저 만든다.

관련: FR-10·11 화면(`review-workspace`), 화면 명세 `docs/screens/SCR-00-앱틀.md`, 디자인 기준 `docs/screens/_디자인.md`.

## What Changes

- 왼쪽 메뉴(홈, RFP 관리 5개, 지식 관리 4개, 팀 공유 4개, 설정)와 머리글(메뉴 접기, 위치, 검색, 도움말, 알림, 사용자)을 목업 그대로 만든다.
- 화면마다 주소(`#/reviews/3`처럼)를 둔다. 주소로 바로 열거나 새로 고쳐도 같은 화면이 열린다.
- 사용자 고르기를 머리글 오른쪽 사용자 칩으로 옮긴다. 고른 사용자와 메뉴 접기 상태는 브라우저에 기억한다.
- 머리글 검색은 검토(번호, 파일 이름)를 찾는다. 알림은 API가 없어 예시로 보인다.
- 목업 CSS와 글꼴(Pretendard), 아이콘 글꼴(Material Symbols)을 그대로 가져온다.
- 지금 화면(검토 시작·실행 목록·결과 탭, 내 할 일)은 새 틀 안의 "RFP 검토", "협조 요청"으로 옮기기만 한다. 아직 만들지 않은 화면은 안내만 보인다.

## Non-Goals

- 각 화면의 내용을 목업대로 바꾸는 것(SCR-06 이후 화면마다 따로 한다).
- 로그인, 알림 저장·발송, 요구사항·제품·입찰 찾기 API.

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
- `review-workspace`: 앱 틀(메뉴·화면 주소·사용자 고르기) 요구사항을 더한다.

## Impact

- 프런트만 바뀐다. API·DB 변경 없음.
- 의존성 추가 없음(화면 주소는 `hashchange`로 처리).
- 정적 파일: `frontend/public/fonts/PretendardVariable.woff2`(SIL OFL), `frontend/public/img/spec2win-white.png`(목업 로고).
- e2e: 검토 흐름 테스트가 새 주소와 사용자 칩을 쓴다. 틀 테스트(`e2e/shell.spec.ts`) 추가.
