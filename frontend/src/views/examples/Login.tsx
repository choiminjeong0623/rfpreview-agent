import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { ROLE_NAMES } from '../../components/labels'
import { usePageCss } from '../../shell/pageCss'
import { navigate } from '../../shell/router'
import { useSession } from '../../shell/useSession'
import { useFakeLoad } from './useFakeLoad'

// SCR-01 로그인 (목업 v4.57 Login). docs/screens/SCR-01-로그인.md
// 앱에는 로그인이 없다. 주소 #/login으로만 열고, 로그인을 누르면 홈으로 간다. 사용자는 머리글에서 고른다.
// 아이디·비밀번호는 어디에도 보내지 않고, 접근 권한 요청도 보내지 않는다 (예시 화면 규칙).

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
const LOGIN_STAGES: [number, string][] = [[0, '사내 계정 확인 중'], [30, '사용 권한 확인 중'], [55, '내 할 일 불러오는 중'], [80, '홈 화면 준비 중']]
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
  const { user } = useSession()
  const loader = useFakeLoad()
  const [big, setBig] = useState(false)
  const [slide, setSlide] = useState(0)
  const [paused, setPaused] = useState(reducedMotion)
  const [hover, setHover] = useState(false)
  const [tab, setTab] = useState<'login' | 'req'>('login')
  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [keep, setKeep] = useState(true)
  const [tried, setTried] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
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
  const finish = () => {
    setBusy(true)
    loader.start('로그인', LOGIN_STAGES, '', () => { setBusy(false); setDone(true); navigate('/') })
  }
  const doLogin = () => {
    if (!id.trim() || !pw) { setTried(true); return }
    setTried(false)
    finish()
  }
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
              {done ? (
                <div className="done" role="status">
                  <div className="ic"><span className="ms" aria-hidden="true">check</span></div>
                  <h2>로그인했습니다</h2>
                  <p>{user ? `${user.user_name} · ${ROLE_NAMES[user.role] ?? user.role}` : '머리글에서 사용자를 고르세요'}</p>
                  <a className="go" href="#/">홈으로 이동<span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>arrow_forward</span></a>
                </div>
              ) : (
                <>
                  <h1 className="lh"><img src="/img/spec2win-color.png" alt="Spec2Win" width={141} height={28} /><span>로그인</span></h1>
                  <p className="sub">사내 계정으로 로그인해 주세요.</p>
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
                      <button type="button" className="sso" onClick={finish} disabled={busy}><span className="ms" aria-hidden="true">badge</span>사내 계정(SSO)으로 계속</button>
                      <div className="or">또는 사번으로 로그인</div>
                      <div className="field">
                        <label htmlFor="uid">사번 또는 회사 이메일</label>
                        <div className={'inp' + (idErr ? ' bad' : '')}><input id="uid" autoComplete="username" value={id} onChange={(e) => setId(e.target.value)} placeholder="예: 20261234" aria-invalid={idErr} aria-describedby="uid-err" /></div>
                        {idErr && <div className="ferr" id="uid-err"><span className="ms" aria-hidden="true">error</span>사번 또는 회사 이메일을 입력해 주세요.</div>}
                      </div>
                      <div className="field">
                        <label htmlFor="upw">비밀번호</label>
                        <div className={'inp pw' + (pwErr ? ' bad' : '')}>
                          <input id="upw" type={showPw ? 'text' : 'password'} autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="비밀번호" aria-invalid={pwErr} aria-describedby="upw-err" />
                          <button type="button" className="eye" onClick={() => setShowPw(!showPw)} aria-label={showPw ? '비밀번호 숨기기' : '비밀번호 보기'} title={showPw ? '비밀번호 숨기기' : '비밀번호 보기'}>
                            <span className="ms" aria-hidden="true" style={{ fontSize: 18 }}>{showPw ? 'visibility_off' : 'visibility'}</span></button>
                        </div>
                        {pwErr && <div className="ferr" id="upw-err"><span className="ms" aria-hidden="true">error</span>비밀번호를 입력해 주세요.</div>}
                      </div>
                      <div className="row">
                        <label className="chk"><input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />로그인 상태 유지</label>
                        <a href="#" onClick={noop}>비밀번호를 잊으셨나요?</a>
                      </div>
                      <button type="button" className="go" onClick={doLogin} disabled={busy}>{busy && <span className="spin" aria-hidden="true" />}{busy ? '로그인 중…' : '로그인'}</button>
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
      {loader.view}
    </div>
  )
}
