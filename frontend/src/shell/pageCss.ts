import { useEffect } from 'react'

// 화면별 목업 CSS (docs/screens/_디자인.md 1장). Main.css는 늘 깔려 있고, 다른 화면은 보이는 동안만 그 화면 CSS를 더한다.
// Main.css(main.tsx)와 SummaryV496.css(SummaryBox.tsx)는 정적 import로 늘 실리므로 여기서 빼 같은 CSS가 빌드에 두 번 들어가지 않게 한다.
const SHEETS = import.meta.glob<string>(
  ['../styles/pages/*.css', '!../styles/pages/Main.css', '!../styles/pages/SummaryV496.css'],
  { query: '?inline', import: 'default' },
)

export type PageKey = 'Main' | 'Register' | 'Detail' | 'Wait' | 'Fail' | 'Todo' | 'Home' | 'Products' | 'Rules' | 'Tbe' | 'Datasheet' | 'Bids' | 'BidView' | 'Projects' | 'Project' | 'Phrases' | 'Eval' | 'Team' | 'Notice' | 'SysNotice' | 'Files' | 'Settings' | 'Login' | 'DetailV496' | 'JudgeView' | 'TodoV496' | 'ProductsV496' | 'HomeV496' | 'ProjectsV496' | 'ProjectV496'

export function usePageCss(key: PageKey) {
  useEffect(() => {
    if (key === 'Main') return
    let alive = true
    const style = document.createElement('style')
    style.dataset.mockup = key
    SHEETS[`../styles/pages/${key}.css`]?.().then((css) => { if (alive) style.textContent = css })
    document.head.appendChild(style)
    return () => { alive = false; style.remove() }
  }, [key])
}
