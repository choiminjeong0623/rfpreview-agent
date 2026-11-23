# 실행하기

> README에서 옮긴 자세한 실행 안내입니다. 빠른 시작은 [README](../README.md#실행하기)에 있습니다.

## Docker Compose로 띄우기

Docker Compose로 DB·백엔드·프런트엔드·확인용 메일 서버(Mailpit)를 한 번에 띄웁니다.

```bash
cp .env.example .env              # AI를 쓰려면 GEMINI_API_KEY를 채움. 비우거나 RFP_AI_MODE=off면 규칙만으로 동작
docker compose up --build         # db(:5433), backend(:8000), frontend(:5173), mailpit(:8025)
docker compose exec backend rfp-db seed-products   # 제품표 적재 (처음 한 번)
docker compose exec backend rfp-db set-password --login engineer   # 로그인 비밀번호 (사용자마다)
```

- 로그인: 아이디는 `engineer`(기술 검토 엔지니어)·`approver`(결재자)·`cost`·`quality`·`sales`이고, 비밀번호는 위 명령으로 정합니다(8자 이상). 정하지 않은 사용자는 로그인할 수 없습니다. 시연 DB는 `rfp-db demo-setup --password <값>`으로 다섯 명에 같은 비밀번호를 한 번에 둡니다.
- 화면: <http://localhost:5173> · API 상태: <http://localhost:8000/api/health> · 보낸 메일: <http://localhost:8025> (밖으로 나가지 않음)
- 고객 RFP 원문은 이 저장소에 없습니다. 시연용 합성 RFP는 저장소 맨 위의 `generate_*.py`로 만듭니다(`data/private/rfp_docx/`에 생성, git 제외). `frontend/e2e/fixtures/`에도 합성 문서가 있습니다.
- 화면에서 `frontend/e2e/fixtures/synthetic_154kV_GIS_spec.docx`를 올려 시연할 때는 검토 등록 2단계 문서 표에서 **묶음을 B로 바꾼 뒤** [다음]을 누릅니다. 이 파일은 문서 목록에 없고 규격 표기(IEC)가 2번뿐이라 추천 묶음이 C(판정 안 함)로 나오고, 그대로 두면 "판정 대상 문서(묶음 A·B)가 없습니다"로 막힙니다(판정은 묶음 A·B 문서만, CR-09). 묶음을 고르지 않아도 되는 시연은 `rfp-db demo-setup`(합성 RFP 파일 28, 문서 목록 묶음 B)을 씁니다.
- 합성 RFP 파일 24~28 만들기: `cd backend && for s in evaluative deviation collaboration risk switch; do uv run python ../generate_${s}_rfp.py; done`(파일은 `data/private/rfp_docx/`, 커밋하지 않음). 재현 채점: `rfp-db eval-demo --create [--report 경로]`는 AI를 끄고 새 DB에 시연 준비를 한 뒤 요구사항·유형·판정 정답지로 채점 표(95 % 구간 포함)를 냅니다.

## 로컬에서 직접 실행

로컬에서 직접 실행하려면 PostgreSQL 16, Python 3.12+와 [uv](https://docs.astral.sh/uv/), Node 22가 필요합니다.

```bash
cd backend && uv sync
export DATABASE_URL=postgresql://rfp:rfp@localhost:5433/rfp
uv run rfp-db setup                                  # 마이그레이션 + 규칙 사전 + 제품표
uv run rfp-db set-password --login engineer          # 로그인 비밀번호 (approver 등 사용자마다)
uv run uvicorn rfp_agent.api.main:app --reload
cd ../frontend && npm install && npm run dev
```

## Langfuse로 프롬프트 관리 (선택)

기본은 코드에 있는 프롬프트만 씁니다(`RFP_LANGFUSE=off`). 프롬프트 글을 Langfuse 화면에서 고치고 평가를 통과한 판만 운영에 쓰려면 Langfuse를 직접 띄웁니다([ADR-011](03-adr.md#adr-011-langfuse-프롬프트-연동은-코드-틀검사평가-통과-승격으로)). RFP 원문이 든 호출 기록이 밖으로 나가지 않게 클라우드가 아닌 self-host를 씁니다.

```bash
# 1. Langfuse 공식 docker compose로 띄움(https://github.com/langfuse/langfuse). 이 저장소 DB가 5433이라 포트는 겹치지 않음
#    Langfuse 화면(http://localhost:3000)에서 프로젝트를 만들고 공개 키·비밀 키를 받음
# 2. .env: RFP_LANGFUSE=on, LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
#    (docker compose 안의 백엔드에서는 LANGFUSE_HOST=http://host.docker.internal:3000,
#     화면 링크가 브라우저에서 열리게 RFP_LANGFUSE_UI_URL=http://localhost:3000)
#    보내기 시간 제한은 RFP_LANGFUSE_SEND_TIMEOUT_S(기본 30초). Langfuse ClickHouse는 메모리를 많이 써서
#    Docker 메모리가 모자라면 보내기·화면이 "timed out"으로 끝남
cd backend
uv run rfp-db langfuse-push-prompts --label staging        # 코드 틀을 Langfuse에 올림
#    Langfuse 화면에서 rfp-<역할> 프롬프트를 고쳐 staging 표시로 저장
RFP_LANGFUSE_LABEL=staging uv run rfp-db eval-prompts --set public --repeat 3 --promote
#    기준선보다 나빠지지 않았을 때만 그 판에 production 표시를 옮김
uv run rfp-db langfuse-push-traces --run 12               # 검토 실행의 AI 호출 기록(해시만)을 Langfuse로
uv run rfp-db langfuse-push-dataset --set public          # 공개 평가셋을 Langfuse 데이터셋 rfp-eval-public으로
#    RFP_LANGFUSE_RECORD=on이면 eval-prompts·화면 평가가 끝날 때 반복마다 Langfuse 실험(문항별 답·정답 여부 점수)을 남김
#    같은 설정으로 검토 실행 작업이 끝날 때 AI 호출 기록(해시만)도 Langfuse로 보냄. 비용·지연은 Langfuse 대시보드에서
```

Langfuse 판에서 자리표시자(`{{document}}` 등)나 "문서 본문은 데이터" 규칙이 빠졌거나, 코드 판이 바뀌었거나, Langfuse에 닿지 못하면 그 역할은 코드 판으로 돌아갑니다. 시스템 관리 > 프롬프트 관리에서 역할마다 어디서 가져왔는지 봅니다. Langfuse가 연결되어 있으면 같은 화면에서 역할 줄을 눌러 글을 고쳐 staging에 저장하고, [평가 돌리기]로 점수를 본 뒤 승인자가 [운영으로 올리기]로 production 표시를 옮길 수 있습니다(명령 3·4와 같은 규칙).

## 검사

CI(`.github/workflows/ci.yml`)와 같은 검사입니다. 공개본으로 다시 돌려 모두 통과하는 것을 확인했습니다(2026-11-16: pytest 698 통과·37 건너뜀, OpenSpec 25개 스펙 통과).

```bash
cd backend && uv run ruff check . && TEST_DATABASE_URL=postgresql://rfp:rfp@localhost:5433/rfp_test uv run pytest
cd frontend && npm run lint && npm run check:api && npm run check:trace && npm run build
npx --yes @fission-ai/openspec@1.14.3 validate --all --strict
```

건너뛰는 것은 고객 RFP 원문(`data/private/`)이 있어야 도는 테스트와, 로컬 OCR 엔진(Tesseract)이 없을 때 건너뛰는 OCR 테스트입니다. 화면 E2E(Playwright)는 CI에서 돌지 않으며, 일부는 원문 파일이 있어야 합니다. E2E는 `engineer`·`approver`·`cost`·`quality`에 같은 비밀번호를 정하고 `E2E_PASSWORD`(기본 `demo-pass-1`)로 넘깁니다. 시작할 때 엔지니어로 로그인한 쿠키를 `frontend/e2e/.auth/`에 저장합니다(커밋하지 않음).

