// 표준 문구 예시 데이터 (목업 v4.57 Phrases의 PH 10건). 표준 문구 저장소가 없어 예시로만 보여 준다 (SCR-18_공유.md).
// 일탈·질의 문장은 지금 FR-09에서 언어 모델이 쓴다. 사람 이름은 역할로 바꿨다.

export type PhraseKind = 'dev' | 'qry' | 'cf'
export type PhraseState = 'use' | 'rev' | 'old'
/** [코드, 구분, 쓰는 상황, 영문, 국문, 연결된 판정 규칙, 변경 이력, 최근 90일 사용, 수정한 사람, 수정일, 상태] */
export type Phrase = [string, PhraseKind, string, string, string, string, string, number, string, string, PhraseState]

export const PHRASE_RELEASE = "현재 배포본 v3"
export const PHRASE_RELEASE_BY = "10-17 · 기술 검토 엔지니어 D"

export const EXAMPLE_PHRASES: Phrase[] = [
  ["DV-01", "dev", "정격값이 요구보다 낮을 때 — 대안 제안", "The offered {제품} is rated {제품값} for {항목}, which is below the specified {요구값}. As an alternative, we propose {대안}, which fully meets the requirement.", "제안 제품 {제품}의 {항목}은 {제품값}으로 요구값 {요구값}보다 낮습니다. 요구를 모두 만족하는 {대안}을 대안으로 제안합니다.", "정격 비교 규칙 R-03 · R-07", "v3 (10-17) 대안 제안 문장을 앞에 둠\nv2 (2025-06) 최초 작성", 42, "기술 검토 엔지니어 D", "10-17", "use"],
  ["DV-02", "dev", "적용 규격의 판(版)이 다를 때", "Type tests were performed in accordance with {규격} ({제품판}). The results are considered equivalent to {요구판} for {항목}; the comparison table is attached.", "형식시험은 {규격} {제품판}에 따라 실시했습니다. {항목}에 대해서는 {요구판}과 같은 수준으로 보며, 비교표를 첨부합니다.", "규격 판 비교 규칙 R-12", "v3 (10-17) \"considered equivalent\"로 표현 완화\nv2 (2025-06) 최초 작성", 17, "기술 검토 엔지니어 D", "10-17", "use"],
  ["DV-03", "dev", "설치 환경(고도·온도)이 표준 범위를 넘을 때", "For installation above {표준고도}, the insulation level is corrected per {규격}. The offered design applies a correction factor of {보정계수} and is suitable for {요구고도}.", "설치 고도가 {표준고도}를 넘으면 {규격}에 따라 절연 수준을 보정합니다. 보정 계수 {보정계수}를 적용해 {요구고도}에서 사용할 수 있습니다.", "환경 조건 규칙 R-21 · R-22", "v3 (10-17) 보정 계수 자리 추가", 11, "기술 검토 엔지니어 C", "10-17", "use"],
  ["DV-04", "dev", "예비품·납기 범위가 다를 때", "Spare parts are offered for {제공기간} of operation as listed in Annex {부록}. Additional spares for {요구기간} can be quoted separately upon request.", "예비품은 부록 {부록}에 정리한 {제공기간}분을 제안합니다. {요구기간}분 추가 예비품은 요청하시면 따로 견적합니다.", "예비품 규칙 R-30", "v3 (10-17) 최초 작성", 8, "기술 검토 엔지니어 B", "10-17", "use"],
  ["QA-01", "qry", "문서끼리 요구값이 서로 다를 때", "Section {조항A} specifies {값A}, while Section {조항B} specifies {값B} for {항목}. Please confirm which value shall govern.", "{항목}에 대해 {조항A}는 {값A}, {조항B}는 {값B}로 서로 다릅니다. 어느 값을 따라야 하는지 확인 부탁드립니다.", "문서 충돌 규칙 R-40", "v3 (10-17) \"shall govern\"으로 통일\nv2 (2025-06) 최초 작성", 23, "기술 검토 엔지니어 C", "10-17", "use"],
  ["QA-02", "qry", "값에 조건(시간·단위)이 빠졌을 때", "Please clarify the {빠진조건} for the specified {항목} of {요구값}.", "요구값 {요구값}인 {항목}의 {빠진조건}을 알려 주시기 바랍니다.", "조건 누락 규칙 R-41", "v3 (10-17) 최초 작성", 19, "기술 검토 엔지니어 C", "10-17", "use"],
  ["QA-03", "qry", "근거 규격이 적혀 있지 않을 때", "The applicable standard for {항목} is not stated. We propose to apply {제안규격}; please confirm if this is acceptable.", "{항목}의 적용 규격이 없습니다. {제안규격}을 적용하려 하니 괜찮은지 확인 부탁드립니다.", "규격 누락 규칙 R-42", "v3 (10-17) 제안 규격을 함께 적도록 바꿈", 6, "기술 검토 엔지니어 D", "10-17", "use"],
  ["CF-01", "cf", "견적에 영향 있는 상업 조건 확인 요청 (내부)", "Liability cap in clause {조항} is {한도}. Please confirm whether this is reflected in the quotation.", "{조항}의 책임 한도가 {한도}입니다. 견적에 반영되었는지 확인 부탁드립니다.", "상업 조건 규칙 M-02", "v3 (10-17) 최초 작성", 9, "기술 검토 엔지니어 A", "10-17", "use"],
  ["CF-02", "cf", "설계 확인이 필요한 요구 (내부)", "{항목} requires {요구값}. Please confirm whether the {제품} design can meet this, and by when.", "{항목} 요구값이 {요구값}입니다. {제품} 설계로 맞출 수 있는지, 언제까지 답할 수 있는지 확인 부탁드립니다.", "설계 확인 규칙 R-50", "검토 중 — 10-29 팀 회의에서 확정 예정", 0, "기술 검토 엔지니어 A", "10-27", "rev"],
  ["DV-90", "dev", "(v2) 요구를 따를 수 없을 때", "We cannot comply with {항목}.", "{항목}을 따를 수 없습니다.", "—", "v3 (10-17) 폐기 — 고객 회신에서 부정적 표현으로 2회 지적", 0, "기술 검토 엔지니어 D", "10-17", "old"],
]
