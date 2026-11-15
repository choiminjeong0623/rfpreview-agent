## MODIFIED Requirements

### Requirement: Langfuse로 호출 기록 보내기
시스템은 사람이 요청하면 검토 실행 하나의 AI 호출 기록을 OpenTelemetry 형식으로 Langfuse에 보내야 하며, 원문 없이 해시만 보내고, Langfuse 판으로 부른 호출에는 그 프롬프트 이름과 버전을 붙여야 한다(SHALL). Langfuse 기록을 켜면 검토 실행 작업(등록·다시 시도·문서 추가·단계부터 다시)이 끝날 때마다 AI 호출이 있으면 같은 내용을 저절로 보내고, 보낸 시각과 Langfuse 주소 또는 보내지 못한 이유를 남겨 실행 기록 상세의 AI 호출에 보여야 한다. 링크는 그 검토에서 가장 최근에 AI를 부른 실행의 trace를 가리키고, 화면용 Langfuse 주소를 따로 정하면 그 주소로 만든다. 보내지 못해도 검토 단계·결과는 바뀌지 않는다. 끄면 저절로 보내지 않는다. [제안]

#### Scenario: Langfuse로 호출 기록 보내기
- **WHEN** Langfuse 유형 판으로 처리한 검토 실행의 호출 기록을 보내면
- **THEN** 내려받기와 같은 OTLP 내용이 가고, 유형 호출에만 프롬프트 이름 rfp-type과 그 버전이 붙고 RFP 원문은 없다

#### Scenario: 분석이 끝나면 호출 기록을 저절로 보냄
- **WHEN** Langfuse 기록을 켜고 AI를 쓰는 검토를 등록해 담당자 확인까지 처리하면
- **THEN** 그 검토의 AI 호출 기록이 내려받기와 같은 내용으로 한 번 Langfuse로 가고, 실행 기록 상세 AI 호출에 보낸 시각과 Langfuse 링크가 보인다

#### Scenario: 호출 기록을 보내지 못해도 검토는 그대로
- **WHEN** Langfuse 기록을 켰는데 Langfuse에 닿지 못하는 상태로 검토를 처리하면
- **THEN** 검토는 담당자 확인에서 멈추고, 실행 기록 상세 AI 호출에 보내지 못한 이유가 중립색으로 보인다

#### Scenario: 끄면 저절로 보내지 않음
- **WHEN** Langfuse 기록이 꺼진 상태로 검토를 처리하면
- **THEN** Langfuse에 요청하지 않고 실행 기록 상세에 Langfuse 줄이 없다

#### Scenario: 다시 처리한 작업의 링크는 호출이 있는 trace
- **WHEN** Langfuse 기록을 켜고 AI로 분석한 검토를 AI를 부르지 않는 단계부터 다시 처리하면
- **THEN** 작업 끝에 다시 보내고, 링크는 처음 분석의 AI 호출이 든 trace를 가리킨다

#### Scenario: 화면용 주소로 링크
- **WHEN** 서버가 닿는 Langfuse 주소와 다른 화면용 주소를 정하고 검토를 처리하면
- **THEN** 실행 기록 상세의 Langfuse 링크는 화면용 주소로 시작한다
