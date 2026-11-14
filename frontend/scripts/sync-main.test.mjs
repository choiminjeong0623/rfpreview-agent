// sync-main 줄 번호 다시 붙이기 (npm run sync-main). 표 밖 글과 남의 줄은 그대로다.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { mineRows, renumber } from './sync-main.mjs'

const table = (rows) => ['| 단계 | change | 내용 |', '|---|---|---|', ...rows, '', '## 3. 작업 흐름'].join('\n')

test('main이 먼저 같은 번호를 쓴 줄 다시 붙이기', () => {
  const head = table(['| 90 | `archive/a` | A |', '| 91 | `archive/mine` | 내 것 |'])
  const main = table(['| 90 | `archive/a` | A |', '| 91 | `archive/other` | 남의 것 |', '| 92 | `archive/other2` | 남의 것 2 |'])
  const mine = mineRows(head, main)
  assert.deepEqual(mine, ['| 91 | `archive/mine` | 내 것 |'])
  // 다시 올린 뒤 표에는 main 줄과(충돌 때 main 쪽을 받음) 내 줄이 함께 있을 수 있다
  const merged = table(['| 90 | `archive/a` | A |', '| 91 | `archive/other` | 남의 것 |', '| 92 | `archive/other2` | 남의 것 2 |', '| 91 | `archive/mine` | 내 것 |'])
  assert.equal(renumber(merged, mine), table(['| 90 | `archive/a` | A |', '| 91 | `archive/other` | 남의 것 |',
    '| 92 | `archive/other2` | 남의 것 2 |', '| 93 | `archive/mine` | 내 것 |']))
  // 충돌로 내 줄이 빠진 표에도 끝에 붙는다
  assert.equal(renumber(main, mine).split('\n').at(-3), '| 93 | `archive/mine` | 내 것 |')
})

test('내 줄이 여러 개면 순서대로 번호', () => {
  const main = table(['| 10 | `archive/a` | A |'])
  const mine = ['| 11 | `archive/x` | X |', '| 12 | `archive/y` | Y |']
  assert.equal(renumber(main, mine), table(['| 10 | `archive/a` | A |', '| 11 | `archive/x` | X |', '| 12 | `archive/y` | Y |']))
})
