import type { RunDocument } from '../api'

// 검토 문서 표시 (머리글 판정 묶음, 문서 표 창). change update-document-info

/** 분류 방법 (document.classify_by) */
export const CLASSIFY_BY: Record<string, string> = { RULE: '규칙', AI: 'AI', HUMAN: '사람' }

/** 판정 대상인 문서의 묶음 (A·B 순서). 없으면 빈 배열 */
export const judgedBundles = (docs: RunDocument[]) =>
  Array.from(new Set(docs.filter((d) => d.judge_target).map((d) => d.bundle))).sort()

/** 판정하지 않는 이유 (표시 문구만 고른다. 판정 대상은 백엔드가 정한다, CR-09) */
export function skipReason(d: RunDocument): string {
  if (!d.readable) return '글자를 읽지 못함'
  if (d.bundle === 'C') return '묶음 C: 판정 범위 밖 (문서 목록에 없는 문서도 C)'
  if (d.bundle === 'D') return '묶음 D: 판정 범위 밖'
  return '판정 범위 밖'
}
