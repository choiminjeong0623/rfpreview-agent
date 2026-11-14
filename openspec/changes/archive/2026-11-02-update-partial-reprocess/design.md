# 설계: update-partial-reprocess

## 지금 (add-document-processors)
```
_prepare(proc)  구조 → 추출 → AI 문장 구분(절마다 40줄) → 규칙 유형 → AI 유형(못 정한 줄) → Stats
점검(Stats) 걸림 + AI 있음 + proc ≠ 일반 → _prepare(GENERAL) 문서 전체 다시
```
구조·추출·규칙 유형은 코드라 처리기와 상관없이 같다. 다시 할 때 달라지는 것은 AI 두 단계뿐이다.

## 결정

### 1. 점검마다 고칠 수 있는 AI 단계 (`pipeline/processors.py`)
`Processor`에 `fix` 칸을 더한다. 점검이 걸렸을 때 다시 물을 AI 단계다.
```
BID_FORM          표 칸 0줄       fix: 없음     (표 칸은 AI에 묻지 않는다)
REQUIREMENT_SPEC  요구사항 0줄    fix: LABEL
TEST_SPEC         시험 유형 0줄   fix: TYPE
PURCHASE_SPEC     요구사항 0줄    fix: LABEL
SUPPLIER_SPEC     C/D/E 0줄       fix: 없음     (표시는 표에서 코드가 센다)
UNKNOWN(일반)     점검 없음
```
- 표 칸 후보와 C/D/E 표시는 `_refine_with_ai`에 들어가지 않고(문장 후보만 묻는다) 유형 답과도 상관없어, 지금 다시 처리해도 Stats가 같다. 그래서 다시 묻지 않는다. AI 호출을 아낀다.

### 2. 떨어진 부분 고르기 (`pipeline/document.py`)
`_prepare`가 첫 답을 버리지 않고 남긴다: 절마다 AI에 물은 문장 후보 번호와 받은 답, 유형을 물은 줄 번호와 답.
- **LABEL**: AI에 물은 절 중에 답이 하나도 REQUIREMENT가 아닌 절만 고른다. 그 절의 문장 후보를 첫 답 전(규칙 추출 결과)으로 되돌리고 일반 처리기(설명 없음)로 다시 묻는다. 그 뒤 규칙 유형을 다시 붙이고(코드), 새로 요구사항이 된 줄 중 규칙 유형이 없는 줄만 AI 유형을 처음 묻는다.
- **TYPE**: 첫 답이 NONE인 줄만 일반 처리기로 다시 묻는다. 문장 구분은 다시 묻지 않는다.
- 나머지 절·줄은 첫 답을 그대로 쓴다. 다시 물은 뒤 Stats를 다시 세지만 점검을 또 하지는 않는다(한 번만, CR-12). 걸린 이유는 첫 점검 결과다(지금과 같음).
- 다시 물은 줄 수 = LABEL로 다시 물은 문장 수 + TYPE으로 다시 물은 줄 수(새로 요구사항이 된 줄의 첫 유형 질문은 세지 않는다).
- 요구사항 0줄 점검은 걸렸다면 AI에 물은 절이 모두 떨어진 경우라, 문장 구분은 사실상 전부 다시 묻는다. 줄어드는 것은 구조·추출을 다시 하지 않는 것뿐이다. 아끼는 몫이 큰 곳은 1장의 "다시 묻지 않음"과 TYPE이다.
- `_refine_with_ai`·`tasks.label_sections`·`tasks.type_unclassified`는 그대로 쓴다(넘기는 절·줄만 줄인다). 프롬프트가 같으니 `PROMPT_VERSION`은 그대로 p5. 처리 판(`code_version`)은 문서 처리 코드 해시라 저절로 바뀌어 같은 파일도 새로 분석한다.

### 3. 기록
- `document.processor`는 처음 고른 처리기를 그대로 남긴다(대부분의 답이 그 처리기에서 왔다). 지금은 다시 처리하면 GENERAL로 바뀐다 → 바뀜.
- `document.reprocessed`는 실제로 다시 물었을 때만 true. 마이그레이션 0032: `document.reprocessed_lines INT NOT NULL DEFAULT 0`(main에서 마지막 번호를 다시 확인).
- 문서 표 응답 `reprocessed_lines`, 실행 기록 `lines_reprocessed`(graph_state에 문서 수와 함께), `npm run gen:api`.

## 대안
- 문서 전체 다시(지금): 단순하지만 다시 물어도 바뀔 수 없는 점검에도 AI를 두 번 쓴다. 버림.
- 점검을 절마다 하기(점검 통과 문서도 요구 문장이 다 빠진 절을 다시 묻기): 다시 묻는 문서가 늘고 발동 조건이 바뀐다. 이번 범위 밖.
- 떨어진 절을 다시 물을 때 다른 종류 설명을 넣기: 종류를 AI가 고르는 셈이라 버림(CR-01, 이전 결정).

## 위험
- 첫 답과 다시 물은 답을 섞으면 같은 문서 안에서 처리기 설명이 다른 답이 섞인다. 문서에 `reprocessed`·`reprocessed_lines`와 "확인 필요"가 남아 사람이 본다.
- 동시 처리(C1 병렬)와 결과가 같아야 한다. 다시 묻기도 `_prepare` 안(저장 전)이라 저장 순서와 상관없다. 기존 "동시 처리 = 차례 처리" 테스트를 그대로 통과해야 한다.
