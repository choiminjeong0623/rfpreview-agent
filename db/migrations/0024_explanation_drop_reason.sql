-- AI 답 검사 보강 (update-ai-answer-checks): 근거 대조에서 위험 조건 설명을 버린 이유.
-- UNKNOWN_EVIDENCE 주지 않은 근거 ID, QUOTE_NOT_FOUND 근거에 없는 인용,
-- NUMBER_NOT_ALLOWED 사실·그 문장의 근거 조각에 없는 숫자·배수 말. 저장했거나 AI 없이 돌면 NULL.
ALTER TABLE risk_flag
  ADD COLUMN explanation_drop_reason VARCHAR(30)
    CHECK (explanation_drop_reason IN ('UNKNOWN_EVIDENCE', 'QUOTE_NOT_FOUND',
                                       'NUMBER_NOT_ALLOWED'));
