import { useState } from 'react'
import { ROLE_NAMES } from '../../components/labels'
import { usePageCss } from '../../shell/pageCss'
import { href } from '../../shell/router'
import { useSession } from '../../shell/useSession'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-24 설정 (목업 v4.57 Settings). docs/screens/SCR-24-설정.md
// 설정 저장 API가 없어 예시 화면이다. 바꾼 값은 화면을 떠나면 처음으로 돌아간다. 내 정보만 머리글에서 고른 사용자를 보인다.

const NOTICES: [string, string, string][] = [
  ['analyzed', '분석이 끝났을 때', '판정 확인할 차례'], ['fail', '분석이 멈췄을 때', ''], ['reply', '협조 요청 회신이 왔을 때', ''],
  ['late', '협조 요청을 24시간 넘게 확인하지 않을 때', ''], ['due', '마감 3일 전', ''], ['ea', '결재가 끝났을 때', '사내 전자결재 결과'],
]
const APPROVERS = ['결재자', '기술 검토 엔지니어 D', '기술 검토 엔지니어 C']
const COSTS = ['견적 담당 A', '견적 담당 B']
const RATIOS = ['15 %', '20 %', '25 %']

export function Settings() {
  usePageCss('Settings')
  const { user } = useSession()
  const [appr, setAppr] = useState(APPROVERS[0])
  const [cost, setCost] = useState(COSTS[0])
  const [ratio, setRatio] = useState('20 %')
  const [nt, setNt] = useState<Record<string, boolean>>(() => Object.fromEntries(NOTICES.map(([k]) => [k, true])))
  const [mail, setMail] = useState(false)
  const [big, setBig] = useState(false)
  const [keepSb, setKeepSb] = useState(true)
  const [toast, setToast] = useState('')
  const save = () => { setToast('예시 화면이라 설정을 저장하지 않습니다.'); setTimeout(() => setToast(''), 3000) }

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl"><h1>설정</h1></div>
      <div className="stc">
        <section className="sts"><div><h2>내 정보</h2><p className="d">사내 인사 정보에서 가져옵니다.</p></div>
          <div className="stf"><div className="stv">{user ? `${user.user_name} · ${ROLE_NAMES[user.role] ?? user.role}` : '사용자 없음'}</div>
            <div className="stv" style={{ color: 'var(--c-muted)' }}>소속 · 사번 (인사 정보 연결 전)</div></div></section>
        <section className="sts"><div><h2>검토 기본값</h2><p className="d">검토 등록할 때 처음 채워지는 값입니다. 건마다 바꿀 수 있습니다.</p></div>
          <div className="stf">
            <label>기본 결재자<br /><select className="fi" value={appr} onChange={(e) => setAppr(e.target.value)} style={{ marginTop: 6 }}>{APPROVERS.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>기본 협조 담당 · 견적<br /><select className="fi" value={cost} onChange={(e) => setCost(e.target.value)} style={{ marginTop: 6 }}>{COSTS.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>확인 필요 비율 기준<br /><select className="fi" value={ratio} onChange={(e) => setRatio(e.target.value)} style={{ marginTop: 6 }}>{RATIOS.map((x) => <option key={x}>{x}</option>)}</select></label>
          </div></section>
        <section className="sts"><div><h2>알림</h2><p className="d">머리글 알림과 메일로 받을 항목을 고릅니다.</p></div>
          <div className="stf">
            {NOTICES.map(([k, label, sub]) => (
              <label key={k} className="stck"><input type="checkbox" checked={nt[k]} onChange={() => setNt({ ...nt, [k]: !nt[k] })} />{label}<span>{sub}</span></label>
            ))}
            <label className="stck" style={{ marginTop: 6 }}><input type="checkbox" checked={mail} onChange={() => setMail(!mail)} />같은 내용을 메일로도 받기<span>예시 메일 주소</span></label>
          </div></section>
        <section className="sts"><div><h2>화면</h2></div>
          <div className="stf"><div>글자 크기</div>
            <div className="stseg" role="group" aria-label="글자 크기">
              <button type="button" className={big ? '' : 'on'} aria-pressed={!big} onClick={() => setBig(false)}>기본</button>
              <button type="button" className={big ? 'on' : ''} aria-pressed={big} onClick={() => setBig(true)}>크게</button>
            </div>
            <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-xs)', color: 'var(--c-muted)' }}>고르는 즉시 모든 화면에 적용되고, 다음에 접속해도 유지됩니다.</p>
            <label className="stck" style={{ marginTop: 6 }}><input type="checkbox" checked={keepSb} onChange={() => setKeepSb(!keepSb)} />메뉴 접힘 상태 기억하기</label>
          </div></section>
        <div className="stact"><a className="bo" href={href('/')}>취소</a><button type="button" className="bp" onClick={save}>저장</button></div>
      </div>
      {toast && <div className="stt" role="status"><span className="ms" aria-hidden="true">check_circle</span>{toast}</div>}
    </main>
  )
}
