import { describe, expect, it } from 'vitest'
import { pageItems } from './pageItems'

// 표 아래 쪽 번호 줄 (update-detail-layout): 9쪽 이하는 모두, 넘으면 처음·끝과 지금 쪽 근처만, 빈 곳은 "…"(null)
describe('pageItems', () => {
  it('9쪽 이하는 모든 쪽 번호', () => {
    expect(pageItems(1, 1)).toEqual([1])
    expect(pageItems(4, 9)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9])
  })

  it('처음 쪽 근처는 앞쪽 번호를 이어 보이고 끝 앞에만 …', () => {
    expect(pageItems(1, 20)).toEqual([1, 2, 3, 4, 5, 6, null, 20])
  })

  it('가운데 쪽은 앞뒤 2쪽과 양쪽 …', () => {
    expect(pageItems(10, 20)).toEqual([1, null, 8, 9, 10, 11, 12, null, 20])
  })

  it('끝 쪽 근처는 끝쪽 번호를 이어 보이고 처음 뒤에만 …', () => {
    expect(pageItems(20, 20)).toEqual([1, null, 15, 16, 17, 18, 19, 20])
  })

  it('보이는 번호는 늘 1과 마지막 쪽을 포함하고 지금 쪽을 포함한다', () => {
    for (let pages = 1; pages <= 30; pages++) {
      for (let page = 1; page <= pages; page++) {
        const items = pageItems(page, pages)
        expect(items[0]).toBe(1)
        expect(items.at(-1)).toBe(pages)
        expect(items).toContain(page)
        const nums = items.filter((n): n is number => n !== null)
        expect([...nums].sort((a, b) => a - b)).toEqual(nums)
      }
    }
  })
})
