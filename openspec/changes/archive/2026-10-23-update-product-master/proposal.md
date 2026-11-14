# Proposal

## Why

처음 적재한 제품표(product_master_입력용.csv, product_master_TRF_v2.csv)는 잘못된 파일이었다. 팀이 새 product_master.csv(제품 122개, 제품군 GIS·MV_EQUIP·SPD·TRANSFORMER)를 기준으로 정했으므로, 실제 제품표를 이 파일로 바꾸고 이전 제품과 그 제품으로 만든 검토 결과를 지울 수 있어야 한다. 지금 적재는 덮어쓰기만 해서 이전 제품이 계속 비교 대상으로 남는다.

## What Changes

- 실제 제품표를 `data/seed/products/product_master.csv` 한 파일로 바꾼다. 손실값 파일은 새 코드로 된 것이 나올 때까지 없음.
- 제품표 적재에 "바꾸기"를 더한다: 이전 제품·제품군과 검토 실행 결과를 지우고 파일 내용만 남긴다.
- 바꾸기 없이 적재했는데 파일에 없는 이전 제품이 DB에 남아 있으면 그 수를 알린다.
- 판정 이후 단계 테스트는 실제 제품표 대신 테스트용 고정 제품표를 쓴다 (실제 제품 데이터가 바뀌어도 Scenario 입력이 같도록).

## Capabilities

### New Capabilities

### Modified Capabilities
- `reference-data`: 제품표 바꾸기, 남은 이전 제품 알림.

## Impact

- 새 제품표로는 파일 1의 비교 제품이 줄어든다 (변압기 전압 없음, 손실값 없음, 배전반 제품군 다름 등). 데이터 보완은 팀이 CSV에서 한다.
- 바꾸기는 검토 실행 결과를 지우므로 되돌릴 수 없다. 명령에 직접 지정할 때만 한다.
