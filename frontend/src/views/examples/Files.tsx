import { useState } from 'react'
import { EXAMPLE_FILES, EXAMPLE_UPLOAD, type FileCat, type SharedFile } from '../../examples/SCR-23'
import { usePageCss } from '../../shell/pageCss'
import { href } from '../../shell/router'
import { ExampleBand } from '../detail/ExampleTab'

// SCR-23 자료실 (목업 v4.57 Files). docs/screens/SCR-23-자료실.md
// 자료실 API가 없어 예시 데이터로만 보여 준다. 올리기·지우기·내려받기는 화면 안에서만 바뀌고 파일은 없다.

const KINDS: ['all' | FileCat, string][] = [['all', '전체'], ['tech', '규격·기술'], ['cust', '고객 자료'], ['guide', '가이드'], ['form', '양식']]
const CAT: Record<FileCat, string> = { tech: '규격·기술', cust: '고객 자료', guide: '가이드', form: '양식' }
const ME = '기술 검토 엔지니어 A'

export function Files() {
  usePageCss('Files')
  const [kind, setKind] = useState<'all' | FileCat>('all')
  const [q, setQ] = useState('')
  const [added, setAdded] = useState<SharedFile[]>([])
  const [gone, setGone] = useState<Record<string, boolean>>({})
  const [got, setGot] = useState<Record<string, boolean>>({})
  const [toast, setToast] = useState('')
  const say = (m: string) => { setToast(m); setTimeout(() => setToast(''), 2800) }
  const needle = q.trim().toLowerCase()
  const rows = [...added, ...EXAMPLE_FILES].filter((f) => !gone[f[3]])
    .filter((f) => (kind === 'all' || f[0] === kind) && (!needle || (f[3] + f[4] + f[5]).toLowerCase().includes(needle)))
  const upload = () => {
    if (added.length) { say('이미 올린 파일입니다.'); return }
    setAdded([EXAMPLE_UPLOAD])
    setKind('all')
    say(`${EXAMPLE_UPLOAD[3]} 를 올렸습니다. (예시 화면이라 저장하지 않습니다)`)
  }

  return (
    <main className="main">
      <ExampleBand />
      <div className="ttl"><h1>자료실</h1><button type="button" className="bp" onClick={upload}><span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>upload</span>파일 올리기</button></div>
      <div className="sh-note"><span className="ms" aria-hidden="true">info</span><span>팀원 누구나 올릴 수 있고, 올린 사람만 고치거나 지울 수 있습니다. 일탈·질의 표준 문구는 파일이 아니라 지식 관리에서 관리합니다.<a href={href('/phrases')}>표준 문구로 이동</a></span></div>
      <div className="sh-bar">
        <div className="seg" role="group" aria-label="분류">
          {KINDS.map(([k, label]) => <button key={k} type="button" className={kind === k ? 'on' : ''} aria-pressed={kind === k} onClick={() => setKind(k)}>{label}</button>)}
        </div>
        <label className="sh-q"><span className="ms" aria-hidden="true">search</span><input placeholder="파일 이름, 설명, 올린 사람 찾기" aria-label="파일 찾기" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <span className="sh-mut" style={{ marginLeft: 'auto' }}>{rows.length}개</span>
      </div>
      <div className="sh-box">
        <div className="fl-tr sh-th"><span /><span>파일</span><span>분류</span><span>올린 사람</span><span>날짜 · 크기</span><span>받은 수</span><span /></div>
        {rows.length === 0 && <div className="sh-empty">조건에 맞는 파일이 없습니다.</div>}
        {rows.map(([cat, ext, x, name, desc, by, date, size, dl]) => (
          <div key={name} className="fl-tr fl-row">
            <span className={`hm-ext ${x}`}>{ext}</span>
            <span className="hm-fn"><b className="ell">{name}</b><span>{desc}</span></span>
            <span className="sh-mut">{CAT[cat]}</span><span className="sh-mut">{by}</span><span className="mono sh-mut">{date} · {size}</span>
            <span className="mono sh-mut">{dl + (got[name] ? 1 : 0)}</span>
            <span className="fl-act">
              <button type="button" className="bo" title="예시 화면이라 실제 파일은 없습니다" onClick={() => setGot({ ...got, [name]: true })}>
                <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>{got[name] ? 'check' : 'download'}</span>{got[name] ? '받음' : '내려받기'}</button>
              {by === ME && <button type="button" className="ib" aria-label={`${name} 지우기`} title="지우기"
                onClick={() => { setGone({ ...gone, [name]: true }); say(`${name} 파일을 지웠습니다.`) }}><span className="ms" aria-hidden="true">delete</span></button>}
            </span>
          </div>
        ))}
      </div>
      {toast && <div className="stt" role="status"><span className="ms" aria-hidden="true">check_circle</span>{toast}</div>}
    </main>
  )
}
