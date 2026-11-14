# requirement-extraction Specification

## Purpose
요구사항 후보를 한 줄씩 뽑고 담당이 갈리는 유형을 붙여, 엔지니어가 문서를 처음부터 읽지 않고 필요한 사람이 자기 몫만 보게 한다 (FR-03, FR-04).

## Requirements

### Requirement: 요구사항 추출
시스템은 데이터시트 표의 행을 모두 요구사항 후보로 뽑고(요구값이 빈칸이어도), 문장은 정해진 표현("shall / must / required / 하여야 / 한다")으로 1차 후보를 뽑아야 한다(SHALL). AI는 절 단위로 후보를 다듬고 작성 규칙·설명 문장을 구분한다.

#### Scenario: 데이터시트 행
- **WHEN** 파일 1의 7459행 "Rated short-time withstand current, (1 sec.) / kA / 40"을 추출하면
- **THEN** 요구사항 1줄, 출처 = 표 칸, 원문 위치 = 파일 1 TS-115-GIS 16번이다

#### Scenario: 작성 규칙
- **WHEN** 파일 1의 7419행 "'comply' not allow to use in Warranted Data column"을 추출하면
- **THEN** 요구사항이 아니라 작성 규칙으로 표시된다

#### Scenario: 공급사 표시
- **WHEN** 파일 18(RFP18 Electric Distribution)의 공급사 C/D/E 칸을 추출하면
- **THEN** 표시는 요구사항 내용과 섞이지 않고 별도 칸에 저장된다

### Requirement: 유형 표시
시스템은 요구사항마다 주 유형 1개와 보조 유형 0개 이상(7종)을 붙이고 판단 근거(규칙 ID 또는 AI)를 남겨야 한다(SHALL). 유형 규칙표가 먼저이고, AI는 규칙에 안 걸린 줄만 판단한다. 규칙과 AI가 다르면 둘 다 표시하고, 어느 유형도 아니면 "미분류"로 둔다(SHALL).

#### Scenario: 시험
- **WHEN** "Type Test Report / Required"에 유형을 붙이면
- **THEN** 주 유형은 시험이다

#### Scenario: 제조사 자격
- **WHEN** "ISO 9001 or equivalent certificates / Required"에 유형을 붙이면
- **THEN** 주 유형은 제조사 자격이다

#### Scenario: 손실 환산 조항
- **WHEN** 파일 1의 손실 환산 조항(8238행)에 유형을 붙이면
- **THEN** 주 유형은 비용 영향, 보조 유형은 기술 성능이다

### Requirement: AI 유형 판단의 문맥
시스템은 유형 규칙에 안 걸린 요구사항을 AI에 물을 때 줄마다 그 줄이 속한 절 번호·제목, 표 이름, 표 안 구분 행 제목을 문맥으로 함께 줘야 한다(SHALL). 문맥이 없는 줄은 문장만 준다. 유형을 정하는 규칙과 판정은 바뀌지 않는다. [제안 11-01]

#### Scenario: 표 행에 표 이름과 절 제목
- **WHEN** 유형 규칙에 안 걸린 데이터시트 표 행을 AI에 물으면
- **THEN** 묻는 글의 그 줄에 표 이름과 그 표가 속한 절 제목이 함께 들어간다

#### Scenario: 문맥이 없는 줄
- **WHEN** 절·표에 속하지 않은 문장을 AI에 물으면
- **THEN** 그 줄은 문장만 들어간다

### Requirement: 사람이 유형 고치기
시스템은 기술 검토 엔지니어와 승인자가 요구사항의 주 유형을 사유와 함께 고치게 해야 한다(SHALL). 고친 유형은 판단 근거 "사람"으로 저장하고 이력에 이전·이후 유형을 남기며, 담당 전달 목록을 다시 만들어야 한다(SHALL). 다른 역할은 고칠 수 없다(MUST NOT). [제안 11-01, C3]

#### Scenario: 엔지니어가 유형 고치기
- **WHEN** 엔지니어가 미분류 요구사항의 주 유형을 시험으로 고치면
- **THEN** 그 요구사항의 주 유형은 시험, 근거는 사람이고 이력에 미분류 → 시험이 남으며 품질 담당 요청이 생긴다

#### Scenario: 다른 역할은 못 고침
- **WHEN** 견적 담당이 유형을 고치려 하면
- **THEN** 거절되고 유형은 그대로다

