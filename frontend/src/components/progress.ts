// 처리 진행률: 처리 상태 화면(SCR-02), 홈 카드(SCR-03), 검토 목록(SCR-06)이 같이 쓴다.
import type { RunListItem } from '../api'

type StepDetail = NonNullable<RunListItem['step_detail']>
type Progressing = Pick<RunListItem, 'step' | 'step_detail'>

// 처리 단계 순서 (pipeline/run.py build_graph)와 단계마다 보이는 문장
export const STEPS: [string, string][] = [
  ['created', '처리를 시작하는 중'], ['documents', '문서 읽는 중'], ['pairs', '원본·정정본 찾는 중'], ['risks', '위험 조건 찾는 중'],
  ['judge', '제품과 비교해 판정하는 중'], ['meaning', '뜻이 비슷한 항목 찾는 중'], ['check', '공학 규칙 검산 중'], ['warranty', '보증값 후보 만드는 중'], ['loss', '손실 환산 중'],
  ['outputs', '일탈·질의 목록 만드는 중'], ['proposals', '제안 포인트 만드는 중'], ['assign', '담당자에게 나누는 중'],
]

// 문서 읽기 단계 안의 세부 일 (pipeline/document.py report). [시작 비율, 끝 비율, 문장]
// 비율은 2026-10-25 실측(AI 유형 붙이기가 AI 비용의 약 90%)에 맞춘 어림값 [제안]
const PARTS: Record<StepDetail['part'], [number, number, string]> = {
  classify: [0, 0.02, '문서 종류 확인하는 중'],
  structure: [0.02, 0.05, '절·표 나누는 중'],
  extract: [0.05, 0.05, '요구사항 뽑는 중'],
  label: [0.05, 0.2, 'AI로 문장 구분하는 중'],
  save: [0.2, 0.25, '요구사항 저장하는 중'],
  type: [0.25, 1, 'AI로 유형 붙이는 중'],
}

// 막대에서 문서 읽기 단계가 차지하는 구간. 처리 시간 대부분이 이 단계라 막대 대부분을 준다 [제안]
const DOC_FROM = 2
const DOC_TO = 85

/** 지금까지 끝난 비율 (0~99). 마지막 단계가 끝나면 화면이 판정 탭으로 바뀐다 */
export function progress(run: Progressing): number {
  const at = Math.max(0, STEPS.findIndex(([k]) => k === run.step))
  if (at === 0) return 0
  if (run.step === 'documents') return Math.round(DOC_FROM + (DOC_TO - DOC_FROM) * documentShare(run.step_detail))
  const rest = STEPS.length - 2                              // 문서 읽기 뒤 단계 수
  return Math.min(99, Math.round(DOC_TO + ((at - 2) / rest) * (99 - DOC_TO)))
}

/** 문서 읽기 단계 안에서 끝난 비율 (0~1). 파일 순번으로 나누고 한 파일 안은 세부 일로 센다 */
function documentShare(d: StepDetail | null): number {
  if (!d) return 0
  const [from, to] = PARTS[d.part]
  const inPart = d.total ? Math.min(1, (d.done ?? 0) / d.total) : 0
  const inFile = from + (to - from) * inPart
  return Math.min(1, (d.file_index - 1 + inFile) / Math.max(1, d.file_count))
}

/** 지금 단계 문장. 문서 읽기 단계는 세부 일과 줄 수를 붙인다 (예: "AI로 유형 붙이는 중 480 / 3,397줄") */
export function stepText(run: Progressing): string {
  const d = run.step_detail
  if (run.step === 'documents' && d) {
    const count = d.total ? ` ${(d.done ?? 0).toLocaleString('ko-KR')} / ${d.total.toLocaleString('ko-KR')}건` : ''
    const file = d.file_count > 1 ? ` · 파일 ${d.file_index} / ${d.file_count}` : ''
    return `${PARTS[d.part][2]}${count}${file}`
  }
  return STEPS.find(([k]) => k === run.step)?.[1] ?? '처리하는 중'
}

/** 검토 목록 줄의 짧은 진행 문장 (목업 v4.96 목록 줄 진행 막대, "3/7 요구사항 문장 찾기 · 7 %"). 줄 수는 빼고 단계 순번을 붙인다 */
export function stepLine(run: Progressing): string {
  const steps = STEPS.slice(1)                                 // 'created'는 시작 전이라 세지 않는다
  const at = Math.max(0, steps.findIndex(([k]) => k === run.step))
  const d = run.step_detail
  const name = run.step === 'documents' && d ? PARTS[d.part][2] : steps[at]?.[1] ?? '처리를 시작하는 중'
  return `${at + 1}/${steps.length} ${name} · ${progress(run)} %`
}

/** "n분 m초" 같은 짧은 시간 */
export function duration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(s / 60)
  return m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : m > 0 ? `${m}분 ${s % 60}초` : `${s}초`
}

// 마지막 진행에서 이만큼 지나면 멈췄을 수 있다고 알린다. AI 한 묶음은 보통 10초 안팎 [제안]
export const STALL_MS = 10 * 60 * 1000
