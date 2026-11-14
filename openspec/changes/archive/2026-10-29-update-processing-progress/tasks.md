# Tasks

## 1. 백엔드

- [x] 1.1 `tasks.label_sentences`, `tasks.type_unclassified`에 `on_progress` 추가
- [x] 1.2 `process_document`에 세부 일 알림(`report`) 추가, `_documents_node`가 파일 순번을 붙여 넘김
- [x] 1.3 `RunContext.progress`, `_set_step`이 `detail`을 지우고 `updated_at` 기록, `service.run_to_end`가 자동 커밋 연결로 기록
- [x] 1.4 실행 요약·목록 조회와 응답 모델에 `step_detail`, `step_updated_at`

## 2. 화면

- [x] 2.1 `npm run gen:api`로 타입 다시 만들기
- [x] 2.2 `components/progress.ts`: 가중 백분율, 세부 문장
- [x] 2.3 처리 상태 화면: 세부 문장, 지난 시간·예상 안내, 멈춤 안내 (SCR-02 명세·공유 갱신)
- [x] 2.4 검토 목록·홈 5초 새로고침, 처리 중 표시에 백분율 (SCR-03·06 명세 갱신)

## 3. 테스트 (Scenario마다 하나 이상, 이름에 Scenario 이름)

- [x] 3.1 백엔드: 유형 붙이기 진행 개수 / 단계가 바뀌면 세부 진행을 지움 / 목록에도 세부 진행
- [x] 3.2 화면: 처리 중인 검토 / 유형 붙이기 진행 / 오래 진행이 없음 / 목록이 저절로 바뀜

## 4. 마무리

- [x] 4.1 `ruff`, `pytest`, `npm run lint`, `npm run check:api`, `npm run build`, `openspec validate --all --strict` 통과
- [x] 4.2 archive