### Requirement: 사람 유형 예시
시스템은 유형 규칙에 안 걸린 요구사항을 AI에 물을 때 줄마다 다른 문서에서 사람이 고친 요구사항 가운데 문장 뜻이 가까운(코사인 0.80 이상) 것을 최대 2개 "사람이 고른 예"로 함께 줘야 한다(SHALL). 정답지에 든 문장과 같은 문서의 줄은 예시로 쓰지 않아야 한다(MUST NOT). 벡터를 받지 못하면 예시 없이 묻고 분석은 계속한다(SHALL). 쓴 예시 수는 실행 기록에 남긴다. [제안 11-01, C3]

#### Scenario: 가까운 사람 예시
- **WHEN** 다른 문서에서 사람이 시험으로 고친 줄과 뜻이 가까운 줄을 AI에 물으면
- **THEN** 묻는 글의 그 줄에 그 예시 문장과 시험이 함께 들어가고 실행 기록의 유형 예시 수는 1 이상이다

#### Scenario: 정답지 문장은 예시가 아님
- **WHEN** 사람이 고친 줄의 문장이 유형 정답지에 들어 있으면
- **THEN** 그 줄은 예시로 들어가지 않는다

#### Scenario: 먼 줄에는 예시 없음
- **WHEN** 사람이 고친 줄과 뜻이 먼(코사인 0.80 미만) 줄을 AI에 물으면
- **THEN** 그 줄에는 예시가 들어가지 않는다

#### Scenario: 벡터 실패
- **WHEN** 벡터 요청이 실패하면
- **THEN** 예시 없이 묻고 분석은 담당자 확인 단계까지 간다

### Requirement: AI 질문의 문서 종류 설명
시스템은 AI에 문장 구분과 유형을 물을 때 그 문서 처리기의 문서 종류 설명 한 줄을 질문 앞에 넣어야 한다(SHALL). 설명이 없는 처리기는 넣지 않는다. 답 형식과 검사는 같다. [제안 11-01, C1]

#### Scenario: 시험 사양서 유형 질문
- **WHEN** 시험 사양서의 규칙에 안 걸린 요구사항 유형을 AI에 물으면
- **THEN** 질문 첫머리에 시험 사양서 설명이 있다

### Requirement: 문서 종류별 추출 규칙
시스템은 처리기가 정한 종류별 추출 규칙을 공통 추출 규칙에 더해 써야 한다(SHALL). 공급사 사양서는 C/D/E 표시 줄이 하나라도 있으면 표의 조항 줄(15자 이상, 소문자 포함)을 표시가 없어도 공급사 답안 후보로 뽑고 표시가 없으면 비운다. 입찰 서식은 표 밖 문장 중 서식 작성 안내 표현이 든 문장을 작성 규칙으로 두되 위험 표현이 든 문장은 바꾸지 않는다. 다른 종류는 공통 규칙만 쓴다. 규칙은 코드로만 정한다(CR-01). [제안 11-02, C1]

#### Scenario: 표시 없는 답안 표 조항 줄
- **WHEN** C/D/E 표시 줄이 있는 공급사 사양서의 표에 shall도 표시도 없는 조항 줄 "Short circuit current rating: 200 kAIC."가 있으면
- **THEN** 그 줄은 공급사 답안 요구사항 후보이고 공급사 표시는 비어 있다

#### Scenario: 표시가 없는 공급사 사양서
- **WHEN** C/D/E 표시 줄이 하나도 없는 공급사 사양서를 처리하면
- **THEN** 표의 조항 줄을 공급사 답안 후보로 더하지 않는다

#### Scenario: 입찰 서식 작성 안내
- **WHEN** 입찰 서식의 표 밖 문장 "Each Bidder must fill out this form."을 처리하면
- **THEN** 그 문장은 작성 규칙이고, 같은 문장이 요구 사양서에 있으면 요구사항이다

#### Scenario: 위험 표현이 든 작성 안내
- **WHEN** 입찰 서식의 서식 작성 안내 문장에 위험 표현이 들어 있으면
- **THEN** 그 문장은 요구사항으로 남는다

### Requirement: AI 문장 구분에서 묻지 않는 문장
시스템은 AI로 요구사항 후보를 작성 규칙·설명과 구분할 때, 위험 표현이 든 문장과 협조 요청 유형(비용 영향·시험·제조사 자격처럼 담당이 견적·품질·영업인 유형) 규칙에 걸리는 문장은 AI에 묻지 않고 요구사항으로 두어야 한다(SHALL, CR-01). 그 밖의 문장은 AI 답을 따른다. 작성 규칙·설명으로 바뀌면 위험 조건 찾기와 부서 협조 요청에서 빠지기 때문이다. [제안 11-02]

