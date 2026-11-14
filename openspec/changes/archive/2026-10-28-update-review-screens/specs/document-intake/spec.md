## ADDED Requirements

### Requirement: 그림 위치 기록
시스템은 문서를 나눌 때 그림(그림 개체가 든 단락)이 있는 줄 번호와 그림 설명(바로 앞이나 뒤 단락이 "Fig."·"Figure"·"그림"으로 시작하면 그 문장)을 저장해야 한다(SHALL). 그림 속 글자는 읽지 않는다(OCR 범위 밖).

#### Scenario: 단선도 그림 위치
- **WHEN** 본문 사이에 그림 단락이 있고 다음 단락이 "Fig. 1 Single Line Diagram"인 문서를 나누면
- **THEN** 그림 1개가 그 줄 번호와 설명 "Fig. 1 Single Line Diagram"으로 저장되고, 그림 단락은 요구사항으로 뽑히지 않는다
