import { useState } from 'react'
import { api, type RunSummary } from '../../api'
import { useLoad } from '../../components/useLoad'
import { useSession } from '../../shell/useSession'
import '../detail.css'

// SCR-08 머리글의 비교 제품 고르기 (목업 v4.57 Detail ".seg 115 kV 비교 제품").
// 설비 묶음(표)마다 한 줄: 묶음 이름 | 후보 제품 단추. 다른 제품을 누르면 그 묶음을 다시 판정한다 (PUT /equipment/{group}/product).
// 묶음이 많으면(실제 RFP는 10개 넘음) 접어 두고 요약만 보인다 (SCR-08_공유.md).

/** "파일 94 TS-115-GIS" → "TS-115-GIS" */
const groupName = (label: string | null) => (label ?? '').replace(/^파일 \d+\s*/, '') || '설비'

const OPEN_MAX = 4          // 묶음이 이보다 많으면 처음에는 접어 둔다

/** 다시 판정 중인 묶음과 바꾼 제품. 검토 상세가 화면 가운데 안내를 띄우는 데 쓴다 */
export type Rejudging = { group: string; product: string }

export function ProductSeg({ run, onSwitched, onBusy }: {
  run: RunSummary; onSwitched: () => void; onBusy?: (b: Rejudging | null) => void
}) {
  const { user } = useSession()
  const id = run.run_id
  const groups = useLoad(() => api.equipment(id), [id])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const canEdit = run.stage === 'ENGINEER_REVIEW' && user?.role === 'ENGINEER'
  const shown = (groups.data ?? []).filter((g) => g.family && (g.candidates.length > 0 || g.products?.length))
    .map((g) => ({ g, name: groupName(g.label), current: g.chosen_product ?? g.products?.[0] ?? null }))
    .sort((a, b) => a.name.localeCompare(b.name))
  if (!shown.length) return null
  const choose = (group: string, name: string, code: string) => {
    setBusy(group)
    setError(null)
    onBusy?.({ group: name, product: code })
    api.chooseProduct(id, group, code).then(() => { groups.reload(); onSwitched() }, (e: Error) => setError(e.message))
      .finally(() => { setBusy(null); onBusy?.(null) })
  }
  const products = Array.from(new Set(shown.map((s) => s.current).filter(Boolean)))
  const picked = shown.filter((s) => s.g.chosen_product).length
  const optionsOf = (g: (typeof shown)[number]['g']) => Array.from(new Set([...g.candidates, ...(g.products ?? [])]))
  // 후보가 하나뿐인 묶음만 있으면 바꿀 제품이 없다
  const switchable = shown.some(({ g }) => optionsOf(g).length > 1)
  return (
    <details className="pseg" open={shown.length <= OPEN_MAX}>
      <summary>
        <span className="ms" aria-hidden="true">inventory_2</span>
        <b>비교 제품</b>
        <span className="pseg-sum">설비 {shown.length}개 · {products.slice(0, 3).join(', ')}{products.length > 3 ? ` 외 ${products.length - 3}개` : ''}
          {picked > 0 && ` · 엔지니어가 고름 ${picked}개`}</span>
        <span className="pseg-tg">{canEdit && switchable ? '펼쳐서 바꾸기' : '펼쳐 보기'}</span>
      </summary>
      <div className="pseg-grid">
        {shown.map(({ g, name, current }) => {
          const options = optionsOf(g)
          return (
            <div className="pseg-row" key={g.equipment_group}>
              <div className="pseg-name" title={name}>{name}</div>
              <div className="seg" role="group" aria-label={`${name} 비교 제품`}
                title={canEdit ? (g.chosen_product ? '엔지니어가 고름' : '자동으로 고름') : '담당자 확인 단계의 엔지니어만 바꿀 수 있습니다'}>
                {options.map((c) => (
                  <button key={c} type="button" className={c === current ? 'on' : ''} aria-pressed={c === current}
                    disabled={!canEdit || busy !== null} onClick={() => { if (c !== current) choose(g.equipment_group, name, c) }}>{c}</button>
                ))}
              </div>
              {busy === g.equipment_group ? <span className="en">다시 판정 중…</span>
                : options.length === 1 && <span className="en pseg-one" title="제품표에 요구 정격에 맞는 제품이 이것 하나뿐입니다">다른 후보 없음</span>}
            </div>
          )
        })}
      </div>
      {error && <span className="aphint" role="alert">{error}</span>}
    </details>
  )
}
