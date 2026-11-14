import { useEffect, useState } from 'react'
import { api, type RuleDictionary, type RuleValue } from '../api'
import { DICTIONARY_NAMES, DIRECTION_NAMES, DOC_KIND_NAMES, EDITOR_ROLES, RISK_NAMES } from '../components/labels'
import { useSession } from '../shell/useSession'
import './detail.css'
import './rules.css'

// SCR-17 판정 규칙 고치기 창 (add-rule-editing). 결재 상신 창(.apw)과 같은 모양.
// 검사(코드표·정규식·겹침·권한)는 서버가 하고, 틀리면 서버 문구를 그대로 보여 준다.

type Field = {
  key: string; label: string; kind: 'text' | 'number' | 'select' | 'check' | 'list'
  options?: [string, string][]; required?: boolean; hint?: string; fixedOnEdit?: boolean; wide?: boolean
}

const STRENGTHS: [string, string][] = [['HIGHER', '클수록 강점'], ['LOWER', '작을수록 강점'], ['NONE', '강점 아님']]
const codes = (names: Record<string, string>, only?: string[]): [string, string][] =>
  Object.entries(names).filter(([k]) => !only || only.includes(k)).map(([k, v]) => [k, `${v} (${k})`])

function fields(dictionary: RuleDictionary, itemKeys: [string, string][]): Field[] {
  switch (dictionary) {
    case 'compare': return [
      { key: 'table_name', label: '대상 표', kind: 'text', required: true, hint: '예: TS-115-GIS' },
      { key: 'item_no', label: '항목 번호', kind: 'text', required: true },
      { key: 'item_key', label: '표준 항목', kind: 'select', options: [['', '표준 항목 없음'], ...itemKeys], wide: true },
      { key: 'direction', label: '비교 방향', kind: 'select', required: true, options: codes(DIRECTION_NAMES) },
      { key: 'strength_direction', label: '강점 방향', kind: 'select', options: [['', '표준 항목 기본값 따름'], ...STRENGTHS] },
      { key: 'time_condition', label: '시간 조건도 비교 (더 길면 준수)', kind: 'check', wide: true },
      { key: 'process_note', label: '처리', kind: 'text', wide: true },
    ]
    case 'risk-expressions': return [
      { key: 'expression', label: '표현 (원문)', kind: 'text', required: true, wide: true, hint: '예: to the satisfaction of the Engineer' },
      { key: 'risk_kind', label: '위험 종류', kind: 'select', required: true,
        options: codes(RISK_NAMES, ['BLANKET', 'COST_SHIFT', 'OPEN_SCOPE']) },
      { key: 'language', label: '언어', kind: 'select', required: true, options: [['en', '영어 (en)'], ['ko', '한국어 (ko)']] },
      { key: 'context_rule', label: '위험으로 보는 조건', kind: 'text', wide: true, hint: '비우면 "(조건 미정)"' },
    ]
    case 'items': return [
      { key: 'item_key', label: '표준 항목 키', kind: 'text', required: true, fixedOnEdit: true, hint: '영어 소문자·숫자·밑줄. 예: rated_current' },
      { key: 'name_ko', label: '한글 이름', kind: 'text', required: true },
      { key: 'aliases', label: 'RFP에 나오는 표기 (;로 구분)', kind: 'list', wide: true },
      { key: 'default_direction', label: '기본 비교 방향', kind: 'select', required: true,
        options: codes(DIRECTION_NAMES).filter(([k]) => k !== 'AI') },
      { key: 'strength_direction', label: '강점 방향', kind: 'select', required: true, options: STRENGTHS },
      { key: 'note', label: '메모', kind: 'text', wide: true },
    ]
    case 'doc-kinds': return [
      { key: 'doc_kind', label: '문서 종류', kind: 'select', required: true, options: codes(DOC_KIND_NAMES).filter(([k]) => k !== 'UNKNOWN') },
      { key: 'priority', label: '순서', kind: 'number', required: true, hint: '작을수록 먼저 봄' },
      { key: 'name_pattern', label: '파일 이름에서 찾는 표현 (정규식)', kind: 'text', required: true, wide: true, hint: '예: testing|시험' },
      { key: 'page_pattern', label: '첫 장에서 찾는 표현 (정규식)', kind: 'text', wide: true, hint: '비우면 파일 이름만 봄' },
      { key: 'note', label: '메모', kind: 'text', wide: true },
    ]
  }
}

type Form = Record<string, string | boolean>

function toForm(fs: Field[], value: RuleValue | null): Form {
  const out: Form = {}
  fs.forEach((f) => {
    const v = value?.[f.key]
    out[f.key] = f.kind === 'check' ? !!v : f.kind === 'list' ? ((v as string[] | undefined) ?? []).join('; ')
      : v === null || v === undefined ? (f.kind === 'select' && f.required ? f.options?.[0][0] ?? '' : '') : String(v)
  })
  return out
}

function toValue(fs: Field[], form: Form): RuleValue {
  const out: RuleValue = {}
  fs.forEach((f) => {
    const v = form[f.key]
    if (f.kind === 'check') out[f.key] = !!v
    else if (f.kind === 'list') out[f.key] = String(v).split(';').map((s) => s.trim()).filter(Boolean)
    else if (f.kind === 'number') out[f.key] = String(v).trim() === '' ? null : Number(v)
    else out[f.key] = String(v).trim() === '' ? null : String(v).trim()
  })
  return out
}