#### Scenario: 협조 요청 유형 문장
- **WHEN** AI가 절의 문장을 모두 작성 규칙이라고 답하는 처리에서 "The evaluated price shall state the currency, price validity period and payment milestones for the complete scope of supply."를 처리하면
- **THEN** 그 문장은 AI에 묻지 않고 요구사항으로 남으며 주 유형은 비용 영향이다

#### Scenario: 유형 낱말이 없는 문장
- **WHEN** 같은 처리에서 위험 표현도 협조 요청 유형 낱말도 없는 "The Evaluation Committee shall score compliant proposals using the weight model below."를 처리하면
- **THEN** AI 답대로 작성 규칙이다

### Requirement: 의무 표현이 없는 요구 줄
시스템은 의무 표현("shall / must / required …")이 없어도 다음 줄을 요구사항 후보로 뽑아야 한다(SHALL, CR-01). 데이터시트가 아닌 표에서 한 칸이 상태 값("Mandatory", "Required", "필수")으로 2줄 이상 반복되면 그 값이 있는 줄(머리 줄은 빼고), 필수 제출물·제출 서류 절의 짧은 목록 줄(문서에 한 번만 나오는 줄), 위험 표현 사전에 걸리는 문장. [제안 11-02]

#### Scenario: 상태 칸이 있는 요구 표
- **WHEN** 머리 줄 "ID | Requirement | Required Bidder Response | Status"와 상태가 "Mandatory"인 줄 3개가 있는 표를 추출하면
- **THEN** 상태가 "Mandatory"인 3줄이 요구사항 후보이고 머리 줄은 후보가 아니다

#### Scenario: 제출물 목록 절
- **WHEN** 제목이 "2. Mandatory Proposal Submission"인 절의 목록 줄 "Manufacturer product datasheet and a complete bill of materials for every offered item."을 추출하면
- **THEN** 의무 표현이 없어도 요구사항 후보이다

#### Scenario: 머리말 반복 줄
- **WHEN** 제출 서류 절 안에 문서 곳곳에 반복되는 머리말 줄과 15자보다 짧은 쪽 번호 줄이 있으면
- **THEN** 그 줄들은 후보가 아니다

#### Scenario: 위험 표현 문장
- **WHEN** "No deviations from the technical requirements will be accepted after contract award."를 추출하면
- **THEN** 의무 표현이 없어도 요구사항 후보이고, 처리하면 포괄 조항 위험 조건 후보가 된다

### Requirement: 보강한 유형 규칙
시스템의 유형 규칙표는 번호 없는 규격 이름 표현("IEC/ANSI/UL standards", 다른 유형이 없을 때만 주 유형), 단가·가격 조건 표현("unit price", "commercial proposal", "단가"), 제조사 위임·생산 시설 표현("manufacturer authorization", "production facility"), 누설·부분 방전 표현("leakage", "partial discharge", "누설")을 각각 적용 규격·인증, 비용 영향, 제조사 자격, 기술 성능으로 붙여야 한다(SHALL, CR-01). [제안 11-03]

#### Scenario: 번호 없는 규격 이름
- **WHEN** "Applicable IEC/ANSI/UL standards, declarations, certificates, and test reports."에 유형을 붙이면
- **THEN** 주 유형은 적용 규격·인증이다

#### Scenario: 기술 성능 줄의 규격 이름
- **WHEN** "Rated terminal load / As per IEC standards"에 유형을 붙이면
- **THEN** 주 유형은 기술 성능이다

#### Scenario: 단가 조건
- **WHEN** "Commercial proposal showing unit price, quantity, delivery term, warranty, and validity period."에 유형을 붙이면
- **THEN** 주 유형은 비용 영향이고 견적 담당 협조 요청 대상이다

#### Scenario: 한국어 오타의 단가
- **WHEN** "차단가의 보조접점은 10,000회 연속 개폐 후에도 성능을 유지하여야 한다"에 유형을 붙이면
- **THEN** 단가 규칙으로 비용 영향이 되지 않는다

#### Scenario: 제조사 위임
- **WHEN** "Manufacturer authorization, production facility information, after-sales organization, and technical support plan."에 유형을 붙이면
- **THEN** 주 유형은 제조사 자격이다

#### Scenario: 가스 누설
- **WHEN** "The annual gas leakage rate of each gas compartment of the GIS shall not exceed 0.5 %."에 유형을 붙이면
- **THEN** 주 유형은 기술 성능이다
