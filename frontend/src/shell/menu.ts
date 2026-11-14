// 왼쪽 메뉴. 목업 v4.57의 메뉴 순서·아이콘·이름 그대로 (docs/screens/SCR-00-앱틀.md 1장).

export type MenuKey =
  | 'home' | 'register' | 'projects' | 'reviews' | 'todo' | 'bids'
  | 'products' | 'rules' | 'phrases' | 'eval' | 'runlog'
  | 'team' | 'notice' | 'sysnotice' | 'files' | 'settings'

export type GroupKey = 'rfp' | 'kn' | 'sh'

export type MenuItem = { key: MenuKey; path: string; icon: string; label: string; scr: string }

export const HOME: MenuItem = { key: 'home', path: '/', icon: 'home', label: '홈', scr: 'SCR-03' }
export const SETTINGS: MenuItem = { key: 'settings', path: '/settings', icon: 'settings', label: '설정', scr: 'SCR-24' }

export const GROUPS: { key: GroupKey; icon: string; label: string; items: MenuItem[] }[] = [
  {
    key: 'rfp', icon: 'description', label: 'RFP 관리', items: [
      { key: 'register', path: '/register', icon: 'note_add', label: 'RFP 등록', scr: 'SCR-07' },
      { key: 'projects', path: '/projects', icon: 'business_center', label: '사업 현황', scr: 'SCR-04' },
      { key: 'reviews', path: '/reviews', icon: 'fact_check', label: 'RFP 검토', scr: 'SCR-06' },
      { key: 'todo', path: '/todo', icon: 'forward_to_inbox', label: '협조 요청', scr: 'SCR-13' },
      { key: 'bids', path: '/bids', icon: 'history', label: '입찰 이력', scr: 'SCR-14' },
    ],
  },
  {
    key: 'kn', icon: 'menu_book', label: '지식 관리', items: [
      { key: 'products', path: '/products', icon: 'inventory_2', label: '제품 관리', scr: 'SCR-16' },
      { key: 'rules', path: '/rules', icon: 'rule', label: '규칙 관리', scr: 'SCR-17' },
      { key: 'phrases', path: '/phrases', icon: 'format_quote', label: '표준 문구', scr: 'SCR-18' },
      { key: 'eval', path: '/eval', icon: 'fact_check', label: '정답지·채점', scr: 'SCR-19' },
      { key: 'runlog', path: '/runlog', icon: 'timer', label: '실행 기록', scr: 'SCR-25' },     // 목업에 없음 (add-run-log)
    ],
  },
  {
    key: 'sh', icon: 'groups', label: '팀 공유', items: [
      { key: 'team', path: '/team', icon: 'monitoring', label: '팀 현황', scr: 'SCR-20' },
      { key: 'notice', path: '/notice', icon: 'campaign', label: '공지사항', scr: 'SCR-21' },
      { key: 'sysnotice', path: '/sysnotice', icon: 'dns', label: '시스템 공지', scr: 'SCR-22' },
      { key: 'files', path: '/files', icon: 'folder_open', label: '자료실', scr: 'SCR-23' },
    ],
  },
]

export const ALL_ITEMS: MenuItem[] = [HOME, ...GROUPS.flatMap((g) => g.items), SETTINGS]

export function groupOf(key: MenuKey): GroupKey | null {
  return GROUPS.find((g) => g.items.some((i) => i.key === key))?.key ?? null
}

export function itemOf(key: MenuKey): MenuItem {
  return ALL_ITEMS.find((i) => i.key === key)!
}
