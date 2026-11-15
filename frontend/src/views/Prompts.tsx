import { Fragment, useState } from 'react'
import { api, type PromptRole, type PromptVersion } from '../api'
import './detail.css'
import { stamp } from '../components/format'
import { useLoad } from '../components/useLoad'
import { usePageCss } from '../shell/pageCss'
import { Badge } from '../ui'

// SCR-26 프롬프트 관리 (목업에 없음, add-prompt-view). docs/screens/SCR-26_공유.md
// 보기만 한다. 프롬프트 글과 판은 코드에서 고치고, 판을 올리면 해시 테스트와 평가를 거친다.

const num = (n: number) => n.toLocaleString('en-US')
const day = (iso: string | null) => (iso ? stamp(iso) : '—')

/** 그 판의 가장 최근 평가: 주 지표 반복 최솟값 */
function Score({ v, evaluated }: { v: PromptVersion; evaluated: boolean }) {
  if (!evaluated) return <span className="dimv">평가 문항 없음</span>
  if (!v.eval) return <span className="dimv">평가 기록 없음</span>
  const e = v.eval
  return (
    <span title={`평가 ${e.eval_id} · 평가셋 ${e.set_name} · ${e.model ?? '모델 모름'}`}>
      {e.metric} <b>{e.min === null ? '—' : `${e.min.toFixed(1)} %`}</b>
      {e.weak && <> <Badge tone="grey" title="사람이 확인하지 않은 정답(Claude 초안)만으로 잰 점수">근거 약함</Badge></>}
      {e.is_baseline && <> <Badge tone="blue">기준선</Badge></>}
      <div className="en">{day(e.created_at)}</div>
    </span>
  )
}

function History({ r }: { r: PromptRole }) {
  return (
    <table className="tbl" style={{ margin: '4px 0 8px' }}>
      <thead><tr>
        <th>판</th><th>처음 쓴 때</th><th>마지막으로 쓴 때</th>
        <th style={{ textAlign: 'right' }}>검토 실행</th><th style={{ textAlign: 'right' }}>AI 호출</th><th>평가</th>
      </tr></thead>
      <tbody>
        {[...r.versions].reverse().map((v) => (
          <tr key={v.version}>
            <td className="en"><b>{v.version}</b>{v.current && <> <Badge tone="green">지금 판</Badge></>}</td>
            <td>{day(v.first_used)}</td>
            <td>{day(v.last_used)}</td>
            <td style={{ textAlign: 'right' }}>{num(v.runs)}</td>
            <td style={{ textAlign: 'right' }}>{num(v.calls)}</td>
            <td><Score v={v} evaluated={r.evaluated} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function Prompts() {
  usePageCss('Products')
  const data = useLoad(() => api.prompts(), [])
  const [open, setOpen] = useState<string | null>(null)
  const roles = data.data?.roles ?? []
  const cur = (r: PromptRole) => r.versions.find((v) => v.current)!

  return (
    <main className="main">
      <div className="idl"><span>보기 전용</span><span>프롬프트 글은 코드에서만 고칩니다{data.data && <> · <span className="en">{data.data.source}</span></>}</span></div>
      <div className="ttl"><div><h1>프롬프트 관리</h1>
        <p className="tb-sub">AI 역할마다 지금 쓰는 프롬프트 판과 판 기록, 판별 평가 점수를 봅니다. 판을 올리면 해시 테스트와 프롬프트 평가를 거칩니다.</p></div></div>
      <div className="kpis">
        <div className="kpi"><div className="l">AI 역할</div><b>{data.data ? roles.length : '—'}</b><div className="s">평가 문항이 있는 역할 {roles.filter((r) => r.evaluated).length}개</div></div>
        <div className="kpi"><div className="l">판을 올린 역할</div><b>{data.data ? roles.filter((r) => r.versions.length > 1).length : '—'}</b><div className="s">쓴 기록에 판이 둘 이상</div></div>
        <div className="kpi"><div className="l">문서 처리 재사용 열쇠</div><b className="en">{data.data?.doc_key ?? '—'}</b><div className="s">문서 분류·문장 구분·유형 판. 바뀌면 같은 파일도 새로 처리</div></div>
      </div>
      <div className="tw" style={{ marginTop: 16 }}>
        <table className="tbl">
          <thead><tr>
            <th>역할</th><th>지금 판</th><th style={{ textAlign: 'right' }}>판 수</th>
            <th style={{ textAlign: 'right' }}>지금 판 검토 실행</th><th>지금 판 마지막 사용</th><th>지금 판 평가</th>
          </tr></thead>
          <tbody>
            {data.data === null && !data.error && <tr><td colSpan={6} className="dimv">불러오는 중…</td></tr>}
            {data.error && <tr><td colSpan={6} className="c-red">{data.error}</td></tr>}
            {roles.map((r) => {
              const c = cur(r)
              return (
                <Fragment key={r.role}>
                  <tr className={open === r.role ? 'cur' : undefined} style={{ cursor: 'pointer' }} aria-expanded={open === r.role}
                    onClick={() => setOpen(open === r.role ? null : r.role)}>
                    <td><b>{r.label}</b> <span className="en">{r.role}</span>
                      {r.in_doc_key && <div className="en" title="이 판이 바뀌면 같은 파일도 새로 처리합니다">재사용 열쇠에 들어감</div>}</td>
                    <td className="en"><b>{r.current}</b></td>
                    <td style={{ textAlign: 'right' }}>{r.versions.length}</td>
                    <td style={{ textAlign: 'right' }}>{num(c.runs)}</td>
                    <td>{day(c.last_used)}</td>
                    <td><Score v={c} evaluated={r.evaluated} /></td>
                  </tr>
                  {open === r.role && <tr className="rlopen"><td colSpan={6}><b>판 기록</b> <span className="en">최근 판이 위</span><History r={r} /></td></tr>}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </main>
  )
}
