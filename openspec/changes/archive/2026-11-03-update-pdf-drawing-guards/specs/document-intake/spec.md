## MODIFIED Requirements

### Requirement: PDF 쪽 속 그림 읽기
시스템은 PDF의 글자가 있는 쪽에 든 큰 그림(쪽 넓이의 5 % 이상)을 그림 위치 기록과 같게 줄 번호와 설명으로 저장하고, OCR 엔진이 있으면 그 그림 영역을 OCR로 읽어 그림 바로 뒤 단락으로 더해야 한다(SHALL). 작은 그림(로고·도장)은 건너뛰고, 그림 영역 안에 글자층 글자가 50자 이상이면 그 글자를 이미 읽었으므로 OCR하지 않는다(그림 위치는 저장). 그림 속 줄에서 나온 요구사항은 OCR로 글자 읽기와 같게 추출 방법 OCR과 낮은 신뢰도다. [제안 11-03]

#### Scenario: 글자 쪽에 박은 그림
- **WHEN** 본문 문장 아래에 "The enclosure shall be painted RAL 7032."가 그려진 그림과 설명 "Figure 1 Painting"이 있는 PDF 쪽을 OCR 엔진과 함께 처리하면
- **THEN** 그림 1개가 설명 "Figure 1 Painting"으로 저장되고 그림 속 문장이 추출 방법 OCR 요구사항으로 나온다

#### Scenario: 글자층이 깔린 그림
- **WHEN** 그림 위에 글자층 문장(50자 이상)이 겹쳐 있는 PDF 쪽을 OCR 엔진과 함께 처리하면
- **THEN** 그림 위치는 저장되고 OCR 단락은 없으며, 글자층 문장은 한 번만 요구사항으로 나온다

### Requirement: PDF 도면 쪽
시스템은 PDF 쪽에 표제란 낱말(DRAWING NO 또는 DWG NO, 그리고 SCALE)이 표 칸이나 짧은 라벨 줄(30자 이하, "."로 끝나지 않고 shall·must 없음)로 있고 shall·must 줄이 2줄 미만이면 도면 쪽으로 보고, 그 쪽의 라벨·치수·표제란을 단락이나 표로 읽지 않고 "NOTE"로 시작하는 주기 줄만 줄마다 단락으로 읽어야 한다(SHALL). 도면 쪽마다 그림 하나를 표제란의 도면 번호·제목을 설명으로(번호를 못 찾으면 "도면") 저장해 문서 읽기 점검에 보인다. 도면 기호·연결의 뜻은 읽지 않는다. [제안 11-03]

#### Scenario: 단선도 쪽
- **WHEN** 차단기 라벨 "CB 52-1"·"3150A", 치수 "2400", 주기 "NOTE 2: CONTRACTOR SHALL VERIFY ALL DIMENSIONS ON SITE.", 표제란(DRAWING NO DWG-SLD-001, SCALE NTS, TITLE SINGLE LINE DIAGRAM 154kV GIS)이 있는 PDF 쪽을 처리하면
- **THEN** 라벨·치수는 어떤 단락에도 없고 표제란은 표로 저장되지 않으며, 주기 문장은 요구사항으로 나오고, 그림 1개가 설명 "도면 DWG-SLD-001 · SINGLE LINE DIAGRAM 154kV GIS"로 저장된다

#### Scenario: 도면 낱말이 든 사양 본문
- **WHEN** "The Contractor shall submit shop drawings showing the drawing no., revision and scale."와 shall 요구 문장들이 든 글자 쪽(표제란 없음)을 처리하면
- **THEN** 도면 쪽으로 보지 않아 그 문장들이 모두 요구사항으로 나오고, 도면 그림은 저장되지 않는다

### Requirement: PDF 돌아간 글자
시스템은 PDF 쪽에서 실제로 돈 글자(가로 성분이 0 이하이거나 각도가 30°를 넘는 글자)를 줄로 읽지 않고, 그런 글자가 있는 쪽마다 그림 하나를 설명 "돌아간 글자 n자"로 저장해 문서 읽기 점검에 보여야 한다(SHALL). 기울임꼴(옆으로만 기울인 글자)은 가로 글자로 읽는다. 돌아간 글자를 돌려 읽어 문장을 만들지 않는다(CR-04). [제안 11-03]

#### Scenario: 돌아간 글자
- **WHEN** 가로 문장 "4.1 Cable shall be rated 33 kV."와 90°로 돌아간 라벨 "CABLE TRAY 600W"가 있는 PDF 쪽을 처리하면
- **THEN** 가로 문장은 요구사항으로 나오고, 돌아간 글자는 어떤 단락에도 없으며, 그림 1개가 설명 "돌아간 글자 13자"(빈칸 뺌)로 저장된다

#### Scenario: 기울임꼴 문장
- **WHEN** 가로 문장들과 옆으로 기울여 그린 문장 "The enclosure shall be painted RAL 7032."가 있는 PDF 쪽을 처리하면
- **THEN** 기울인 문장도 요구사항으로 나오고 "돌아간 글자" 그림은 저장되지 않는다
