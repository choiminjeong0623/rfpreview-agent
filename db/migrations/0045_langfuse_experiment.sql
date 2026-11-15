-- 평가를 Langfuse 실험으로 남긴 데이터셋 화면 주소 (add-langfuse-experiments).
-- 보내지 않았거나 주소를 얻지 못하면 비움
ALTER TABLE prompt_eval_run ADD COLUMN langfuse_url TEXT;
