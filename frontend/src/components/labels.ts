import type { Location } from '../api'

// 사람이 읽는 이름 (코드 값 → 화면 문구)
export const RESULT_NAMES: Record<string, string> = {
  COMPLY: '준수',
  DEVIATION_CANDIDATE: '일탈 후보',
  QUERY_CANDIDATE: '질의 후보',
  NEEDS_REVIEW: '확인 필요',
  WARRANTY_TO_FILL: '보증값 작성',
}
/** 판정 배지 색과 칩 점 색 (목업 K) */
export const RESULT_TONES: Record<string, string> = {
  DEVIATION_CANDIDATE: 'c-red', QUERY_CANDIDATE: 'c-ora', NEEDS_REVIEW: 'c-ora', WARRANTY_TO_FILL: 'c-blue', COMPLY: 'c-green',
}
export const RESULT_DOTS: Record<string, string> = {
  DEVIATION_CANDIDATE: 'var(--c-red)', QUERY_CANDIDATE: 'var(--c-orange)', NEEDS_REVIEW: 'var(--c-orange-dot)', WARRANTY_TO_FILL: 'var(--c-link)', COMPLY: 'var(--c-green)',
}
/** 판정 순서: 일탈 → 질의 → 확인 필요 → 보증값 작성 → 준수 */
export const RESULT_ORDER = ['DEVIATION_CANDIDATE', 'QUERY_CANDIDATE', 'NEEDS_REVIEW', 'WARRANTY_TO_FILL', 'COMPLY']
export const STAGE_NAMES: Record<string, string> = {
  PROCESSING: '처리 중',
  ENGINEER_REVIEW: '담당자 확인',
  APPROVAL: '승인 대기',
  APPROVED: '승인됨',
  REJECTED: '반려됨',
  FAILED: '처리 실패',
}
/** 단계 배지 색 (목업 .st.c-*) */
export const STAGE_TONES: Record<string, string> = {
  PROCESSING: 'c-grey', ENGINEER_REVIEW: 'c-blue', APPROVAL: 'c-grey', APPROVED: 'c-green', REJECTED: 'c-grey',
  FAILED: 'c-red',
}
export const STEP_NAMES: Record<string, string> = {
  created: '시작', documents: '문서 읽기', pairs: '같은 문서 찾기', risks: '위험 조건 찾기',
  judge: '제품 비교 판정', check: '공학 규칙 검산', warranty: '보증값 후보', loss: '손실 환산', outputs: '일탈·질의 목록',
  proposals: '제안 포인트', assign: '담당자 전달', done: '처리 끝', engineer_review: '담당자 확인', approval: '승인 대기',
  approved: '승인됨', rejected: '반려됨', meaning: '유사 문장 검색',
}
// 흐름 기록 (add-flow-history): 사람 동작과 바뀐 건수 이름. 단계 이름은 STEP_NAMES (+ meaning)
export const FLOW_ACTION_NAMES: Record<string, string> = {
  submit: '상신', approve: '승인', reject: '반려', withdraw: '상신 취소', reopen: '다시 확인', add_documents: '문서 추가',
  rewind: '되돌려 다시 처리',
}
export const FLOW_COUNT_NAMES: Record<string, string> = {
  documents: '문서', readable_documents: '읽은 문서', risk_count: '위험 조건', judgment_count: '판정', check_count: '검산',
  warranty_count: '보증값', loss_count: '손실 환산', output_count: '목록 줄', proposal_count: '제안 포인트',
  assignment_count: '협조 요청', meaning_count: '유사도 분석',
}
// 단계부터 다시 처리 (add-step-rewind)에서 고를 수 있는 처리 단계, 흐름 순서
export const PIPELINE_STEPS = ['documents', 'pairs', 'risks', 'judge', 'meaning', 'check', 'warranty', 'loss', 'outputs', 'proposals', 'assign']
export const STATUS_NAMES: Record<string, string> = {
  CANDIDATE: '후보', CONFIRMED: '확정', EDITED: '수정함', REJECTED: '반려', EMPTY_REVIEW: '확인 필요',
  DRAFT: '초안', REMOVED: '제외', ADOPTED: '채택', DISCARDED: '제외', CLOSED_OK: '문제 없음',
}
export const POINT_KIND_NAMES: Record<string, string> = {
  MARGIN: '여유', LOSS: '손실 환산', FIELD: '현장 이력',
}
export const ROLE_NAMES: Record<string, string> = {
  ENGINEER: '기술 검토 엔지니어', APPROVER: '승인자', COST: '견적 담당', QUALITY: '품질 담당', SALES: '영업 담당',
}
/** 요구사항 유형 7종 (명세서 2-2). 순서는 거르기 목록 순서 */
export const TYPE_NAMES: Record<string, string> = {
  TECH_PERF: '기술 성능', STANDARD_CERT: '적용 규격·인증', SITE_ENV: '설치 환경', MAKER_QUAL: '제조사 자격',
  TEST: '시험', COST: '비용 영향', RISK: '위험 조건',
}
export const RISK_NAMES: Record<string, string> = {
  BLANKET: '포괄 조항', VALUE_MISMATCH: '값 불일치', OPEN_SCOPE: '범위 모호', COST_SHIFT: '비용 전가',
}

