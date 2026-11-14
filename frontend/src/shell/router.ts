import { useEffect, useState } from 'react'

// 화면 주소는 `#/reviews/3`처럼 # 뒤에 둔다 (SCR-00 2장). 새 의존성 없이 hashchange만 쓴다.

/** 지금 화면 주소. `#/reviews/3` → `/reviews/3`, 비어 있으면 `/`. */
export function currentPath(): string {
  const h = window.location.hash.replace(/^#/, '')
  return h.startsWith('/') ? h : '/' + h
}

export function useHashPath(): string {
  const [path, setPath] = useState(currentPath)
  useEffect(() => {
    const on = () => setPath(currentPath())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return path
}

/** replace면 방문 기록을 남기지 않는다 (판정 상세 ↑↓처럼 뒤로 가기가 목록으로 가야 할 때) */
export function navigate(path: string, opts?: { replace?: boolean }) {
  if (opts?.replace) window.location.replace('#' + path)
  else window.location.hash = path
}

/** 주소의 ? 뒤 값. `#/reviews/3?f=x` → f=x */
export function pathQuery(path: string): URLSearchParams {
  return new URLSearchParams(path.split('?')[1] ?? '')
}

export function href(path: string): string {
  return '#' + path
}
