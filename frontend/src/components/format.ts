// 화면 표시 형식 (docs/screens/_공통규칙.md 3장). 목업 v4.57과 같은 모양.

/** 로컬 날짜 YYYY-MM-DD */
export function isoDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 오늘부터 마감까지 남은 날. 마감이 오늘이면 0, 지났으면 음수 */
export function daysLeft(due: string, today: Date = new Date()): number {
  const [y, m, d] = due.split('-').map(Number)
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((new Date(y, m - 1, d).getTime() - t.getTime()) / 86_400_000)
}

/** 목업의 마감 표시: D-3 / D-Day / D+1. 3일 이하는 빨강, 7일 이하는 주황 */
export function dday(due: string, today: Date = new Date()): { text: string; cls: string } {
  const left = daysLeft(due, today)
  const text = left < 0 ? `D+${-left}` : left === 0 ? 'D-Day' : `D-${left}`
  return { text, cls: left <= 3 ? 'neg' : left <= 7 ? 'crit' : 'neu' }
}

/** 마감 날짜: 올해는 MM-DD, 다른 해는 YYYY-MM-DD */
export function dueText(due: string, today: Date = new Date()): string {
  return due.startsWith(String(today.getFullYear())) ? due.slice(5) : due
}

/** 상신 권장일: 제출 마감 2일 전(달력 기준, _공통규칙.md 3장·_v4.96_결정.md Q3). 마감이 없으면 null, 지났으면 late */
export function submitBy(due: string | null, today: Date = new Date()): { text: string; late: boolean } | null {
  if (!due) return null
  const [y, m, d] = due.split('-').map(Number)
  const day = isoDay(new Date(y, m - 1, d - 2))
  return { text: dueText(day, today), late: daysLeft(day, today) < 0 }
}

/** 시각: 올해는 MM-DD HH:mm, 다른 해는 YY-MM-DD (목업 검토 목록 "시작") */
export function stamp(iso: string, today: Date = new Date()): string {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  if (d.getFullYear() === today.getFullYear()) {
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }
  return isoDay(d).slice(2)
}

/** 천 단위 쉼표 */
export function num(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : v.toLocaleString('en-US')
}

/** 첫 파일 이름 (검토명이 비었을 때 대신 보인다) */
export function firstFile(files: string | null): string | null {
  return files ? files.split(', ')[0] : null
}

/** 파일 목록 줄임: "a.docx 외 2건" */
export function filesText(files: string | null): string {
  if (!files) return ''
  const all = files.split(', ')
  return all.length > 1 ? `${all[0]} 외 ${all.length - 1}건` : all[0]
}

/** 검토명(설비 범위). 비어 있으면 첫 파일 이름 (add-review-info "검토명이 빈 검토") */
export function scopeName(r: { review_name: string | null; files?: string | null; run_id: number }): string {
  return r.review_name ?? firstFile(r.files ?? null) ?? `검토 #${r.run_id}`
}

/** 화면 제목: "사업명 · 검토명" (한쪽이 비면 있는 쪽만) */
export function reviewTitle(r: { project_name: string | null; review_name: string | null; files?: string | null; run_id: number }): string {
  return r.project_name ? [r.project_name, r.review_name].filter(Boolean).join(' · ') : scopeName(r)
}
