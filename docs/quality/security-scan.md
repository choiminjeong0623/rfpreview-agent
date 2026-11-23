# 의존성·비밀값 검사

> CI 작업 `security`(`.github/workflows/ci.yml`)가 PR과 main마다 돈다. 포트폴리오 점검(2026-11-22) P1-7.

| 검사 | 도구 | 대상 | 실패 조건 |
|---|---|---|---|
| Python 의존성 | `pip-audit` 2.10.1 (`uv export --frozen --no-dev`로 잠금 파일 그대로) | 백엔드 운영 의존성 | 알려진 취약점 1건 이상 |
| 화면 의존성 | `npm audit --omit=dev --audit-level=high` | 프런트 운영 의존성 | high 이상 1건 이상 |
| 비밀값 | `gitleaks` (git 기록 전체, 작업은 커밋 SHA로 고정) | 저장소 전체 | 비밀값으로 보이는 문자열 |

## 처음 돌린 결과 (2026-11-23, main 1e6601b 기준)

| 검사 | 결과 | 한 일 |
|---|---|---|
| pip-audit | 2개 꾸러미 5건: `opentelemetry-api` 1.45.1(CVE-2026-126360), `pyasn1` 0.6.4(CVE-2026-119194~119197) | 잠금 파일만 올림: `opentelemetry-api` 1.45.2, `pyasn1` 0.6.5 (`uv lock --upgrade-package`). 코드 바뀜 없음, pytest 그대로 통과 |
| npm audit | 0건 | 없음 |
| gitleaks | 0건 (git 기록 전체, PR #36 CI 첫 실행 "No leaks detected") | 없음 |

## 무시 목록

없음. 고칠 수 없는 결과가 나오면 여기에 꾸러미·번호·이유·다시 볼 날짜를 적고 도구의 무시 설정(`pip-audit --ignore-vuln`, `.gitleaksignore`)에 넣는다.
