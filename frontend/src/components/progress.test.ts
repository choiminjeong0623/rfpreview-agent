import { describe, expect, it } from 'vitest'
import type { RunListItem } from '../api'
import { duration, isStalled, progress, stepLine, stepText } from './progress'

// 처리 진행률 (update-processing-progress, update-list-progress, add-run-queue)
type Detail = NonNullable<RunListItem['step_detail']>
const at = (step: string, step_detail: Detail | null = null, queue_position: number | null = null) => ({ step, step_detail, queue_position }) as Pick<RunListItem, 'step' | 'step_detail'> & { queue_position: number | null }
const detail = (p: Partial<Detail>) => ({ part: 'type', file_index: 1, file_count: 1, done: 0, total: 0, ...p }) as Detail

describe('progress: 끝난 비율', () => {
  it('시작 전 0, 문서 읽기는 2~85, 마지막 단계도 99를 넘지 않는다', () => {
    expect(progress(at('created'))).toBe(0)
    expect(progress(at('documents', detail({ part: 'classify' })))).toBe(2)
    expect(progress(at('documents', detail({ part: 'type', done: 10, total: 10 })))).toBe(85)
    expect(progress(at('assign'))).toBeLessThanOrEqual(99)
  })

  it('단계가 뒤로 갈수록 비율이 줄지 않는다', () => {
    const steps = ['created', 'documents', 'pairs', 'risks', 'judge', 'meaning', 'check', 'warranty', 'loss', 'outputs', 'proposals', 'assign']
    const values = steps.map((s) => progress(at(s)))
    expect([...values].sort((a, b) => a - b)).toEqual(values)
  })

  it('파일이 여럿이면 파일 순번으로 나눈다: 두 파일 중 첫 파일을 다 읽으면 문서 읽기의 절반', () => {
    expect(progress(at('documents', detail({ file_index: 2, file_count: 2, part: 'classify' })))).toBe(Math.round(2 + 83 * 0.5))
  })
})

describe('진행 문장', () => {
  it('문서 읽기 단계는 세부 일과 건수, 파일 순번', () => {
    expect(stepText(at('documents', detail({ part: 'type', done: 480, total: 3397, file_index: 1, file_count: 2 }))))
      .toBe('AI로 유형 붙이는 중 480 / 3,397건 · 파일 1 / 2')
  })

  it('대기열에서 기다리면 순번만', () => {
    expect(stepText(at('created', null, 2))).toBe('대기 중 2번째')
    expect(stepLine(at('created', null, 2))).toBe('대기 중 2번째')
  })

  it('목록 줄은 "n/11 단계 · p %"', () => {
    expect(stepLine(at('judge'))).toMatch(/^4\/11 제품과 비교해 판정하는 중 · \d+ %$/)
  })

  it('걸린 시간은 초·분·시간으로', () => {
    expect(duration(42_000)).toBe('42초')
    expect(duration(376_000)).toBe('6분 16초')
    expect(duration(3_900_000)).toBe('1시간 5분')
    expect(duration(-5)).toBe('0초')
  })
})

describe('isStalled: 멈췄을 수 있는가', () => {
  const now = Date.parse('2026-11-16T08:00:00Z')
  const ago = (min: number) => new Date(now - min * 60_000).toISOString()

  it('처리기 살아 있음이 3분 넘게 끊기면 멈춤 (진행 기록과 상관없이)', () => {
    expect(isStalled({ step_updated_at: ago(30), heartbeat_at: ago(1) }, now)).toBe(false)
    expect(isStalled({ step_updated_at: ago(1), heartbeat_at: ago(4) }, now)).toBe(true)
  })

  it('대기 중이면 멈춤이 아니고, 작업 기록이 없는 옛 검토는 진행 기록 10분', () => {
    expect(isStalled({ step_updated_at: ago(60), queue_position: 1 }, now)).toBe(false)
    expect(isStalled({ step_updated_at: ago(9) }, now)).toBe(false)
    expect(isStalled({ step_updated_at: ago(11) }, now)).toBe(true)
  })
})
