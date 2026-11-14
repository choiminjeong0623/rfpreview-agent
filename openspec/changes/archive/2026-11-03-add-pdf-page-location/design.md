## Context

원문 위치는 `source_location.line_start`(문서 처음부터 센 줄 번호)로 저장하고 `queries.LOCATIONS`가 파일 번호·절·표·행으로 돌려준다. PDF 줄 번호는 `pdf_reader`가 쪽을 넘어 이어 센다. 쪽 정보는 저장하지 않았다.

## Decisions

- **쪽 시작 줄 배열**: `document.page_starts INT[]` — i번째 값이 i쪽 첫 줄 번호. 위치마다 쪽 칸을 두지 않고 문서에 한 번만 둔다(위치를 만드는 곳이 여럿이어도 줄 번호만 있으면 된다).
- **줄 → 쪽**: SQL 함수 `line_page(starts, line)` = 시작 줄이 그 줄 이하인 가장 큰 쪽 번호. 빈 쪽(블록 없음)은 다음 쪽과 같은 시작 줄을 가져 다음 쪽이 골라진다. Python 쪽(문서 읽기 점검)은 같은 규칙의 `page_of`.
- **Block.page**: `pdf_reader`가 블록마다 쪽 번호(1부터)를 붙이고 `page_starts(blocks)`로 배열을 만든다. docx·txt는 None.
- **표시**: `파일 · n쪽 · 절 또는 표 · n행`. 쪽이 없으면(docx) 지금과 같다. 응답 `Location.page`는 없을 수 있는 칸.
- 버린 대안: `source_location.page` 칸 — 위치를 넣는 곳마다 쪽을 계산해 넣어야 하고, 문서 읽기 점검의 그림·표 줄에는 위치 행이 없다.

## Risks

- 이미 처리한 PDF는 다시 처리되기 전까지 쪽이 비어 있다(처리 코드 판이 바뀌어 다음 분석 때 다시 처리).
