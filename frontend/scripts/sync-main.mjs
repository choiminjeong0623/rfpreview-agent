// 최신 main 위로 브랜치 맞추기. 여러 세션이 동시에 PR을 올릴 때 늘 겹치는 두 곳만 코드가 푼다:
//   AGENTS.md 2장 change 표 끝 줄 → main 표는 그대로 두고, 이 브랜치가 더한 줄만 표 끝에 "main 마지막 번호 + 1"부터 다시 붙인다
//   docs/추적표.md               → 손으로 풀지 않고 main 쪽을 받은 뒤 npm run trace 로 다시 만든다
// 다른 파일이 겹치면 멈추고 알린다(git rebase --abort 로 되돌릴 수 있음).
// 쓰는 법 (frontend에서, 커밋한 뒤): npm run sync-main          맞추고 커밋까지
//                                    npm run sync-main -- --push  맞춘 뒤 git push --force-with-lease 까지
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('../../', import.meta.url))
const AGENTS = 'AGENTS.md'
const TRACE = 'docs/추적표.md'
// 맞출 기준. 시험할 때만 SYNC_BASE=<브랜치>로 바꾸고 그때는 받아오지 않는다
const BASE = process.env.SYNC_BASE ?? 'origin/main'
const ROW = /^\| (\d+) \| `([^`]+)` \|/

/** 표 줄의 change 이름(archive 경로) */
export const rowKey = (line) => line.match(ROW)?.[2] ?? null

/** text의 change 표에서 mine(change 이름 목록)에 든 줄을 빼고, 표 끝에 마지막 번호 다음부터 다시 붙인다 */
export function renumber(text, mineRows) {
  const lines = text.split('\n')
  const keys = new Set(mineRows.map(rowKey))
  const kept = lines.filter((l) => !(ROW.test(l) && keys.has(rowKey(l))))
  const rows = kept.map((l, i) => (ROW.test(l) ? i : -1)).filter((i) => i >= 0)
  if (!rows.length) throw new Error('AGENTS.md에서 change 표를 찾지 못했습니다.')
  const last = rows[rows.length - 1]
  let n = Number(kept[last].match(ROW)[1])
  const added = mineRows.map((l) => l.replace(ROW, (_, _n, key) => `| ${++n} | \`${key}\` |`))
  return [...kept.slice(0, last + 1), ...added, ...kept.slice(last + 1)].join('\n')
}

/** 이 브랜치가 main에 없는 change 줄 (main 쪽 표에 없는 change 이름) */
export function mineRows(head, main) {
  const onMain = new Set(main.split('\n').map(rowKey).filter(Boolean))
  return head.split('\n').filter((l) => ROW.test(l) && !onMain.has(rowKey(l)))
}

// core.quotepath=false: 한글 파일 이름(docs/추적표.md)을 따옴표 없이 받는다
const git = (...args) => execFileSync('git', ['-c', 'core.quotepath=false', ...args], { cwd: ROOT, encoding: 'utf8' }).trim()
const tryGit = (...args) => { try { return [true, git(...args)] } catch (e) { return [false, `${e.stdout ?? ''}${e.stderr ?? ''}`] } }
const npm = (script) => execFileSync('npm', ['run', '--silent', script], { cwd: join(ROOT, 'frontend'), stdio: 'inherit' })

function main() {
  if (git('status', '--porcelain')) {
    console.error('커밋하지 않은 변경이 있습니다. 먼저 커밋하거나 stash 한 뒤 다시 돌리세요.')
    process.exit(1)
  }
  if (!process.env.SYNC_BASE) git('fetch', 'origin')
  const mine = mineRows(git('show', `HEAD:${AGENTS}`), git('show', `${BASE}:${AGENTS}`))
  console.log(`[sync-main] 이 브랜치의 change 줄 ${mine.length}개`)

  // 다시 올리기: 겹치는 곳이 표·추적표뿐이면 main 쪽을 받고 이어 간다 (줄 번호·추적표는 끝에 다시 만든다)
  let [ok, out] = tryGit('rebase', BASE)
  while (!ok) {
    const conflicted = git('diff', '--name-only', '--diff-filter=U').split('\n').filter(Boolean)
    if (!conflicted.length) { console.error(out); process.exit(1) }
    const other = conflicted.filter((f) => f !== AGENTS && f !== TRACE)
    if (other.length) {
      console.error(`[sync-main] 다른 파일도 겹칩니다: ${other.join(', ')}\n직접 풀고 git rebase --continue, 되돌리려면 git rebase --abort`)
      process.exit(1)
    }
    for (const f of conflicted) { git('checkout', '--ours', '--', f); git('add', '--', f) }
    ;[ok, out] = tryGit('-c', 'core.editor=true', 'rebase', '--continue')
  }

  // 줄 번호 다시 붙이기와 추적표 다시 만들기
  const path = join(ROOT, AGENTS)
  if (mine.length) writeFileSync(path, renumber(readFileSync(path, 'utf8'), mine))
  npm('trace')
  npm('check:trace')
  if (git('status', '--porcelain')) {
    git('add', '--', AGENTS, TRACE)
    git('commit', '-q', '-m', 'chore: 최신 main 위로 맞춤 (AGENTS.md 줄 번호, 추적표)')
  }
  console.log(`[sync-main] ${BASE} 위로 맞춤 끝. ${mine.map((l) => l.match(ROW).slice(1, 3).join(' ')).join(', ') || 'change 줄 없음'}`)
  if (process.argv.includes('--push')) {
    git('push', '--force-with-lease', 'origin', 'HEAD')
    console.log('[sync-main] 올림 (force-with-lease)')
  } else {
    console.log('올리려면: git push --force-with-lease')
  }
}

// 경로에 한글이 있어도 맞도록 URL이 아니라 파일 경로로 비교한다
if (fileURLToPath(import.meta.url) === resolve(process.argv[1] ?? '')) main()
