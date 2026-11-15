# Design: 읽지 못한 쪽 알림 (add-unread-pages)

## 1. 쪽 읽기 결과 (`pipeline/pdf_reader.py`, `pipeline/ocr.py`)

- `ocr.read(image) -> OcrResult(lines, dropped, dropped_conf)`: 지금의 `read_lines`가 버리던 줄(신뢰도 60 미만)의 수와 평균 신뢰도를 함께 돌려준다. `read_lines`는 `read(...).lines`.
- `ocr.unavailable_reason() -> "OCR_OFF" | "OCR_MISSING" | None`: 설정으로 끔이 먼저, 그다음 엔진 없음.
- `pdf_reader.read_pdf(path) -> (blocks, PageScan)`. `read_blocks`는 블록만 돌려준다(미리 보기·원문 줄 API는 그대로).
  - 쪽마다: 글자 층 줄이나 표가 있으면 **읽음**. 없으면 쪽 그림(`page.images`) 유무를 본다.
    - 그림 없음 → OCR이 쓸 수 있으면 지금처럼 쪽 전체를 OCR(벡터로 그린 글자 대비), 읽은 줄이 있으면 읽음, 없으면 **BLANK**. OCR을 쓸 수 없으면 BLANK.
    - 그림 있음 → OCR을 쓸 수 없으면 `OCR_OFF`/`OCR_MISSING`. 쓸 수 있으면 OCR, 남은 줄이 있으면 읽음, 버린 줄만 있으면 `OCR_LOW_CONF`, 아무 줄도 없으면 `OCR_EMPTY`.
  - `PageScan(page_count, pages_read, pages_blank, unread=[{page, reason, dropped, dropped_conf}])`. 쪽 순서대로, 같은 파일·같은 엔진 판이면 같다(CR-11).
- 글자 쪽 안의 큰 그림(`_ocr_region`)과 docx 그림(`docx_reader._figure_text`)도 같은 규칙으로 그림 블록에 `ocr_reason`을 붙인다(OCR이 남긴 줄이 있거나 글자층이 깔린 그림이면 None).

## 2. 저장 (마이그레이션 0041)

- `document`: `page_count INT`, `pages_read INT`, `pages_blank INT`, `unread_pages JSONB`(PDF만, docx는 NULL).
- `doc_figure.ocr_reason VARCHAR(16)` — CHECK 다섯 코드 중 BLANK 뺀 넷.
- `approval_rule`에 `AR-09` 줄.
- `document.needs_review`: `len(unread) * 2 >= page_count`이면 참(쪽 절반 이상).
- 모든 쪽을 읽지 못한 PDF는 블록 0개라 지금처럼 판독 불가로 저장되고, `unread_pages`도 남는다.
- 처리 재사용 열쇠의 코드 판(`code_version`)이 이 변경으로 바뀌므로 같은 파일도 한 번 새로 처리한다.

## 3. 문서 읽기 점검 (`pipeline/read_checks.py`)

- 종류 순서: **쪽** → 표 → 그림 → 단위 → 위치. 키 `G-{document_id}-{page}`.
- 쪽 줄 문장(이유별):
  - `OCR_LOW_CONF`: "스캔 쪽 · OCR 신뢰도가 낮아 읽지 못함" / 문제 "글자 n줄을 찾았지만 신뢰도(평균 c)가 기준보다 낮아 버렸습니다. 이 쪽의 요구사항은 결과에 없습니다."
  - `OCR_EMPTY`: "스캔 쪽 · 글자를 찾지 못함" / "그림만 있는 쪽(사진·도면일 수 있음)입니다."
  - `OCR_OFF`: "스캔 쪽 · OCR이 꺼져 있음", `OCR_MISSING`: "스캔 쪽 · OCR 엔진 없음".
  - 할 일 공통 "원문을 직접 확인".
- 판독 불가 문서 줄("문서를 읽지 않음")은 쪽 줄이 있으면 만들지 않는다(쪽 줄이 더 구체적).
- 그림 줄: `ocr_reason`이 있으면 문제 문장 앞에 이유("OCR 신뢰도가 낮아 그림 속 글자를 읽지 못했습니다." 등).

## 4. AR-09 (`pipeline/review.py`)

- `criteria`에 확인하지 않은 쪽 점검 줄 수가 1 이상이면 `Criterion("AR-09", "읽지 못한 쪽 n개 미확인")`. 상신은 막지 않는다. 확인함 표시·이력은 지금 `set_checked` 그대로.
- 화면 `components/approval.ts` CHECKS에 AR-09 줄.

## 5. 등록 화면 (`pipeline/preview.py`, `api/runs.py`)

- 미리 보기 응답에 `page_count`, `unread_pages`(수), `unread_reason`(가장 많은 이유). OCR을 쓸 수 없는데 읽지 못한 쪽이 있으면 화면이 "OCR이 꺼져 있어 n쪽을 읽지 못합니다"(엔진 없음이면 "OCR 엔진이 없어 …").
- 거절 문구: 판정 대상으로 고른 문서가 있는데 모두 읽지 못했으면 "판정할 문서를 읽지 못했습니다(이유)". 이유: 모든 쪽 OCR 실패 / OCR 꺼짐 / OCR 엔진 없음 / 열 수 없는 파일. 묶음 때문이면 지금 문구.

## 6. 문서 표

- `RunDocument`에 `page_count`, `pages_read`, `pages_blank`. 문서 표 칸 "읽은 쪽"에 `n / m`(docx는 "—").

## 대안

- **쪽 번호 빈틈으로 나중에 추측**: 블록 없는 쪽은 `page_starts`로도 알 수 있지만, 빈 쪽과 못 읽은 쪽을 구별할 수 없고 이유도 모른다. 읽는 자리에서 기록한다(명세서 ④).
- **못 읽은 쪽을 AI 이미지 읽기로 채우기**: 외부 전송(NFR-07)과 지어냄(CR-04) 때문에 하지 않는다.

## 위험

- 미리 보기도 OCR을 돌리므로 스캔 PDF는 미리 보기가 느리다(지금도 같음).
- 쪽 그림이 아주 작은 장식뿐인 빈 쪽은 OCR_EMPTY로 잡힐 수 있다. 그림 크기 문턱은 두지 않고 결과를 보며 정한다 [확인 필요].
