# Proposal

## Why

목업 v4.96 협조 요청 화면(v4.88~v4.95)은 요청이 많아질 때 찾기 쉽게 **검색 영역**(사업·RFP 검토·회신·수신자·검색어, 조건 칩), **RFP별 묶어 보기**, 탭마다 건수, 회신 기한 표시, 회신 대기 줄의 **[재요청]**, **내보내기(엑셀)**를 더했다.
지금 화면은 부서 탭 하나씩만 불러 표로 보여 주고, 내보내기는 잠겨 있으며, 메일을 보낸 뒤 회신이 없으면 "다시 연락 필요"만 보일 뿐 다시 보낼 방법이 없다.
프런트 4단계 4번(`docs/screens/_v4.96_결정.md` 3장 `update-todo-search`, 4장 4번). 화면 명세 `docs/screens/SCR-13-협조요청.md` "v4.96 바뀐 점". minjeong 11-01 16:13 "승인받지 않고 클로드의 제안대로 진행".

## What Changes

- `GET /assignments`의 `role`을 생략하면 세 부서(견적·품질·영업) 요청을 모두 돌려준다. 탭 건수와 RFP별 보기에 쓴다.
- `POST /assignments/export` (`role`, `assignment_ids`): 화면에서 거른 요청을 엑셀(`협조요청_<부서>.xlsx`, 전부면 `협조요청_전체.xlsx`)로. 칸: No., 검토 번호, 검토 이름, 사업명, 수신 부서, 상태, 요구사항, 원문 위치, 팀 가정, 보낸 주소, 보낸 일시, 회신 기한, 회신 받음, 회신 요지.
- 재요청: `POST /runs/{id}/assignments/send`에 `resend: true`면 메일 보냄(회신 대기) 요청도 다시 보낸다(엔지니어만). 보낸 시각이 새로 바뀌어 회신 기한(보낸 날 + 3일)이 다시 3일 뒤가 되고 이력에 재요청으로 남는다. 자동으로는 한 번만 보내는 규칙은 그대로.
- 화면: 탭 이름 옆 건수, 검색 영역(사업 → RFP 검토 목록 좁힘, 회신 전체·회신 대기·회신 기한 지남·회신 받음, 수신자 = 부서 주소 (n)·미지정, 검색어), [초기화]·[검색], 걸린 조건 칩(누르면 그 조건만 풂)·"n건", 요약 줄 누르면 그 상태만, 상태 칸 아래 "회신 MM-DD HH:mm"·"회신 기한 MM-DD"(지나면 빨강), 보기 고르기 담당별·RFP별, RFP별 묶음(검토 번호·이름·사업명, 부서별 수, 회신 m / n 막대, 기한 지남 k 또는 협조 끝남, [이 검토에 요청] 예시 창), 표 5줄씩, 회신 대기·기한 지남 줄 [재요청](엔지니어), 내보내기 열림.

## Non-Goals

- 요청하기로 직접 요청 만들기(예시 창 그대로), 사람별 수신자(부서 주소만), AI 요약 상자(Q1: 검토 상세·홈만).
- 받은 메일 읽기. 회신은 지금처럼 엔지니어가 요지를 적는다.

## Impact

- 백엔드: `api/runs.py`(`/assignments` role 생략, `/assignments/export`, 보내기 `resend`), `pipeline/review.py`(`assignments_for` 여러 부서), `pipeline/handoff_mail.py`(재요청), `pipeline/assignment_export.py`(새). 마이그레이션 없음.
- 프런트: `views/Todo.tsx`, `mockup/TodoV496.css`(v4.96 규칙만), `components/Pager.tsx`(쪽 크기 고르기), `api.ts`.
- 명세: `review-workspace`(MODIFIED 협조 요청 현황 화면, ADDED 3), `role-assignment`(MODIFIED 협조 요청 메일 발송, ADDED 1).
