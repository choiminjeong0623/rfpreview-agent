import { api, type Health } from '../api'
import { useLoad } from './useLoad'

// AI 사용 방식 한 줄 (add-ai-mode, NFR-07). 목업에 없음 — docs/screens/SCR-25_공유.md
// 키·사내 주소는 서버가 주지 않는다. 방식은 운영자가 설정(RFP_AI_MODE)으로만 바꾼다.

function aiModeText(h: Health): string {
  if (h.ai_mode === 'GEMINI') return `AI: Gemini ${h.ai_model ?? ''} · 문장을 외부 AI로 보냅니다`
  if (h.ai_mode === 'LOCAL') return `AI: 사내 모델 ${h.ai_model ?? ''} · 외부로 보내지 않습니다`
  return 'AI 사용 안 함 · 외부로 보내지 않고 규칙 기반으로만 분석합니다'
}

export function AiModeLine({ as = 'p' }: { as?: 'p' | 'span' }) {
  const h = useLoad(() => api.health(), [])
  if (!h.data) return null
  const Tag = as
  return (
    <Tag className={h.data.external_send ? 'c-ora' : 'dimv'} data-testid="ai-mode">
      <span className="ms" aria-hidden="true" style={{ fontSize: 'var(--ic-s)', verticalAlign: 'middle' }}>
        {h.data.external_send ? 'cloud_upload' : 'lock'}</span> {aiModeText(h.data)}
    </Tag>
  )
}
