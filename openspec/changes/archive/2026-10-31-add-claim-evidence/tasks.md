# Tasks

## 1. 근거 대조 (박경빈 브랜치 정리, 최민정)

- [x] 1.1 `llm/evidence.py`: 근거 조각 ID 만들기·읽기, 인용 정리
- [x] 1.2 `llm/tasks.py` `explain_risk`: claim·인용·관계 받기, 형식 검사(재시도)와 근거 검사(버림)
- [x] 1.3 마이그레이션 0016 `claim_evidence`, `claim_evidence_source`
- [x] 1.4 `pipeline/run.py`: 근거 조각 주기, 통과한 문장 저장, 다시 돌릴 때 지우기
- [x] 1.5 테스트: 근거와 맞는 설명 저장, 근거에 없는 인용, 설명을 받지 못함, 없는 숫자
