## 1. PDF 읽기

- [x] 1.1 `Block.caption`, `find_figures`가 caption을 먼저 쓰기
- [x] 1.2 글자 쪽 큰 그림: 그림 블록 + 영역 OCR 단락
- [x] 1.3 도면 쪽 판별: 표·라벨 빼고 NOTE 줄만, 도면 그림 블록(번호·제목)
- [x] 1.4 돌아간 글자 빼기, "돌아간 글자 n자" 그림 블록

## 2. 시험

- [x] 2.1 `tests/test_pdf_drawings.py`: Scenario "글자 쪽에 박은 그림", "단선도 쪽", "돌아간 글자"
- [x] 2.2 기존 PDF·OCR 시험과 합성 도면 PDF로 다시 확인, 전체 검사
