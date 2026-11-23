# 용어집 (Korean → English)

문서와 화면은 쉬운 우리말로 썼습니다. 영어로 설명하거나 코드를 읽을 때 대응하는 말입니다. "코드 이름"은 DB 칸·상수·함수에서 실제로 쓰는 이름입니다.

## 업무

| 우리말 | English | 코드 이름 | 뜻 |
|---|---|---|---|
| 입찰 기술 검토 | bid technical review | — | RFP의 기술 요구를 우리 제품과 비교해 일탈·질의를 정하는 일 |
| 검토 | review (run) | `review_run`, `run_id` | RFP 한 건을 올려 분석부터 결재까지 가는 단위 |
| 요구사항 | requirement | `requirement` | 문서에서 뽑은 지켜야 할 조건 한 줄 |
| 제품표 | product master | `product_master` | 우리 제품의 정격값 표(카탈로그 기준) |
| 항목 사전 | item dictionary (item keys and aliases) | `item_key`, `item_alias` | 원문 표현을 표준 항목(정격 전압 등)으로 잇는 사전 |
| 판정 | judgment | `judgment` | 요구값과 제품값을 코드가 비교한 결과(후보) |
| 준수 | comply | `COMPLY` | 요구를 맞춤 |
| 일탈 후보 | deviation candidate | `DEVIATION_CANDIDATE` | 요구를 못 맞춤. 일탈 목록 초안이 됨 |
| 질의 후보 | clarification (query) candidate | `QUERY_CANDIDATE` | 문서 안 값이 엇갈리거나 검산이 맞지 않아 고객에게 물을 것 |
| 확인 필요 | needs review | `NEEDS_REVIEW` | 코드가 정하지 못해 사람이 볼 줄 |
| 보증값 작성 | guaranteed value to fill (GTP / datasheet) | `WARRANTY_TO_FILL` | 데이터시트 빈칸에 넣을 우리 값 후보 |
| 위험 조건 | risk clause | `risk_flag` | 포괄 조항·범위 모호·값 불일치처럼 놓치면 계약 위험이 되는 조항 |
| 손실 환산 | loss capitalization (loss evaluation) | `loss_calc` | 변압기 손실(kW)을 단가로 곱해 평가 가격에 더하는 계산 |
| 제안 포인트 | proposal point (technical advantage) | `proposal_point` | 판정 여유에서 나온, 내세울 만한 강점 후보 |
| 공학 검산 | engineering check | `engineering_check` | 문서 숫자끼리 공학 규칙(예: 최대 순간 전류 = 단시간 전류 × 2.5)이 맞는지 계산 |
| 협조 요청 | handoff request | `assignment` | 견적·품질·영업 부서로 보내는 확인 요청과 메일 |
| 영업 인계 패키지 | sales handoff package | `sales_handoff` | 결재 뒤 영업에 넘기는 일탈·질의 Word, TBE·데이터시트 엑셀 zip |
| TBE 준수표 | technical bid evaluation (compliance) sheet | — | 요구 항목별 준수·일탈을 적는 표 |
| 팀 가정 | team assumption | `is_assumed` | 카탈로그에 없어 팀이 정한 비교값. 결과마다 표시 |
| 원문 위치 | source location | `source_location` | 파일 번호 + 절 또는 표 + 행 (PDF는 쪽까지) |
| 묶음 A·B | bundle A / B | `bundle` | 판정 대상 문서 묶음. 그 밖 묶음은 읽기만 함 |
| 정정본·Addendum | revision / addendum | `document_pair` | 나중에 온 문서. 원본과 쌍을 지어 바뀐 줄을 찾음 |

## 사람 동작과 흐름

| 우리말 | English | 코드 이름 | 뜻 |
|---|---|---|---|
| 담당자 확인 | engineer review | `ENGINEER_REVIEW` | 분석이 끝나고 엔지니어가 확정·수정·반려하는 멈춤 자리 |
| 확정·수정·반려 | confirm / edit / reject | `CONFIRM`, `EDIT`, `REJECT` | 판정 한 줄에 대한 사람 결정 |
| 한꺼번에 확정 | bulk confirm | `bulk_confirm` | 여러 줄을 한 번에 확정. 검산 위반 등은 코드가 뺌 |
| 상신 | submit for approval | `submit` | 엔지니어가 결재자에게 올림 |
| 결재(승인·반려) | approval (approve / reject) | `approve`, `reject` | 결재자의 결정 |
| 상신 취소 | withdraw | `withdraw` | 결재 전 되돌리기 |
| 단계부터 다시 | rewind | `rewind` | 처리 단계 하나부터 다시 돌림. 사람 확정은 이어받음 |
| 처리 단계 | pipeline step | `PIPELINE` | documents → pairs → risks → judge → … → assign |
| 멈춤 자리 | interrupt stop | `STOPS` | 흐름이 사람을 기다리며 실제로 멈추는 곳 |
| 갈 곳 표 | transition table | `NEXT` | 멈춤 자리마다 사람 동작 → 다음 단계 |
| 흐름 상태 | checkpoint | LangGraph `PostgresSaver` | 단계마다 저장한 흐름 상태. 멈춘 단계부터 이어 감 |
| 흐름 기록 | flow history | `graph_flow.history` | 단계별 시간·바뀐 건수·사람 동작 |

