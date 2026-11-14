## ADDED Requirements

### Requirement: OCR 사용 가능 표시
시스템은 `/api/health`에서 OCR을 쓸 수 있는지(엔진이 있고 켜져 있음)와 엔진 판을 돌려줘야 한다(SHALL). [제안 11-02]

#### Scenario: OCR 상태
- **WHEN** OCR 엔진이 있고 켜진 상태와 끈 상태에서 상태를 조회하면
- **THEN** ocr_available은 각각 true·false이고, 켜진 상태에서는 엔진 판이 있다
