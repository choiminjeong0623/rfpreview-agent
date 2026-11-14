## 1. 문서

- [x] 1.1 명세서 FR-05 ⑤ B3, FR-06 ④ B5, FR-10 ④ B4

## 2. 구현

- [x] 2.1 `embed`·`embed_with_retry`, FakeLLM.embed, 마이그레이션 0028(text_vector, meaning_candidate)
- [x] 2.2 `pipeline/meaning.py`: 벡터 저장·코사인, meaning 단계(상태), B3·B5 후보
- [x] 2.3 B4 `review_memory` 뜻 힌트(match·score)
- [x] 2.4 API: 위험 조건 탭 후보·상태, 항목 연결 후보 목록·받아들이기·숨기기, 판정 힌트 칸, `npm run gen:api`
- [x] 2.5 화면: 위험 조건 탭 후보, 판정 탭 점수, 판정 규칙 항목 이름 탭 후보

## 3. 테스트

- [x] 3.1 Scenario마다 테스트, 검사 통과
- [x] 3.2 실제 Gemini로 문턱 확인, 개발 기록