## 실행과 운영

| 우리말 | English | 코드 이름 | 뜻 |
|---|---|---|---|
| 실행 대기열 | run queue | `run_job` | 등록·다시 시도 등 작업을 넣어 두는 표. `FOR UPDATE SKIP LOCKED`로 꺼냄 |
| 처리기 (대기열) | worker | `rfp-worker`, `run_worker` | 대기열에서 작업을 꺼내 도는 프로세스 |
| 처리기 (문서 종류별) | document processor | `processors.py` | 문서 종류마다 다른 설명·점검·추출 규칙 묶음. 위의 worker와 다른 말 |
| 실행 토큰 | run token (fencing token) | `run_token` | 한 검토에 실행 하나만 결과를 쓰게 하는 표 |
| 살아 있음 | heartbeat | `heartbeat_at` | 처리기가 살아 있다고 30초마다 적는 시각 |
| 다시 넣기 | reclaim / requeue | `reclaim` | 처리기가 3분 끊기면 새 토큰으로 작업을 다시 넣음 |
| 실행 기록 | run log | `run_step_time`, 실행 기록 화면 | 단계별 시간·AI 호출·토큰·추정 비용 |
| AI 호출 기록 | AI call trace | `ai_call` | AI 요청 시도마다 역할·판·시간·토큰·결과(원문 없이 해시) |
| 버린 이유 | drop reason | `dropped_reason` | 형식은 맞지만 코드 검사에서 버린 답의 이유 |
| 문서 읽기 점검 | read check | `read_check` | 읽지 못한 쪽·그림·표를 모아 보이는 목록 |

## AI와 평가

| 우리말 | English | 코드 이름 | 뜻 |
|---|---|---|---|
| AI 역할 | AI role | `tasks.PROMPTS` | 문장 구분·유형·위험 설명·검증·초안·협조 질문·도우미·문서 분류 8개 |
| 프롬프트 판 | prompt version | 예: `p5`, `t2+lf4` | 역할마다 프롬프트 글의 판. 바꾸면 해시 시험이 판 올림을 요구 |
| 자리표시자 | placeholder | `{value}` 등 | AI가 숫자 대신 쓰는 자리. 코드가 채우고 근거와 대조 |
| 근거 조각 | evidence span | `EvidenceSpan` | AI에게 주는 원문 조각과 그 ID |
| 검증 에이전트 | claim verifier | `verify` 역할 | 위험 설명 문장을 근거가 받쳐 주는지 두 번째 AI가 표시 |
| 검토 도우미 | review assistant | `assistant` 역할 | 읽기 도구 3개만 쓰는 질의응답 에이전트 |
| 문장 벡터·뜻으로 찾기 | embedding / semantic search | `text_vector` | 후보·힌트만 내는 유사 문장 찾기 |
| 평가셋 | eval set | `data/eval/*.jsonl` | 프롬프트 평가 문항 |
| 기준선 | baseline | `baseline` | 비교 기준이 되는 평가 결과(3번 반복의 최솟값) |
| 회귀 | regression | `regression` | 지표가 떨어지고 틀린 문항 수가 허용보다 늘어난 것 |
| 주입 시험 | prompt injection test | 주입 쌍 10개 | 문서 속 지시를 따르는지 보는 시험 |
| 비용 상한 | cost cap | `RFP_EVAL_MAX_KRW` | 평가 한 번에 쓸 수 있는 추정 비용(팀 가정 단가) |
| 정답지 | answer key | `answer_key` | 요구사항·유형·판정의 정답 표 |
| 채점 | scoring | `eval_score` | 정답지·사람 확정과 시스템 결과를 대조한 지표 |
| 사람 수정 비율 | human edit rate | `EDIT-RATE` | 한 줄씩 본 판정 중 사람이 수정·반려한 비율 |
| 95 % 구간 | 95 % (Wilson) confidence interval | `ci_low`, `ci_high` | 비율 지표의 불확실성 범위 |
