# Design

## 결정

1. **뺄 칸**: `warranty_candidate.status = 'EMPTY_REVIEW' AND reason_code = 'NOT_MAPPED'`인 판정. 같은 EMPTY_REVIEW라도 제품을 못 고른 칸(PRODUCT_AMBIGUOUS), 연결됐는데 값이 없는 칸은 의심할 줄이라 그대로 센다.
2. **계산**: `review_ratio`의 분자(확인 필요)와 분모(전체) 모두에서 뺀다. 분모에서 빼지 않으면 비율이 낮아 보이기만 하고 뜻이 흐려진다.
3. **직접 작성할 칸 수**: 같은 조건의 판정 수(반려한 판정 제외). 엔지니어가 보증값을 써 넣어 확정·수정하면 그 칸은 더 이상 EMPTY_REVIEW가 아니어서 자연히 줄어든다.
4. **응답**: `ReviewRatio.hand_fill: int`. 승인 화면(`/approval`)과 결정 결과가 같이 쓴다. 다시 만들 화면 타입은 `gen:api`.
5. **화면**: 요약 칸 문장만 더한다. 승인 기준 줄은 `approval.ts` `checkItems`에서 AR-03 문장 뒤에 "직접 작성할 칸 n개는 뺌".

## 위험

- 입찰 양식이 아닌 문서에서도 NOT_MAPPED 빈칸이 생기면 같이 빠진다. 그 칸도 제품표에 없는 항목이라 지어낼 수 없는 칸이므로 뜻은 같다.
