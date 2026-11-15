# Tasks

## 1. 쪽 읽기 결과

- [x] 1.1 `ocr.py`: `read`(남긴 줄·버린 줄 수·평균 신뢰도), `unavailable_reason`
- [x] 1.2 `pdf_reader.py`: `read_pdf` → (블록, PageScan), 쪽마다 읽음·빈 쪽·이유, 쪽 속 그림 `ocr_reason`
- [x] 1.3 `docx_reader.py`: 그림 블록 `ocr_reason`
- [x] 1.4 마이그레이션 `0041_unread_pages.sql`: document 쪽 칸, `doc_figure.ocr_reason`, AR-09
- [x] 1.5 `document.py`: 쪽 결과·그림 이유 저장, 절반 이상이면 확인 필요

## 2. 점검·결재

- [x] 2.1 `read_checks.py`: "쪽" 줄(이유별 문장), 판독 불가 줄과 겹치지 않게, 그림 줄 이유
- [x] 2.2 `review.py`: AR-09
- [x] 2.3 API: `RunDocument` 쪽 칸, `DocumentPreview` 쪽 칸, 거절 문구, `npm run gen:api`

## 3. 화면

- [x] 3.1 문서 읽기 점검 탭 "쪽" 종류와 안내 문장
- [x] 3.2 결재 상신 창 AR-09 줄
- [x] 3.3 문서 표 "읽은 쪽"
- [x] 3.4 등록 화면 읽지 못한 쪽 수·OCR 꺼짐 안내, 거절 문구

## 4. 테스트

- [x] 4.1 document-intake Scenario 8개 (합성 PDF: 글자 쪽·낮은 신뢰도 스캔 쪽·빈 쪽)
- [x] 4.2 review-workspace Scenario 4개, review-approval Scenario 2개
- [x] 4.3 기존 OCR·읽기 점검·등록 거절 테스트 그대로 통과
