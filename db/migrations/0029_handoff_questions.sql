-- 협조 요청 메일의 부서 관점 확인 질문 (add-handoff-questions, C4).
-- 보낸 메일에 넣은 질문과 쓴 이(AI·CODE). 질문은 요구사항 원문을 대신하지 않는 참고 문장.
ALTER TABLE assignment ADD COLUMN ask_text TEXT;
ALTER TABLE assignment ADD COLUMN ask_by VARCHAR(4) CHECK (ask_by IN ('AI', 'CODE'));
