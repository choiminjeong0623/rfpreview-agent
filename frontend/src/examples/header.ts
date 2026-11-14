// 머리글 알림의 예시 데이터 (목업 v4.57 Main 알림 그대로). 알림 API가 없어 예시로만 보여 준다 (SCR-00_공유.md).
// 검토 이름·사람 이름은 목업의 지어낸 값이다. 실제 고객사명·원문은 넣지 않는다.

export type ExampleNotice = { id: string; icon: string; tone: string; title: string; sub: string; t: string; path: string }

export const EXAMPLE_NOTICES: ExampleNotice[] = [
  { id: 'n1', icon: 'error', tone: 'c-red', title: 'RV-2026-030 광양 데이터센터 · 배전반·UPS 설비 분석이 멈췄습니다', sub: '위험 조건 찾기 · 3회 재시도 실패', t: '10-24 15:41', path: '/reviews' },
  { id: 'n2', icon: 'reply', tone: 'c-green', title: '정우진 대리가 회신했습니다', sub: 'RV-2026-025 지급 조건 · 당사 표준과 같음', t: '10-24 16:40', path: '/todo' },
  { id: 'n3', icon: 'schedule', tone: 'c-ora', title: 'RV-2026-027 Cikarang · 115 kV GIS 구매 사양 마감이 지났습니다', sub: '결재 대기 · 마감 10-23', t: '10-24 09:00', path: '/reviews' },
  { id: 'n4', icon: 'rule', tone: 'c-blue', title: 'RV-2026-031 평택 데이터센터 · 22.9 kV 수배전반 교체 판정이 끝났습니다', sub: '일탈 후보 2 · 질의 후보 1', t: '10-24 13:58', path: '/reviews' },
  { id: 'n5', icon: 'mark_email_unread', tone: 'c-ora', title: '한서연 선임이 24시간 넘게 확인하지 않았습니다', sub: 'RV-2026-025 SF6 가스 누설률 카탈로그 값', t: '10-24 10:40', path: '/todo' },
  { id: 'n6', icon: 'task_alt', tone: 'c-green', title: 'RV-2026-028 울산 물류센터 · 중전압 스위치기어·배전 결재가 끝났습니다', sub: '이도현 책임 승인', t: '10-24 10:12', path: '/reviews' },
]

/** 목업처럼 앞의 3건을 읽지 않은 알림으로 둔다. */
export const EXAMPLE_UNREAD = 3
