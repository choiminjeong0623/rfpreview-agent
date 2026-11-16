import { describe, expect, it } from 'vitest'
import { daysLeft, dday, filesText, num, reviewTitle, submitBy } from './format'

// 화면 표시 형식 (docs/screens/_공통규칙.md 3장)
const today = new Date(2026, 10, 16) // 2026-11-16 (로컬 시각)

describe('마감 표시', () => {
  it('남은 날: 오늘 0, 지났으면 음수', () => {
    expect(daysLeft('2026-11-16', today)).toBe(0)
    expect(daysLeft('2026-11-19', today)).toBe(3)
    expect(daysLeft('2026-11-15', today)).toBe(-1)
  })

  it('D-n 표시와 색: 3일 이하 빨강, 7일 이하 주황', () => {
    expect(dday('2026-11-16', today)).toEqual({ text: 'D-Day', cls: 'neg' })
    expect(dday('2026-11-19', today)).toEqual({ text: 'D-3', cls: 'neg' })
    expect(dday('2026-11-23', today)).toEqual({ text: 'D-7', cls: 'crit' })
    expect(dday('2026-11-30', today)).toEqual({ text: 'D-14', cls: 'neu' })
    expect(dday('2026-11-14', today)).toEqual({ text: 'D+2', cls: 'neg' })
  })

  it('상신 권장일은 마감 2일 전, 지났으면 late, 마감이 없으면 null', () => {
    expect(submitBy('2026-11-30', today)).toEqual({ text: '11-28', late: false })
    expect(submitBy('2026-11-17', today)).toEqual({ text: '11-15', late: true })
    expect(submitBy('2027-01-01', today)).toEqual({ text: '12-30', late: false })
    expect(submitBy('2027-01-03', today)).toEqual({ text: '2027-01-01', late: false })
    expect(submitBy(null, today)).toBeNull()
  })
})

describe('글 표시', () => {
  it('숫자는 천 단위 쉼표, 값이 없으면 —', () => {
    expect(num(1234567)).toBe('1,234,567')
    expect(num(null)).toBe('—')
    expect(num(undefined)).toBe('—')
  })

  it('파일 여러 개는 "첫 파일 외 n건"', () => {
    expect(filesText('a.docx, b.pdf, c.docx')).toBe('a.docx 외 2건')
    expect(filesText('a.docx')).toBe('a.docx')
    expect(filesText(null)).toBe('')
  })

  it('화면 제목: 사업명 · 검토명, 검토명이 비면 첫 파일 이름, 둘 다 없으면 검토 번호', () => {
    expect(reviewTitle({ project_name: '시연 사업', review_name: '154 kV GIS', run_id: 3 })).toBe('시연 사업 · 154 kV GIS')
    expect(reviewTitle({ project_name: '시연 사업', review_name: null, run_id: 3 })).toBe('시연 사업')
    expect(reviewTitle({ project_name: null, review_name: null, files: 'a.docx, b.docx', run_id: 3 })).toBe('a.docx')
    expect(reviewTitle({ project_name: null, review_name: null, files: null, run_id: 3 })).toBe('검토 #3')
  })
})
