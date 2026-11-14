"""프롬프트를 바꾼 PR의 평가: CI 워크플로의 경로 거르기를 읽어 확인한다.

명세 prompt-evaluation "프롬프트를 바꾼 PR의 평가"의 Scenario (change add-prompt-eval, NFR-13).
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "prompt-eval.yml"


def trigger_paths() -> list[str]:
    """on.pull_request.paths 목록 (들여쓰기로 읽는다)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index("    paths:")
    out = []
    for line in lines[start + 1:]:
        m = re.fullmatch(r"\s{6}- (\S+)", line)
        if not m:
            break
        out.append(m.group(1))
    return out


def _regex(glob: str) -> re.Pattern:
    """GitHub 경로 글롭: ** 는 / 를 넘고, * 는 넘지 않는다."""
    parts = re.split(r"(\*\*|\*)", glob)
    body = "".join(".*" if p == "**" else "[^/]*" if p == "*" else re.escape(p) for p in parts)
    return re.compile(body + r"\Z")


def runs_for(changed: list[str]) -> bool:
    pats = [_regex(p) for p in trigger_paths()]
    return any(p.match(f) for p in pats for f in changed)


def test_workflow_triggers_on_prompt_file():
    """Scenario: 프롬프트 파일을 바꾼 PR — 공개 평가셋 결과 표를 작업 요약에 남긴다."""
    assert runs_for(["backend/src/rfp_agent/llm/tasks.py"])
    assert runs_for(["data/eval/public.jsonl"])
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text and "--set public" in text
    assert "--baseline-file ../data/eval/baseline.json" in text
    assert "GITHUB_STEP_SUMMARY" in text and "exit $code" in text          # 회귀면 실패
    assert "평가하지 않음" in text                                           # 키가 없으면 건너뜀


def test_workflow_skips_unrelated_change():
    """Scenario: 프롬프트와 무관한 PR — 화면 파일만 바꾸면 프롬프트 평가는 돌지 않는다."""
    assert not runs_for(["frontend/src/views/RunLog.tsx"])
    assert not runs_for(["backend/src/rfp_agent/pipeline/judge.py", "docs/README.md"])
