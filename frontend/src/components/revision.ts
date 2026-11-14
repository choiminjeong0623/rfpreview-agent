import type { Revision } from '../api'

// 개정 줄 수 문장 (add-revision-notice). 판정 탭 개정 안내 띠와 홈 "어제 이후 바뀐 것"이 같이 쓴다.

/** "판정 2줄 바뀜 · 3줄 추가 · 1줄 사라짐" (0인 것은 뺌, 모두 0이면 "판정 바뀐 줄 없음") */
export function revisionText(r: Revision): string {
  const parts = [r.changed && `판정 ${r.changed}건 변경`, r.added && `${r.added}건 추가`, r.removed && `${r.removed}건 삭제`].filter(Boolean)
  return parts.length ? parts.join(' · ') : '변경된 판정 없음'
}
