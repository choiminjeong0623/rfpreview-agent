## ADDED Requirements

### Requirement: OCR로 글자 읽기
시스템은 글자 층이 없는 PDF 쪽과 docx 그림을 로컬 OCR 엔진으로 읽어 단락으로 더하고 같은 단계로 처리해야 한다(SHALL). OCR 줄에서 나온 요구사항은 추출 방법 "OCR"과 낮은 신뢰도로 저장하고 그 문서는 확인 필요로 둔다. 글자 신뢰도가 기준보다 낮은 줄은 버린다(CR-04). AI는 쓰지 않는다(CR-01). 엔진이 없거나 꺼져 있으면 OCR 없이 처리한다(스캔 PDF는 판독 불가). [제안 11-02]

#### Scenario: 스캔한 PDF 사양서
- **WHEN** 글자 층 없이 "The switchgear shall be rated 145 kV." 등 요구 문장 그림만 든 PDF를 OCR 엔진과 함께 처리하면
- **THEN** 판독 가능으로 저장되고 그 문장이 추출 방법 OCR 요구사항으로 원문 위치와 함께 나오며 문서는 확인 필요다

#### Scenario: docx 그림 속 문장
- **WHEN** 본문 사이에 요구 문장이 그려진 그림이 있는 docx를 처리하면
- **THEN** 그림 위치가 저장되고 그 문장이 추출 방법 OCR 요구사항으로 나온다

#### Scenario: OCR 엔진 없음
- **WHEN** OCR을 끈 상태로 같은 스캔 PDF를 처리하면
- **THEN** 판독 불가로 저장되고 요구사항이 없다

## MODIFIED Requirements

### Requirement: 문서 분류
시스템은 docx 파일마다 파일 번호, 묶음(A/B/C/D), 문서 종류, 사업 ID, 언어, 주 규격 체계, 판정 대상 여부를 정해야 한다(SHALL). 파일명·첫 장 표현으로 코드가 1차 판별하고 AI는 보조하며, 둘이 다르면 "확인 필요"로 표시해야 한다(SHALL). 문서 종류를 정하는 파일명·첫 장 표현은 적재된 문서 종류 규칙 사전을 순서대로 쓴다(SHALL). 판정 대상은 묶음 A·B뿐이다(CR-09). 글자를 읽을 수 있는지는 OCR로 읽은 단락까지 세어 정한다. [OCR: 제안 11-02]

#### Scenario: 입찰 서식
- **WHEN** 파일 1(RFP01 Bidding Forms)을 분류하면
- **THEN** 묶음 A, 입찰 서식, 판정 대상, 주 규격 체계 IEC이다

#### Scenario: 판정 대상이 아닌 미국 사양서
- **WHEN** 파일 13(RFP13 Medium-Voltage Switchgear)을 분류하면
- **THEN** 묶음 C, 요구 사양, 판정 대상 아님, 주 규격 체계 IEEE·UL이다

#### Scenario: 이미지만 있는 문서
- **WHEN** 쪽이 그림으로만 든 파일 8을 OCR 엔진 없이 분류하면
- **THEN** "판독 불가"로 두고 이후 단계를 건너뛴다

#### Scenario: OCR로 읽은 이미지 문서
- **WHEN** 같은 파일 8을 OCR 엔진과 함께 처리하면
- **THEN** 판독 가능이고 요구사항이 추출 방법 OCR로 나오며 문서는 확인 필요다

#### Scenario: 사전 순서대로 문서 종류 정하기
- **WHEN** 파일 이름이 "Testing Specification"인 문서를 분류하면
- **THEN** 사전에서 먼저 맞는 시험 사양서 줄(파일 이름 "testing")이 이겨 문서 종류는 시험 사양서다

#### Scenario: 사전에 없는 표현
- **WHEN** 파일 이름과 첫 장 어디에도 사전 표현이 없는 문서를 분류하면
- **THEN** 문서 종류는 "종류 모름"이고 "확인 필요"다

### Requirement: 그림 위치 기록
시스템은 문서를 나눌 때 그림(그림 개체가 든 단락)이 있는 줄 번호와 그림 설명(바로 앞이나 뒤 단락이 "Fig."·"Figure"·"그림"으로 시작하면 그 문장)을 저장해야 한다(SHALL). 그림 속 글자는 OCR 엔진이 있을 때 OCR로 읽어 더하고(OCR로 글자 읽기), 그림 단락 자체는 요구사항이 아니다. 도면 기호·연결의 뜻은 읽지 않는다. [OCR: 제안 11-02]

#### Scenario: 단선도 그림 위치
- **WHEN** 본문 사이에 그림 단락이 있고 다음 단락이 "Fig. 1 Single Line Diagram"인 문서를 나누면
- **THEN** 그림 1개가 그 줄 번호와 설명 "Fig. 1 Single Line Diagram"으로 저장되고, 그림 단락은 요구사항으로 뽑히지 않는다
