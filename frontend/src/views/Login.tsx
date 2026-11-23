import { useEffect, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react'
import { api } from '../api'
import { usePageCss } from '../shell/pageCss'
import { currentPath, navigate, pathQuery } from '../shell/router'
import { useSession } from '../shell/useSession'

// SCR-01 로그인 (목업 v4.57 Login). docs/screens/SCR-01-로그인.md
// 실제 로그인 (add-session-auth): 아이디·비밀번호를 서버에 보내 세션 쿠키를 받고, 주소의 next(없으면 홈)로 간다.
// 세션이 없는 화면에서 API가 401을 주면 이 화면으로 온다. 접근 권한 요청 탭은 예시로 남아 보내지 않는다.

type Card = { icon: string; label: string; dot?: string } | { tag: string; label: string; dir: 'ltr' | 'rtl'; lang: string }
type Slide = { h: string; art: 'globe' | 'check' | 'calc' | 'target'; cards: Card[] }

const SLIDES: Slide[] = [
  { h: '여러 언어 문서를 읽는다', art: 'globe',
    cards: [{ tag: 'EN', label: 'Rated normal current 4,000 A', dir: 'ltr', lang: 'en' }, { tag: 'VI', label: 'Dòng cắt định mức 40 kA', dir: 'ltr', lang: 'vi' },
      { tag: 'AR', label: 'درجة الحرارة المحيطة ⁦40 °C⁩', dir: 'rtl', lang: 'ar' }] },
  { h: '판정한다', art: 'check', cards: [{ icon: 'find_in_page', label: '원문 7161행 "4000 A"' }, { icon: 'inventory_2', label: '제품값 3,150 A (LSG-145-40)' }, { icon: 'report', label: '일탈 후보', dot: 'var(--c-red-dot)' }] },
  { h: '돈으로 본다', art: 'calc', cards: [{ icon: 'gavel', label: '지체상금 조항', dot: 'var(--c-red-dot)' }, { icon: 'warning', label: '포괄 조항 1건', dot: 'var(--c-orange-dot)' }, { icon: 'payments', label: '평가 가격 영업 권한 필요' }] },
  { h: '이기는 제안을 만든다', art: 'target', cards: [{ icon: 'description', label: '일탈 목록 초안' }, { icon: 'help', label: '질의서 초안' }, { icon: 'trending_up', label: '제안 포인트 2건', dot: 'var(--c-green-dot)' }] },
]
const MAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const ARTS: Record<Slide['art'], ReactNode> = {
  globe: (
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle className="glow" cx="62" cy="62" r="56" />
      <circle className="ln" cx="42" cy="56" r="28" />
      <ellipse className="ln mer" cx="42" cy="56" rx="12" ry="28" />
      <path className="ln" d="M14 56 H70 M19 42 H65 M19 70 H65" />
      <path className="ln ac flow" d="M46 24 C62 8 86 12 94 34" />
      <path className="ln ac flowh" d="M94 34 l-7 -2 M94 34 l2 -7" />
      <path className="ln bgfill" d="M62 46 H92 L106 60 V110 H62 Z" />
      <path className="ln" d="M92 46 V60 H106" />
      <path className="ln dr d1" d="M70 70 H98" />
      <path className="ln dr d2" d="M70 80 H94" />
      <path className="ln dr d3" d="M70 90 H98" />
      <g className="ko"><rect className="ln ac bgfill" x="48" y="94" width="24" height="14" rx="3" /><text className="kot" x="60" y="104" textAnchor="middle">KO</text></g>
    </svg>
  ),
  check: (
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle className="glow" cx="60" cy="62" r="56" />
      <rect className="ln" x="24" y="18" width="72" height="94" rx="8" />
      <rect className="ln ac bgfill" x="44" y="10" width="32" height="16" rx="4" />
      <rect className="ln" x="35" y="38" width="14" height="14" rx="3" />
      <rect className="ln" x="35" y="61" width="14" height="14" rx="3" />
      <rect className="ln" x="35" y="84" width="14" height="14" rx="3" />
      <path className="ln dr d1" d="M57 45 H85" />
      <path className="ln dr d2" d="M57 68 H80" />
      <path className="ln dr d3" d="M57 91 H83" />
      <path className="ln ac ck c1" d="M38 45 l4 4 l8 -9" />
      <path className="ln ac ck c2" d="M38 68 l4 4 l8 -9" />
      <path className="ln ac ck c3" d="M38 91 l4 4 l8 -9" />
    </svg>
  ),
  // 계산기 화면의 금액은 영업 권한이 필요한 값이라 자리표시로 둔다 (SCR-01_공유.md)
  calc: (
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle className="glow" cx="60" cy="62" r="56" />
      <rect className="ln" x="28" y="10" width="64" height="100" rx="8" />
      <rect className="ln ac" x="37" y="20" width="46" height="24" rx="3" />
      <text className="dg" x="78" y="36" textAnchor="end"><tspan className="g1">$•,</tspan><tspan className="g2">•••,</tspan><tspan className="g3">•••</tspan></text>
      <circle className="ln bt b1" cx="44" cy="58" r="5" /><circle className="ln bt b2" cx="60" cy="58" r="5" /><circle className="ln bt b3" cx="76" cy="58" r="5" />
      <circle className="ln bt b4" cx="44" cy="74" r="5" /><circle className="ln bt b5" cx="60" cy="74" r="5" /><circle className="ln bt b6" cx="76" cy="74" r="5" />
      <circle className="ln bt b7" cx="44" cy="90" r="5" /><circle className="ln bt b8" cx="60" cy="90" r="5" />
      <rect className="ln ac bt b9" x="71" y="85" width="10" height="16" rx="5" />
    </svg>
  ),
  target: (
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle className="glow" cx="56" cy="64" r="56" />
      <circle className="ln" cx="56" cy="64" r="40" />
      <circle className="ln" cx="56" cy="64" r="27" />
      <circle className="ln" cx="56" cy="64" r="14" />
      <circle className="dot" cx="56" cy="64" r="5" />
      <circle className="rip" cx="56" cy="64" r="14" />
      <g className="arw">
        <path className="ln" d="M60 60 L100 20" />
        <path className="ln ac" d="M100 20 l9 -1 M100 20 l1 -9 M94 26 l9 -1 M94 26 l1 -9" />
        <path className="ln ac" d="M60 60 l9 -2 M60 60 l2 -9" />
      </g>
    </svg>
  ),
}

function reducedMotion() {
  try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return false }
}

