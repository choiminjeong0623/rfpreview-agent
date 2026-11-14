## 1. 문서

- [x] 1.1 명세서 NFR-07에 AI 사용 방식 설정, 기획서 데이터 취급에 한 줄

## 2. 백엔드

- [x] 2.1 설정 칸 5개와 `make_llm(settings)` (gemini·local·off)
- [x] 2.2 `LocalLLM`: OpenAI 호환 chat/completions(JSON 스키마, temperature 0, 토큰 수)·embeddings, HTTP 코드 → 오류 종류
- [x] 2.3 화면 지난 확정 찾기를 지금 벡터 모델로 (`meaning.current_model`)
- [x] 2.4 `/api/health`에 ai_mode·ai_model·external_send
- [x] 2.5 테스트: Scenario 마다 (AI 끄기, 사내 모델로 보냄, 사내 모델 설정 오류, 사내 벡터 모델 없음, AI 방식 표시)

## 3. 화면

- [x] 3.1 `npm run gen:api`, 검토 등록·실행 기록에 AI 방식 한 줄
- [x] 3.2 SCR-25 공유 문서에 한 줄 안내 적기

## 4. 마무리

- [x] 4.1 검사 통과, archive, AGENTS.md 표, 개발 기록
