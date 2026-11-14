-- 위험 설명 검증 에이전트 (add-claim-verifier): 근거 대조를 통과한 설명을 다른 질문으로
-- 한 번 더 확인한 결과. VERIFIED 모든 문장을 근거가 받쳐 줌, NEEDS_REVIEW 하나라도 아니거나 모름.
-- 설명이 없거나 언어 모델 없이 돌면 NULL. 표시만 하고 후보·판정은 바꾸지 않는다.
ALTER TABLE risk_flag
  ADD COLUMN explanation_check VARCHAR(20)
    CHECK (explanation_check IN ('VERIFIED', 'NEEDS_REVIEW'));
