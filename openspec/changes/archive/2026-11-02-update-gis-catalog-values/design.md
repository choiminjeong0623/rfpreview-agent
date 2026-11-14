# 설계: update-gis-catalog-values

## 결정
- `product_master.csv` GIS 4행만 고친다: `rated_current_a` 칸, `description` 끝에 "정격 단시간 전류 N kA (n초), 정격 전류 … A (카탈로그 … p.n)." 문장. 단시간 시간은 지금처럼 `products.SHORT_TIME`이 설명 문장에서 읽는다(새 칸·마이그레이션 없음).
- 값 출처: 팀 입력용 표 `product_master_입력용.csv`(e5ef7a1)와 카탈로그 쪽수. `is_assumed`는 N 그대로(카탈로그 값).
- GIS-170-50 정격 전류는 카탈로그 선택지 1200/2000/4000 A 중 최대 4000 A. 선택지를 판정에 쓰는 규칙은 범위 밖이라 설명 문장에 선택지를 남긴다.
- 테스트(`tests/test_seed_units.py`)는 고정 제품표가 아니라 실제 `data/seed/products/`를 적재해 값과 판정을 본다.

## 위험
- 판정이 바뀐다(확인 필요 → 준수/일탈). 적용하려면 `rfp-db seed-products`(제품표 다시 적재). 이미 만든 검토는 다시 판정하기 전까지 그대로.
