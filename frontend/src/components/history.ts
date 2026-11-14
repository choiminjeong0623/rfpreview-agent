import type { LogEntry } from '../api'
import { RESULT_NAMES, ROLE_NAMES, STATUS_NAMES, STEP_NAMES } from './labels'

// SCR-08-9 이력 탭의 한 줄 문장 (목업 v4.57 Detail logs: '위험 조건 "주위 온도"를 정상으로 닫음').
// 기록(before/after) 그대로 문장으로만 바꾼다. 값을 계산하거나 고치지 않는다.

const INFO_NAMES: Record<string, string> = {
  project_name: '사업명', review_name: '설비 범위', customer_name: '고객사', country: '국가',
  due_date: '제출 마감일', engineer_id: '담당 엔지니어',
}
const LIST_NAMES: Record<string, string> = { DEVIATION: '일탈 목록', QUERY: '질의 목록' }

const q = (label: string | null | undefined) => (label ? `"${label}"` : '')
const v = (x: unknown) => (x === null || x === undefined || x === '' ? '비어 있음' : String(x))
const kw = (x: unknown) => (x === null || x === undefined ? '—' : String(x))

export function historyText(l: LogEntry): string {
  const b = l.before_value ?? {}
  const a = l.after_value ?? {}
  const name = q(l.target_label)
  switch (l.target_table) {
    case 'judgment':
      if (l.action === 'EDIT' && a.result !== undefined) {
        return `판정 ${name} ${RESULT_NAMES[String(b.result)] ?? v(b.result)} → ${RESULT_NAMES[String(a.result)] ?? v(a.result)}`
      }
      return l.action === 'CONFIRM' ? `판정 ${name} 제안대로 확정` : `판정 ${name} ${STATUS_NAMES[String(a.review_status)] ?? l.action}`
    case 'warranty_candidate':
      return l.action === 'CONFIRM' ? `보증값 ${name} 확정` : `보증값 ${name}에 ${v(a.candidate_value)}${a.candidate_unit ? ` ${a.candidate_unit}` : ''} 입력`
    case 'risk_flag':
      return l.action === 'CONFIRM' ? `위험 조건 ${name} 위험으로 확정` : `위험 조건 ${name} 문제 없음으로 닫음`
    case 'output_item': {
      const list = LIST_NAMES[String(a.list_kind ?? b.list_kind)] ?? '목록'
      return l.action === 'CONFIRM' ? `${list} 문장 ${name} 확정` : l.action === 'REJECT' ? `${list}에서 ${name} 뺌` : `${list} 문장 ${name} 고침`
    }
    case 'proposal_point':
      return l.action === 'ADOPT' ? `제안 포인트 ${name} 채택` : l.action === 'DISCARD' ? `제안 포인트 ${name} 제외` : `제안 포인트 ${name} 문장 고침`
    case 'loss_calc':
      return `손실값 고침 (무부하 ${kw(a.loss_noload_kw)} · 부하 ${kw(a.loss_load_kw)} · 보조 ${kw(a.loss_aux_kw)} kW)`
    case 'read_check':
      // 목업: "문서 읽기 점검 확인: <위치> (<무엇>)"
      return `문서 읽기 점검 ${l.action === 'UNDO' ? '확인 되돌림' : '확인'}: ${l.target_label ?? ''}`
    case 'assignment': {
      // 협조 요청 메일 (update-role-handoff-mail): 보낸 기록과 회신 기록
      const dept = ROLE_NAMES[String(a.dept)] ?? '담당'
      if (l.action === 'SEND') return `협조 요청 메일 보냄: ${dept} ${v(a.mail_to)} (${kw(a.count)}건)`
      if (l.action === 'REPLY') return `협조 요청 회신 완료${a.reply_note ? `: ${String(a.reply_note)}` : ''}`
      return '협조 요청 회신 완료 취소'
    }
    case 'sales_handoff': {
      // 영업 인계 (add-submission-package)
      const what = a.kind === 'PACKAGE' ? '인계 패키지' : '데이터시트'
      if (a.error) return `${what} 영업에 넘기지 못함: ${String(a.error)}`
      return `${what} 영업에 넘김: ${v(a.mail_to)}`
    }
    case 'run_document':
      // 문서 추가 (add-document-addendum): 정정본·추가 문서를 더해 다시 분석
      return `문서 추가: ${Array.isArray(a.files) ? a.files.join(', ') : ''}`
    case 'run_product_choice':
      return `비교 제품 바꿈: ${v(b.product_code === null ? '자동' : b.product_code)} → ${v(a.product_code === null ? '자동' : a.product_code)}`
    case 'review_run': {
      // 단계부터 다시 처리 (add-step-rewind)
      if (l.action === 'REWIND') return `${STEP_NAMES[String(a.step)] ?? v(a.step)}부터 다시 처리`
      if (a.stage === 'APPROVAL') return '결재 상신'
      if (a.stage === 'APPROVED') return '승인'
      if (a.stage === 'REJECTED') return '반려'
      if (b.stage === 'APPROVAL' && a.stage === 'ENGINEER_REVIEW') return '결재 상신 취소'
      if (b.stage === 'REJECTED' && a.stage === 'ENGINEER_REVIEW') return '반려 뒤 다시 확인 시작'
      const fields = Object.keys(a).filter((k) => INFO_NAMES[k])
      if (fields.length) return `검토 정보 고침: ${fields.map((k) => `${INFO_NAMES[k]} ${v(b[k])} → ${v(a[k])}`).join(', ')}`
      return '검토 실행 바뀜'
    }
    default:
      return `${l.target_table} ${l.action}`
  }
}

/** 사유 줄의 이름: 결재·상신은 "의견", 나머지는 "사유" */
export function reasonLabel(l: LogEntry): string {
  return l.target_table === 'review_run' && l.action !== 'EDIT' && l.action !== 'REWIND' ? '의견' : '사유'
}
