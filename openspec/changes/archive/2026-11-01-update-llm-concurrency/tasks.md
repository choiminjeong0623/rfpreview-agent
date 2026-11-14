# Tasks

## 1. 문서 고치기

- [x] 1.1 명세서 NFR-10, 기획서 부록 B·9장 위험 줄

## 2. 동시 호출

- [x] 2.1 `llm/parallel.py` `run_ordered`: 순서 유지, `on_done`은 부르는 스레드, 예외 때 남은 일 취소
- [x] 2.2 `Usage.add` 잠금, `call_with_retry`·`GeminiLLM` 사용량 세기 바꾸기
- [x] 2.3 설정 `rfp_llm_workers`·`rfp_llm_timeout_s`, `make_llm`에 넘기기, `GeminiLLM` 시간 제한
- [x] 2.4 `label_sections`(절을 가로질러 묶음), `type_unclassified`, `draft_sentences`를 동시에
- [x] 2.5 `_refine_with_ai`가 `label_sections`를 쓰고 세부 진행을 이어 세기
- [x] 2.6 `_save_risks`: 근거 읽기 → 설명 동시에 → 순서대로 저장

## 3. 테스트·마무리

- [x] 3.1 Scenario 테스트 (`tests/test_llm_concurrency.py`)
- [x] 3.2 전체 검사, archive, AGENTS.md 표 47번 줄