// suggestionId: 사람이 제안한 표현을 반영할 때(add-rule-suggestion). 저장하면 제안 반영 API를 부른다
export type RuleTarget = { mode: 'add' | 'edit' | 'delete'; dictionary: RuleDictionary; id?: string; value?: RuleValue; title?: string; suggestionId?: number }

export function RuleDialog({ target, itemKeys, onClose, onDone }: {
  target: RuleTarget; itemKeys: [string, string][]; onClose: () => void; onDone: () => void
}) {
  const { user } = useSession()
  const fs = fields(target.dictionary, itemKeys)
  const [form, setForm] = useState<Form>(() => toForm(fs, target.value ?? null))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const allowed = !!user && EDITOR_ROLES.includes(user.role)
  const ready = allowed && reason.trim() !== ''
  const verb = { add: '추가', edit: '수정', delete: '삭제' }[target.mode]
  const save = () => {
    if (!ready || !user) return
    setBusy(true)
    setError(null)
    const value = toValue(fs, form)
    const call = target.suggestionId ? api.acceptSuggestion(target.suggestionId, value, reason.trim(), user.user_id)
      : target.mode === 'add' ? api.addRule(target.dictionary, value, reason.trim(), user.user_id)
      : target.mode === 'edit' ? api.updateRule(target.dictionary, target.id!, value, reason.trim(), user.user_id)
        : api.deleteRule(target.dictionary, target.id!, reason.trim(), user.user_id)
    call.then(onDone, (e: Error) => setError(e.message)).finally(() => setBusy(false))
  }

  return (
    <div className="mdo" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="apw" role="dialog" aria-modal="true" aria-labelledby="ruleTitle">
        <div className="mdh">
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <div className="apid">{DICTIONARY_NAMES[target.dictionary]} 사전{target.title ? ` · ${target.title}` : ''}</div>
            <h2 id="ruleTitle" style={{ margin: '2px 0 0', fontSize: 'var(--fs-h3)' }}>{target.suggestionId ? '제안 반영' : `규칙 ${verb}`}</h2>
          </div>
          <button type="button" className="ib" onClick={onClose} aria-label="닫기" title="닫기 (Esc)"><span className="ms" aria-hidden="true">close</span></button>
        </div>
        <div className="apb">
          {target.mode === 'delete' ? (
            <section className="aps"><h3>지울 규칙</h3>
              <ul className="rdel">{fs.filter((f) => target.value?.[f.key] !== null && target.value?.[f.key] !== undefined && target.value?.[f.key] !== '').map((f) => (
                <li key={f.key}><span>{f.label}</span><b>{String(f.kind === 'list' ? (target.value![f.key] as string[]).join('; ') : target.value![f.key])}</b></li>
              ))}</ul>
              <p className="rnote">{target.dictionary === 'doc-kinds' ? '문서 종류 규칙은 다음 분류부터 쓰지 않습니다.'
                : '목록과 다음 검토에서 빠집니다. 이미 만든 검토 결과는 그대로 남고, 같은 키로 다시 추가하면 되살아납니다.'}</p>
            </section>
          ) : (
            <section className="aps"><h3>규칙 내용</h3>
              <div className="infog">
                {fs.map((f) => {
                  const id = `rf-${f.key}`
                  // 제안 반영은 표현을 제안 그대로 쓴다
                  const disabled = (f.fixedOnEdit && target.mode === 'edit') || (!!target.suggestionId && f.key === 'expression')
                  const style = f.wide ? { gridColumn: '1 / -1' } : undefined
                  if (f.kind === 'check') return (
                    <label key={f.key} className="rchk" style={style}>
                      <input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} />{f.label}
                    </label>
                  )
                  return (
                    <label key={f.key} htmlFor={id} style={style}>
                      <span>{f.label}{f.required && <span className="rreq"> *</span>}</span>
                      {f.kind === 'select' ? (
                        <select id={id} className="fi" value={String(form[f.key])} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
                          {f.options!.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </select>
                      ) : (
                        <input id={id} className="fi" type={f.kind === 'number' ? 'number' : 'text'} value={String(form[f.key])} disabled={disabled}
                          placeholder={f.hint} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
                      )}
                      {disabled && <span className="rnote">{target.suggestionId ? '제안한 표현 그대로 넣습니다.' : '표준 항목 키는 바꿀 수 없습니다. 새 항목으로 추가해 주세요.'}</span>}
                    </label>
                  )
                })}
              </div>
            </section>
          )}
          <section className="aps"><h3>{verb} 사유<span className="auto2">필수</span></h3>
            <textarea className="fi" rows={2} aria-label={`${verb} 사유`} value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="예: 현업 멘토 사례, 고객사 파일 이름이 다름" style={{ width: '100%', boxSizing: 'border-box' }} />
            <p className="rnote">고친 내용은 수정 이력에 남고, 다음 검토부터 적용됩니다.</p>
            {!allowed && <p className="aphint">규칙은 엔지니어·승인자만 고칠 수 있습니다. 머리글에서 사용자를 바꿔 주세요.</p>}
            {error && <p className="aphint" role="alert">{error}</p>}
          </section>
        </div>
        <div className="mdf">
          <span className="mdf-n" style={{ marginRight: 'auto' }}>고친 사람 {user?.user_name ?? '—'}</span>
          <button type="button" className="bo" onClick={onClose}>취소</button>
          <button type="button" className={target.mode === 'delete' ? 'bp rdanger' : 'bp'} disabled={!ready || busy} onClick={save}>
            {busy ? '저장하는 중…' : target.mode === 'delete' ? '삭제' : '저장'}</button>
        </div>
      </div>
    </div>
  )
}
