-- AI 오류 종류별 처리 (update-llm-retry-kinds): 형식이 틀린 설명은 다시 묻지 않고 버린다.
-- 버린 이유에 FORMAT_ERROR(형식 오류)를 더한다.
ALTER TABLE risk_flag DROP CONSTRAINT IF EXISTS risk_flag_explanation_drop_reason_check;
ALTER TABLE risk_flag ADD CONSTRAINT risk_flag_explanation_drop_reason_check
  CHECK (explanation_drop_reason IN ('UNKNOWN_EVIDENCE', 'QUOTE_NOT_FOUND',
                                     'NUMBER_NOT_ALLOWED', 'FORMAT_ERROR'));
