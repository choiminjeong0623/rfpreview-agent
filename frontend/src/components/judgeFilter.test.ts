import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTER, filterQuery, pageOf, parseFilter } from './judgeFilter'

// 판정 거르기를 주소에 담기 (add-judgment-view): 판정 탭 ↔ 판정 상세가 같은 거르기·쪽을 쓴다
describe('judgeFilter', () => {
  it('기본값이면 주소에 아무것도 넣지 않는다', () => {
    expect(filterQuery(DEFAULT_FILTER)).toBe('')
  })

  it('주소로 만들고 다시 읽으면 같은 거르기', () => {
    const f = { f: 'DEVIATION_CANDIDATE', unc: true, q: '정격 전류', type: 'T-TECH', past: true, rev: true, page: 3, size: 20 }
    expect(parseFilter(new URLSearchParams(filterQuery(f).slice(1)))).toEqual(f)
  })

  it('잘못된 쪽 번호·쪽 크기는 기본값으로', () => {
    const f = parseFilter(new URLSearchParams('page=-2&size=abc'))
    expect(f.page).toBe(1)
    expect(f.size).toBe(10)
  })

  it('n번째 줄이 있는 쪽', () => {
    expect(pageOf(1, 10)).toBe(1)
    expect(pageOf(10, 10)).toBe(1)
    expect(pageOf(11, 10)).toBe(2)
    expect(pageOf(0, 10)).toBe(1)
  })
})
