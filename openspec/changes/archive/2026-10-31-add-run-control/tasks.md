# Tasks

## 1. 문서

- [x] 1.1 명세서 CR-12, 기획서 예외 표, `SCR-02_공유.md` 5번, `SCR-11_공유.md` 3·9번

## 2. DB·처리 흐름

- [x] 2.1 `db/migrations/0018_run_control.sql`: 취소 요청 시각·요청자, 다시 시도 횟수
- [x] 2.2 `pipeline/run.py`: 처리 시작 때 입력 저장, 진행 기록 때 취소 확인, 취소면 FAILED와 취소 문장
- [x] 2.3 `pipeline/run_control.py`: 취소 요청(멈춘 처리 바로 정리), 다시 시도 준비

## 3. API

- [x] 3.1 `POST /api/runs/{id}/cancel`, `POST /api/runs/{id}/retry`, 실행 요약에 `cancelled`·`retries`·`retryable`
- [x] 3.2 `npm run gen:api`
- [x] 3.3 테스트: Scenario마다

## 4. 화면

- [x] 4.1 처리 상태 화면 "분석 취소"(한 번 더 확인)
- [x] 4.2 분석 실패 화면 "다시 시도" 실제 처리, 취소한 검토 문구
- [x] 4.3 e2e

## 5. 마무리

- [x] 5.1 검사, archive, AGENTS.md 표, 개발 기록
