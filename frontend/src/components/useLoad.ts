import { useCallback, useEffect, useRef, useState } from 'react'

/** 불러오기 + 다시 불러오기. deps가 바뀌면 다시 부른다. 늦게 온 앞선 응답은 버린다. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const seq = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps)
  const reload = useCallback(() => {
    const mine = ++seq.current
    run().then((d) => { if (mine === seq.current) { setData(d); setError(null) } },
      (e: Error) => { if (mine === seq.current) setError(e.message) })
  }, [run])
  useEffect(reload, [reload])
  return { data, error, reload }
}

/** active인 동안 ms마다 다시 부른다 (처리 중인 검토가 있는 검토 목록·홈) */
export function useRepeat(active: boolean, reload: () => void, ms = 5000) {
  useEffect(() => {
    if (!active) return
    const timer = setInterval(reload, ms)
    return () => clearInterval(timer)
  }, [active, reload, ms])
}
