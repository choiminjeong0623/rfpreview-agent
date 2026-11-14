import { createContext, useContext } from 'react'

// 알림 쌓기의 공용 부분 (Toasts.tsx가 그린다)
export type ToastKind = 'success' | 'info' | 'error'
export const TOAST_MS = 4000
/** 알림에 붙이는 링크 하나 (예: 검토 열기). 누르면 알림이 닫힌다 */
export type ToastLink = { href: string; label: string }
type Api = {
  /** 시스템 알림·오류: 오른쪽 위에 쌓는다 (분석 끝남, 저장 실패 등) */
  show: (text: string, kind?: ToastKind, link?: ToastLink) => void
  /** 동작 결과: 사용자가 방금 누른 것의 결과를 아래 가운데에 하나만 (update-action-toast-place) */
  done: (text: string, link?: ToastLink) => void
}

export const ToastCtx = createContext<Api>({ show: () => {}, done: () => {} })

/** 화면에서 알림 띄우기: const toast = useToast(); toast.done('저장했습니다'), 오류는 toast.show(문장, 'error') */
export function useToast() {
  return useContext(ToastCtx)
}