function SlideCard({ c, k }: { c: Card; k: number }) {
  if ('tag' in c) {
    return <div className={`card c${k + 1} doc ic`}><span className="ci"><span className="lt">{c.tag}</span></span><span className="cl" dir={c.dir} lang={c.lang}>{c.label}</span></div>
  }
  return (
    <div className={`card c${k + 1} ic`}><span className="ci"><span className="ms">{c.icon}</span></span>
      {c.dot && <i className="cdot" style={{ background: c.dot }} />}<span className="cl" dir="auto" lang="ko">{c.label}</span></div>
  )
}

export function Login() {
  usePageCss('Login')
  const { refresh } = useSession()
  const [big, setBig] = useState(false)
  const [slide, setSlide] = useState(0)
  const [paused, setPaused] = useState(reducedMotion)
  const [hover, setHover] = useState(false)
  const [tab, setTab] = useState<'login' | 'req'>('login')
  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const [req, setReq] = useState({ name: '', mail: '', role: 'eng', why: '' })
  const [reqTried, setReqTried] = useState(false)
  const [reqSent, setReqSent] = useState(false)

  useEffect(() => {
    if (paused || hover) return
    const t = setInterval(() => setSlide((n) => (n + 1) % SLIDES.length), 5000)
    return () => clearInterval(t)
  }, [paused, hover])

  const idErr = tried && !id.trim()
  const pwErr = tried && !pw
  const nameErr = reqTried && !req.name.trim()
  const mailErr = reqTried && !MAIL.test(req.mail.trim())
  const doLogin = async () => {
    if (!id.trim() || !pw) { setTried(true); return }
    setTried(false)
    setFailed(null)
    setBusy(true)
    try {
      await api.login(id.trim(), pw)
    } catch (e) {
      // 틀린 비밀번호·없는 아이디는 서버가 같은 문장("아이디 또는 비밀번호가 맞지 않습니다.")을 준다
      setFailed((e as Error).message)
      setBusy(false)
      return
    }
    refresh()
    const next = pathQuery(currentPath()).get('next')
    navigate(next && next.startsWith('/') && !next.startsWith('/login') ? next : '/', { replace: true })
  }
  const onEnter = (e: KeyboardEvent) => { if (e.key === 'Enter' && !busy) void doLogin() }
  const doReq = () => {
    if (!req.name.trim() || !MAIL.test(req.mail.trim())) { setReqTried(true); return }
    setReqTried(false)
    setReqSent(true)
  }
  const goLogin = () => { setTab('login'); setReqSent(false) }
  const noop = (e: MouseEvent) => e.preventDefault()

  return (
    <div className={big ? 'fs-l' : 'fs-s'}>
      <div className="wrap">
        <section className="lp" aria-label="Spec2Win 소개" aria-roledescription="carousel">
          <div className="lpfx" aria-hidden="true"><i className="au a1" /><i className="au a2" /><i className="au a3" /></div>
          <div className="brand">
            <div className="plate"><img src="/img/spec2win-white.png" alt="Spec2Win" width={151} height={30} /></div>
            <div className="prod"><span>RFP 기술 검토 지원 시스템</span></div>
          </div>
          <div className="stage" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}>
            <div className="vp" aria-hidden="true">
              <div className="track" style={{ transform: `translateX(${-100 * slide}%)` }}>
                {SLIDES.map((s, i) => (
                  <div key={s.h} className={'slide' + (slide === i ? ' on' : '')}>
                    <div className="ill">
                      <div className="art">{ARTS[s.art]}</div>
                      {s.cards.map((c, k) => <SlideCard key={k} c={c} k={k} />)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="bars" role="tablist" aria-label="소개 넘기기">
              {SLIDES.map((s, i) => <button key={s.h} type="button" className={slide === i ? 'on' : ''} role="tab" aria-selected={slide === i} aria-label={`${i + 1}. ${s.h}`} onClick={() => setSlide(i)} />)}
              <button type="button" className="pp" onClick={() => setPaused(!paused)} aria-label={paused ? '자동 넘김 켜기' : '자동 넘김 멈춤'} title={paused ? '자동 넘김 켜기' : '자동 넘김 멈춤'}>
                <span className="ms" aria-hidden="true">{paused ? 'play_arrow' : 'pause'}</span></button>
            </div>
          </div>
        </section>

        <main className="rp">
          <div className="rtop">
            <div className="fsz" role="group" aria-label="글자 크기">
              <button type="button" className={big ? '' : 'on'} onClick={() => setBig(false)} aria-pressed={!big} title="기본 글씨">가</button>
              <button type="button" className={big ? 'on' : ''} onClick={() => setBig(true)} aria-pressed={big} title="큰 글씨">가</button>
            </div>
            <a className="help" href="#" onClick={noop}><span className="ms" aria-hidden="true">help</span>도움말</a>
          </div>

          <div className="mid">
            <div className="form">
              {(
                <>
                  <h1 className="lh"><img src="/img/spec2win-color.png" alt="Spec2Win" width={141} height={28} /><span>로그인</span></h1>
                  <p className="sub">아이디와 비밀번호로 로그인해 주세요.</p>
                  {/* 앱 틀 CSS(Main.css)의 .tabs 여백이 겹치지 않게 지운다 */}
                  <div className="tabs" role="tablist" aria-label="로그인 방법" style={{ padding: 0, gap: 0 }}>
                    <button type="button" className={tab === 'login' ? 'on' : ''} role="tab" aria-selected={tab === 'login'} onClick={goLogin}>로그인</button>
                    <button type="button" className={tab === 'req' ? 'on' : ''} role="tab" aria-selected={tab === 'req'} onClick={() => setTab('req')}>접근 권한 요청</button>
                  </div>

                  {tab === 'login' && (
                    <>
                      {(idErr || pwErr) && (
                        <div className="alert err" role="alert"><span className="ms" aria-hidden="true">error</span><div><b>입력하지 않은 칸이 있습니다</b><span>빨간 칸을 채운 뒤 다시 로그인해 주세요.</span></div></div>
                      )}
                      {failed && !idErr && !pwErr && (
                        <div className="alert err" role="alert"><span className="ms" aria-hidden="true">error</span><div><b>{failed}</b><span>아이디와 비밀번호를 확인한 뒤 다시 로그인해 주세요.</span></div></div>
                      )}
                      <div className="field">
                        <label htmlFor="uid">아이디</label>
                        <div className={'inp' + (idErr ? ' bad' : '')}><input id="uid" autoComplete="username" value={id} onChange={(e) => setId(e.target.value)} onKeyDown={onEnter} placeholder="예: engineer" aria-invalid={idErr} aria-describedby="uid-err" /></div>
                        {idErr && <div className="ferr" id="uid-err"><span className="ms" aria-hidden="true">error</span>아이디를 입력해 주세요.</div>}
                      </div>
                      <div className="field">
                        <label htmlFor="upw">비밀번호</label>
                        <div className={'inp pw' + (pwErr ? ' bad' : '')}>
                          <input id="upw" type={showPw ? 'text' : 'password'} autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} onKeyDown={onEnter} placeholder="비밀번호" aria-invalid={pwErr} aria-describedby="upw-err" />
                          <button type="button" className="eye" onClick={() => setShowPw(!showPw)} aria-label={showPw ? '비밀번호 숨기기' : '비밀번호 보기'} title={showPw ? '비밀번호 숨기기' : '비밀번호 보기'}>
                            <span className="ms" aria-hidden="true" style={{ fontSize: 18 }}>{showPw ? 'visibility_off' : 'visibility'}</span></button>
                        </div>
                        {pwErr && <div className="ferr" id="upw-err"><span className="ms" aria-hidden="true">error</span>비밀번호를 입력해 주세요.</div>}
                      </div>
                      <div className="row"><span>비밀번호를 잊었으면 관리자에게 문의해 주세요.</span></div>
                      <button type="button" className="go" onClick={() => void doLogin()} disabled={busy}>{busy && <span className="spin" aria-hidden="true" />}{busy ? '로그인 중…' : '로그인'}</button>
                    </>
                  )}

                  {tab === 'req' && (reqSent ? (
                    <>
                      <div className="alert ok" role="status"><span className="ms" aria-hidden="true">check_circle</span><div><b>요청을 보냈습니다</b><span>관리자가 확인하면 이 계정으로 로그인할 수 있습니다. (예시 화면이라 실제로 보내지 않습니다)</span></div></div>
                      <button type="button" className="sso" onClick={goLogin}>로그인으로 돌아가기</button>
                    </>
                  ) : (
                    <>
                      <div className="alert info"><span className="ms" aria-hidden="true">info</span><div><span>관리자 승인 후 사용할 수 있습니다.</span></div></div>
                      <div className="field">
                        <label htmlFor="rname">이름</label>
                        <div className={'inp' + (nameErr ? ' bad' : '')}><input id="rname" value={req.name} onChange={(e) => setReq({ ...req, name: e.target.value })} placeholder="이름" /></div>
                        {nameErr && <div className="ferr"><span className="ms" aria-hidden="true">error</span>이름을 입력해 주세요.</div>}
                      </div>
                      <div className="field">
                        <label htmlFor="rmail">회사 이메일</label>
                        <div className={'inp' + (mailErr ? ' bad' : '')}><input id="rmail" type="email" value={req.mail} onChange={(e) => setReq({ ...req, mail: e.target.value })} placeholder="name@company.com" /></div>
                        {mailErr && <div className="ferr"><span className="ms" aria-hidden="true">error</span>회사 이메일 형식으로 입력해 주세요. 예: name@company.com</div>}
                      </div>
                      <div className="field">
                        <label htmlFor="rrole">맡은 일</label>
                        <div className="inp"><select id="rrole" value={req.role} onChange={(e) => setReq({ ...req, role: e.target.value })}>
                          <option value="eng">기술 검토 엔지니어</option><option value="appr">결재자</option><option value="recv">견적·품질·영업 담당 (협조 요청 받음)</option></select></div>
                      </div>
                      <div className="field">
                        <label htmlFor="rwhy">요청 사유 <span style={{ color: 'var(--c-disabled)', fontWeight: 400 }}>(선택)</span></label>
                        <div className="inp"><textarea id="rwhy" value={req.why} onChange={(e) => setReq({ ...req, why: e.target.value })} placeholder="예: 115 kV GIS 입찰 기술 검토 담당" /></div>
                      </div>
                      <button type="button" className="go" onClick={doReq}>요청 보내기</button>
                    </>
                  ))}
                </>
              )}
            </div>
          </div>

          <div className="rfoot">
            <span>Spec2Win · RFP 기술 검토 지원 시스템</span>
            <span><a href="#" onClick={noop}>개인정보 처리 안내</a> · <a href="#" onClick={noop}>이용 안내</a></span>
          </div>
        </main>
      </div>
    </div>
  )
}
