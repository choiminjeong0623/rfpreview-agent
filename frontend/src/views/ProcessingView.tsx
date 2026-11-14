import { useEffect, useState } from 'react'
import './detail.css'
import { api, type RunSummary } from '../api'
import { duration, progress, STALL_MS, stepText } from '../components/progress'
import { useSession } from '../shell/useSession'

// SCR-02 처리 상태 (목업 v4.57 Loading). docs/screens/SCR-02-처리상태.md
// 진행률은 처리 단계 순서와 문서 읽기 단계의 세부 진행으로 센다. 남은 시간은 알 수 없어 보이지 않는다.

export function ProcessingView({ run, onChanged }: { run: RunSummary; onChanged: () => void }) {
  const { user } = useSession()
  const [now, setNow] = useState(() => Date.now())
  const [asking, setAsking] = useState(false)          // "분석 취소"를 한 번 눌러 확인을 묻는 중
  const [error, setError] = useState('')
  const cancelling = Boolean(run.cancel_requested_at)
  const cancel = () => {
    setError('')
    api.cancelRun(run.run_id, user?.user_id ?? null).then(() => { setAsking(false); onChanged() },
      (e: Error) => setError(e.message))
  }
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)     // 지난 시간을 1초마다 다시 센다
    return () => clearInterval(timer)
  }, [])
  const pct = progress(run)
  const found = [run.documents && `문서 ${run.documents}개`, run.requirements && `요구사항 ${run.requirements}개`].filter(Boolean).join(' · ')
  const stalled = now - Date.parse(run.step_updated_at) > STALL_MS
  const hint = run.llm_model
    ? 'AI를 쓰는 분석은 문서가 크면 15분 넘게 걸릴 수 있어요. 이 창을 닫아도 분석은 계속됩니다.'
    : 'AI 없이 규칙으로만 분석해 보통 1분 안에 끝나요.'
  return (
    <div style={{ position: 'relative', minHeight: '60vh', marginTop: 20 }}>
      <div className="ldo" style={{ position: 'absolute', background: 'var(--c-white)' }}>
        <div className="ldc">
          <img src="/img/spec2win-color.png" alt="Spec2Win" width={200} height={40} />
          <div className="ldrow">
            <div className="ldbar" role="progressbar" aria-label="RFP 분석" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
              <div className="ldfill" style={{ width: `${pct}%` }} />
            </div>
            <span className="ldpct">{pct}%</span>
          </div>
          <div className="ldtx" aria-live="polite">{stepText(run)}{found && ` · ${found}`}</div>
          <div className="ldtx ldtime" style={{ marginTop: 4 }}>지난 시간 {duration(now - Date.parse(run.started_at))}</div>
          <div className="ldtx" style={{ marginTop: 4, fontSize: 12 }}>{hint}</div>
          {stalled && (
            <p role="alert" className="ldtx" style={{ marginTop: 12, color: 'var(--c-red)' }}>
              10분 넘게 진행이 없습니다. 분석 중에 백엔드가 꺼졌다면 이 검토는 끝나지 않으니 분석을 취소한 뒤 다시 시도해 주세요.
            </p>
          )}
          {/* 분석 취소 (add-run-control): 한 번 더 확인한 뒤 요청한다. 처리는 다음 진행 기록에서 멈춘다 */}
          <div className="ldcancel">
            {cancelling ? <span className="ldtx" role="status">취소하는 중… 지금 하던 일을 마치면 멈춥니다.</span>
              : asking ? <>
                <span className="ldtx">분석을 멈출까요? 나중에 실패 화면에서 다시 시도할 수 있습니다.</span>
                <button type="button" className="bp sm" onClick={cancel}>취소하기</button>
                <button type="button" className="bo sm" onClick={() => setAsking(false)}>계속 분석</button>
              </> : <button type="button" className="bo sm" onClick={() => setAsking(true)}>분석 취소</button>}
            {error && <span className="ldtx" role="alert" style={{ color: 'var(--c-red)' }}>{error}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
