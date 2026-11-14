## ADDED Requirements

### Requirement: PDF 올리기
화면은 검토 등록과 문서 추가에서 docx와 함께 PDF 파일도 고를 수 있어야 하고, 서버에 둔 RFP 목록에 PDF도 보여야 한다(SHALL). docx·PDF가 아닌 파일은 거절 안내를 보인다. [제안 11-02]

#### Scenario: PDF로 검토 등록
- **WHEN** 엔지니어가 검토 등록에서 글자가 든 PDF 사양서를 올리고 분석을 시작하면
- **THEN** 분류 추천에 그 PDF가 보이고, 분석이 끝나 담당자 확인 단계가 된다
