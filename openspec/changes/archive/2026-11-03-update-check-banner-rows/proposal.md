## Why

판정 탭 머리의 "공학 검산 위반 1건"은 검산 수를 세는데, "검산 위반" 꼬리표는 그 검산이 쓴 단시간(차단) 전류 줄과 최대 순간 전류 줄 두 곳에 붙는다. 사용자가 표에서 빨간 꼬리표 2개를 보고 1건과 맞지 않는다고 물었다.

## What Changes

- 판정 탭 머리에 검산 수와 함께 꼬리표를 붙인 항목 수를 보인다: "공학 검산 위반 1건(표시한 항목 2개) · 확인 필요 1건(표시한 항목 2개)".
- 설명 줄에 "검산 하나는 단시간 전류와 최대 순간 전류 두 항목에 표시합니다"를 더한다.
- 검산 계산·꼬리표 붙이는 곳은 그대로. 화면만, 마이그레이션 없음.

## Capabilities

### Modified Capabilities
- `review-workspace`: 판정 탭의 공학 검산 표시 (FR-12)

## Impact

- `frontend/src/views/detail/JudgeTab.tsx`, `frontend/e2e/check-display.spec.ts`