export function locationText(loc: Location): string {
  const where = loc.table_name
    ? `${loc.table_name}${loc.item_no ? ` ${loc.item_no}번` : ''}`
    : `${loc.section_no ?? ''} ${loc.section_title ?? ''}`.trim()
  const line = loc.line_start ? ` · ${loc.line_start}행` : ''
  const page = loc.page ? ` · ${loc.page}쪽` : ''      // PDF 쪽 (add-pdf-page-location)
  return `파일 ${loc.file_no}${page}${where ? ` · ${where}` : ''}${line}`
}
export const DOC_KIND_NAMES: Record<string, string> = {
  BID_FORM: '입찰 양식', REQUIREMENT_SPEC: '요구 사양서', PURCHASE_SPEC: '구매 사양서', TEST_SPEC: '시험 사양서',
  SUPPLIER_SPEC: '공급사 사양', BOQ: '물량표', UNKNOWN: '종류 모름',
}
/** 제품군 (product_master.family) */
export const FAMILY_NAMES: Record<string, string> = {
  GIS: 'GIS', MV_EQUIP: '중전압 설비', SPD: '서지 보호기', TRANSFORMER: '변압기',
}
/** 비교 방향 (compare_rule.direction, item_key.default_direction) */
export const DIRECTION_NAMES: Record<string, string> = {
  EQ: '같아야 함', GE: '같거나 커야 함', LE: '같거나 작아야 함', LT: '작아야 함', IN: '요구를 포함해야 함',
  FILL: '보증값 작성', TEXT: '문장 비교', AI: 'AI 문장 판독', SOURCE: '원문 기호 따름',
}
/** 규칙 사전 이름 (판정 규칙 화면 고치기 API의 dictionary) */
export const DICTIONARY_NAMES: Record<string, string> = {
  compare: '비교 방향', 'risk-expressions': '위험 표현', items: '항목 이름', 'doc-kinds': '문서 종류',
}
/** 규칙을 고칠 수 있는 역할 [제안] */
export const EDITOR_ROLES = ['ENGINEER', 'APPROVER']
/** 규칙 사전 칸 이름 (수정 이력의 바뀐 칸) */
export const RULE_FIELD_NAMES: Record<string, string> = {
  table_name: '대상 표', item_no: '항목 번호', item_key: '표준 항목', direction: '비교 방향', time_condition: '시간 조건',
  strength_direction: '강점 방향', process_note: '처리', expression: '표현', language: '언어', risk_kind: '위험 종류',
  context_rule: '위험으로 보는 조건', name_ko: '한글 이름', default_direction: '기본 방향', note: '메모', aliases: 'RFP 표기',
  priority: '순서', doc_kind: '문서 종류', name_pattern: '파일 이름 표현', page_pattern: '첫 장 표현',
}
