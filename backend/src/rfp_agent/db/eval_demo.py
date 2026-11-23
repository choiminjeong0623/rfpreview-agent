"""재현 채점 명령 `rfp-db eval-demo` (add-eval-demo, 명세 evaluation "재현 채점 명령").

AI를 끈 채 검토가 없는 DB에 시연 준비(합성 RFP 28 검토 1건, 정답지 셋)를 하고,
세 정답지(요구사항·유형·판정)로 채점해 지표·분자/분모·95 % 구간·목표 표를 낸다.
같은 저장소·같은 코드면 누가 돌려도 같은 표다(CR-11). 처리 시간은 기계마다 달라 표에 넣지 않는다.
"""

import os
from pathlib import Path

from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect

LEFT_OUT = {"TIME"}                 # 기계마다 다른 값
WHO = {"CLAUDE_DRAFT": "Claude 초안(사람 확인 전)", "HUMAN": "사람", "AUTO": "코드 자동"}


def _num(m: dict) -> str:
    if m["value"] is None:
        return "재지 않음"
    if m["unit"] == "%":
        return f"{m['value']:.1f} %"
    return f"{m['value']:g} {m['unit']}"


def _frac(m: dict) -> str:
    return f"{m['num']}/{m['den']}" if m["den"] else ""


def _ci(m: dict) -> str:
    return "" if m.get("ci_low") is None else f"{m['ci_low']:.1f}–{m['ci_high']:.1f} %"


def _target(m: dict) -> str:
    if m["target"] is None:
        return ""
    sign = "≥" if m["better"] == "up" else "≤"
    return f"{sign} {m['target']:g}" + (" %" if m["unit"] == "%" else f" {m['unit']}")


def table(metrics: dict, keys: list[dict], code: str) -> str:
    """채점 결과를 마크다운 표로. 같은 지표면 같은 글자(시각·DB 이름 없음)."""
    lines = ["# 재현 채점 (rfp-db eval-demo)", "",
             f"- 문서: 합성 RFP 28 (공개본 스크립트로 만듦), AI 끔, 처리 코드 판 `{code}`",
             "- 정답지: " + ", ".join(f"{k['key_name']} {k['rows']}줄 · {WHO[k['made_by']]}"
                                       for k in keys),
             "- 구간: 윌슨 95 %. 분모가 작으면 100 %여도 아래 값이 낮다.", "",
             "| 지표 | 이름 | 값 | 맞음/전체 | 95 % 구간 | 목표 | 메모 |",
             "|---|---|---|---|---|---|---|"]
    for m in metrics["items"]:
        if m["code"] in LEFT_OUT:
            continue
        lines.append(f"| {m['code']} | {m['name']} | {_num(m)} | {_frac(m)} | {_ci(m)} | "
                     f"{_target(m)} | {m['note'] or ''} |")
    if j := metrics.get("judgments"):
        lines += ["", "판정 정답지: 정답 × 시스템", "", "| 정답 | 시스템 | 줄 |", "|---|---|---|"]
        lines += [f"| {c['expected']} | {c['system']} | {c['count']} |" for c in j["table"]]
    return "\n".join(lines) + "\n"


def run(create: bool, report: Path | None, file: Path | None) -> str:
    from rfp_agent.db import cli
    from rfp_agent.pipeline import code_version, evaluation

    os.environ["RFP_AI_MODE"] = "off"            # 재현: AI 없이 규칙만
    get_settings.cache_clear()
    cli.demo_setup(create, file)
    with connect() as conn:
        ids = dict(conn.execute("SELECT key_kind, key_id FROM answer_key "
                                "WHERE key_name LIKE '합성 RFP 28 %'").fetchall())
        run_ids = [r for (r,) in conn.execute("SELECT run_id FROM review_run ORDER BY run_id")]
        saved = evaluation.score(conn, run_ids, ids["TYPE"], "eval-demo", None, ids["REQ"],
                                 ids["JUDGE"])
        keys = [k for k in evaluation.keys(conn) if k["key_id"] in ids.values()]
    text = table(saved["metrics"], keys, code_version())
    print(text)
    if report is not None:
        # 표는 명령을 돌린 폴더 안에만 쓴다(다른 곳 파일을 덮지 않음)
        here = Path.cwd().resolve()
        target = (here / report).resolve()
        if not target.is_relative_to(here):
            raise SystemExit(f"[재현 채점] 표는 지금 폴더 안에만 씁니다: {report}")
        target.write_text(text, encoding="utf-8")
        print(f"[재현 채점] 표를 썼습니다: {report}")
    return text
