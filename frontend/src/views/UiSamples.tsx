import { useState } from 'react'
import { Badge, Button, DataTable, Modal, PageTitle, useToast, type Column } from '../ui'
import { ExampleBand } from './detail/ExampleTab'

// 공통 부품 견본 (add-ui-foundation, docs/screens/_프런트원칙.md 6장). 주소 #/dev/ui, 메뉴에는 없다.
// 새 화면을 만들 때 부품 모양과 쓰는 법을 여기서 본다. 데이터는 지어낸 견본이고 API를 부르지 않는다.

const SWATCHES = ['--c-navy', '--c-link', '--c-text', '--c-muted', '--c-line', '--c-bg-page',
  '--c-red', '--c-orange', '--c-green', '--c-grey', '--c-blue', '--c-purple']

type Row = { id: number; item: string; result: string }
const ROWS: Row[] = Array.from({ length: 12 }, (_, i) => ({ id: i + 1, item: `견본 항목 ${i + 1}`, result: i % 3 === 0 ? '일탈 후보' : '준수' }))
const COLS: Column<Row>[] = [
  { key: 'item', head: '항목', cell: (r) => r.item },
  { key: 'result', head: '판정', cell: (r) => <Badge tone={r.result === '준수' ? 'green' : 'red'}>{r.result}</Badge> },
]

export function UiSamples() {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const shown = ROWS.slice((page - 1) * size, page * size)
  return (
    <main className="main">
      <ExampleBand />
      <PageTitle title="공통 부품 견본" sub="새 화면은 이 부품을 쓴다" />
      <div className="uidev">
        <section aria-labelledby="uiTok">
          <h2 id="uiTok">색 토큰</h2>
          <div className="sw">
            {SWATCHES.map((v) => <div key={v}><i style={{ background: `var(${v})` }} />{v}</div>)}
          </div>
        </section>
        <section aria-labelledby="uiBadge">
          <h2 id="uiBadge">상태 배지</h2>
          <div className="row">
            <Badge tone="red">일탈 후보</Badge><Badge tone="orange">확인 필요</Badge><Badge tone="blue">분석 중</Badge>
            <Badge tone="green">준수</Badge><Badge tone="grey">해당 없음</Badge>
          </div>
        </section>
        <section aria-labelledby="uiBtn">
          <h2 id="uiBtn">단추</h2>
          <div className="row">
            <Button kind="primary" icon="check">제안대로 확정</Button>
            <Button>판정 바꾸기</Button>
            <Button kind="primary" disabledReason="승인자만 결정할 수 있습니다">승인</Button>
            <Button busy>보내는 중</Button>
          </div>
        </section>
        <section aria-labelledby="uiModal">
          <h2 id="uiModal">창</h2>
          <div className="row"><Button onClick={() => setOpen(true)}>견본 창 열기</Button></div>
          {open && (
            <Modal title="견본 창" onClose={() => setOpen(false)}
              footer={<><Button onClick={() => setOpen(false)}>취소</Button><Button kind="primary" onClick={() => setOpen(false)}>적용</Button></>}>
              <label>사유 <input aria-label="사유" /></label>
            </Modal>
          )}
        </section>
        <section aria-labelledby="uiToast">
          <h2 id="uiToast">알림</h2>
          <div className="row">
            <Button onClick={() => toast.show('첫 번째 알림입니다')}>성공 알림 1</Button>
            <Button onClick={() => toast.show('두 번째 알림입니다')}>성공 알림 2</Button>
            <Button onClick={() => toast.show('저장하지 못했습니다. 다시 시도해 주세요.', 'error')}>오류 알림</Button>
            <Button onClick={() => toast.done('첫 번째 동작 결과입니다')}>동작 결과 1</Button>
            <Button onClick={() => toast.done('두 번째 동작 결과입니다')}>동작 결과 2</Button>
          </div>
        </section>
        <section aria-labelledby="uiTable">
          <h2 id="uiTable">목록 표</h2>
          <DataTable label="견본 목록" columns={COLS} rows={shown} rowKey={(r) => r.id} empty="견본이 없습니다."
            page={page} size={size} total={ROWS.length} onPage={setPage} onSize={(s) => { setSize(s); setPage(1) }} />
          <DataTable label="빈 목록" columns={COLS} rows={[]} rowKey={(r) => r.id} empty="조건에 맞는 줄이 없습니다." />
        </section>
      </div>
    </main>
  )
}
