import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { saveFile } from './download'
import { stamp } from './format'
import { useLoad } from './useLoad'
import { useSession } from '../shell/useSession'
import { useToast } from '../ui'
import { PackagePreview } from './PackagePreview'

// 인계 패키지 내려받기·영업에 넘기기 (add-submission-package). 검토 상세 제출본 탭(SCR-08-8)과
// 사업 상세 인계 패키지 창(SCR-05 v4.96)이 같이 쓴다 (update-home-projects).
// 내려받기는 누구나, 영업에 넘기기는 엔지니어만. 넘긴 기록은 /handoffs의 PACKAGE 줄.

// 내려받는 동안 지금 하는 일 (update-package-progress). 서버가 진행을 알려 주지 않아 걸린 시간으로 어림한다
const STAGES: [number, string][] = [[0, '일탈 목록·질의서 Word 만드는 중'], [30, 'TBE 준수표 엑셀 만드는 중'], [60, '데이터시트 엑셀 만드는 중'], [80, 'zip으로 묶는 중']]
const stageText = (pct: number) => [...STAGES].reverse().find(([at]) => pct >= at)![1]

export function PackageActions({ runId, label }: { runId: number; label?: React.ReactNode }) {
  const { user } = useSession()
  const [tick, setTick] = useState(0)
  const [busy, setBusy] = useState<'dl' | 'send' | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [pct, setPct] = useState<number | null>(null)
  const [preview, setPreview] = useState(false)          // 영업 인계 패키지 미리 보기 (add-package-preview)
  const timer = useRef<number | undefined>(undefined)
  const toast = useToast()
  useEffect(() => () => { clearInterval(timer.current) }, [])
  const sent = useLoad(() => api.handoffs(runId), [runId, tick])
  const last = sent.data?.find((h) => h.kind === 'PACKAGE')

  const download = () => {
    if (busy) return
    setBusy('dl')
    setNote(null)
    setPct(0)
    // 받기 전까지 90 %에서 기다린다 (판정 탭 내려받기 ExportOverlay와 같은 방식)
    timer.current = window.setInterval(() => setPct((p) => (p === null ? p : Math.min(90, p + 3))), 120)
    api.downloadPackage(runId).then(({ name, blob }) => {
      clearInterval(timer.current)
      setPct(100)
      setTimeout(() => { setPct(null); setBusy(null); saveFile(name, blob); toast.done(`${name} 를 내려받았습니다.`) }, 350)
    }, (e: Error) => { clearInterval(timer.current); setPct(null); setBusy(null); setNote({ ok: false, text: e.message }) })
  }
  const send = () => {
    if (busy || !user) return
    setBusy('send')
    setNote(null)
    api.handoffPackage(runId, user.user_id).then((res) => {
      setTick((t) => t + 1)
      setNote(res.sent
        ? { ok: true, text: `영업 담당(${res.mail_to})에게 인계 패키지를 보냈습니다. 파일 ${res.files.length - 1}개와 목록.txt` }
        : { ok: false, text: res.error === '주소 없음' ? '영업 담당 메일 주소가 설정되지 않아 보내지 못했습니다. 시스템 담당자에게 문의하세요.' : `보내지 못했습니다: ${res.error}` })
    }, (e: Error) => setNote({ ok: false, text: e.message })).finally(() => setBusy(null))
  }

  return (
    <>
      <div className="subpk">
        <span className="grow">{label ?? <><b>인계 패키지</b> · 일탈 목록·질의서 초안, TBE 준수표, 데이터시트를 zip 하나로 묶어 영업에 넘깁니다.</>}
          {last && (last.mail_error
            ? <span className="c-red"> {stamp(last.sent_at)} 보내지 못함({last.mail_error === '주소 없음' ? '영업 주소 없음' : '발송 실패'})</span>
            : <span> {stamp(last.sent_at)} 영업 담당({last.mail_to})에게 보냄 · {last.sent_by_name}</span>)}</span>
        <button type="button" className="bo" onClick={() => setPreview(true)}>
          <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>visibility</span>미리 보기</button>
        <button type="button" className="bo" onClick={download} disabled={busy !== null}>
          <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>download</span>{busy === 'dl' ? '만드는 중…' : '인계 패키지 내려받기'}</button>
        {user?.role === 'ENGINEER' && (
          <button type="button" className="bp" onClick={send} disabled={busy !== null}>
            <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)' }}>forward_to_inbox</span>
            {busy === 'send' ? '보내는 중…' : last && !last.mail_error ? '다시 넘기기' : '영업에 넘기기'}</button>
        )}
      </div>
      {pct !== null && (
        <div className="pkprog" role="status" aria-live="polite">
          <div className="anbar" role="progressbar" aria-label="인계 패키지 만드는 중" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
            <i style={{ width: `${pct}%` }} /></div>
          <p><b>{stageText(pct)}</b> · {pct} %<span className="en"> · 어림한 진행입니다. 다 만들면 바로 내려받습니다.</span></p>
        </div>
      )}
      {preview && <PackagePreview runId={runId} onClose={() => setPreview(false)} />}
      {note && <p role={note.ok ? 'status' : 'alert'} className={note.ok ? '' : 'c-red'} style={{ margin: '8px 0 0', fontSize: 'var(--fs-sm)' }}>{note.text}</p>}
    </>
  )
}
