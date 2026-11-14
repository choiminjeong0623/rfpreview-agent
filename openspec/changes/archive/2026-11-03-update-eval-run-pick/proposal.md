## Why

정답지·채점 화면 정답지 탭은 사람이 확인한 판정이 있는 검토를 모두 미리 골라 둔다. 검토가 쌓인 DB에서는 수백 건이 한꺼번에 채점되고, 고른 검토를 하나씩 풀어야 해서 원하는 검토만 채점하기 어렵다.

## What Changes

- 정답지 탭 검토 목록 위에 검색 칸(검토 번호·이름), [모두 고르기]·[모두 해제], "검토 n건 고름"을 둔다.
- [모두 고르기]·[모두 해제]는 검색으로 보이는 검토에만 적용한다. 고른 수는 검색과 상관없이 전체에서 센다.
- 처음 고름(판정 줄이 있는 검토)과 채점 API는 그대로. 화면만, 마이그레이션 없음.

## Capabilities

### Modified Capabilities
- `review-workspace`: 정답지·채점 화면 검토 고르기 (SCR-19)

## Impact

- `frontend/src/views/Eval.tsx`, `frontend/e2e/evaluation.spec.ts`
