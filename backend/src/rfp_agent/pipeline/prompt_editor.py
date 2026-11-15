"""프롬프트 관리 화면에서 Langfuse 프롬프트 고치기 (add-prompt-editor, ADR-011 이어서).

화면은 RFP 안에 두고, 저장·판 관리는 Langfuse가 한다(글은 Langfuse 버전으로 남는다).

- 저장: 고친 글을 코드 검사(자리표시자·데이터 규칙)에 통과시킨 뒤 Langfuse에 staging 새 버전으로.
- 평가: 그 역할의 공개 평가셋 문항만 staging 판으로 3번 반복해 기준선과 비교(나머지 역할은 운영 판).
  몇 분 걸리므로 웹 서버 안 스레드에서 돌리고 화면은 상태를 다시 묻는다.
- 운영으로 올리기: 그 평가가 통과했고 평가 뒤 staging 판이 그대로일 때만,
  승인자가 production 표시를 옮긴다.

판단(검사·통과·권한)은 모두 코드가 한다(CR-01). AI는 평가 문항에 답할 뿐이다.
"""

import json
import logging
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg

from rfp_agent.config import get_settings
from rfp_agent.db.connection import connect
from rfp_agent.llm import prompt_source, tasks, trace
from rfp_agent.pipeline import langfuse_ops
from rfp_agent.pipeline import prompt_eval as pe

log = logging.getLogger(__name__)

STAGING = "staging"
EDIT_ROLES = ("ENGINEER", "APPROVER")       # 고치기·평가 [제안]
PROMOTE_ROLES = ("APPROVER",)                # 운영으로 올리기 [제안]
EVAL_SET = "public"
NOT_CONNECTED = "Langfuse가 연결되어 있지 않아 이 화면에서 프롬프트를 고칠 수 없습니다."


class EditorError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _role(role: str) -> str:
    if role not in tasks.PROMPTS:
        raise EditorError(404, f"모르는 AI 역할입니다: {role}")
    return role


def _actor(conn: psycopg.Connection, actor_id: int, allowed: tuple[str, ...], what: str) -> str:
    row = conn.execute("SELECT role, user_name FROM app_user WHERE user_id = %s",
                       (actor_id,)).fetchone()
    if row is None:
        raise EditorError(400, f"사용자 {actor_id}이(가) 없습니다.")
    if row[0] not in allowed:
        names = {"ENGINEER": "엔지니어", "APPROVER": "승인자"}
        raise EditorError(403, f"{what}는 {'·'.join(names[r] for r in allowed)}만 할 수 있습니다.")
    return row[1]


def _client() -> prompt_source.Client:
    lf = prompt_source.client() if prompt_source.enabled() else None
    if lf is None:
        raise EditorError(409, NOT_CONNECTED)
    return lf


def _get(lf: prompt_source.Client, role: str, label: str) -> dict | None:
    try:
        return lf.get_prompt(prompt_source.name_of(role), label)
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise EditorError(502, f"Langfuse에 닿지 못했습니다: {exc}") from exc


def _side(role: str, data: dict | None) -> dict | None:
    if data is None:
        return None
    reason = prompt_source.check(role, data)
    return {"version": int(data["version"]), "text": data.get("prompt") or "",
            "usable": reason is None,
            "problem": prompt_source.FALLBACKS[reason] if reason else None,
            "commit_message": data.get("commitMessage")}


AI_OFF = "AI를 쓰지 않는 설정이라 평가할 수 없습니다."


def _ai_ready() -> bool:
    from rfp_agent.llm import client as llm_client

    return llm_client.ai_mode(get_settings()) != "OFF"


def detail(role: str) -> dict:
    """역할 하나의 코드 틀과 Langfuse 운영·staging 판, 가장 최근 화면 평가."""
    _role(role)
    out = {"role": role, "code_version": tasks.PROMPTS[role],
           "code_template": tasks.TEMPLATES[role],
           "slots": sorted(prompt_source.slots(tasks.TEMPLATES[role])),
           "data_rule": tasks.DATA_RULE, "langfuse_name": prompt_source.name_of(role),
           "connected": False, "editable_reason": NOT_CONNECTED,
           "evaluable": role in pe.METRICS, "ai_ready": _ai_ready(),
           "production": None, "staging": None, "evaluation": latest_job(role)}
    lf = prompt_source.client() if prompt_source.enabled() else None
    if lf is None:
        return out
    try:
        out["production"] = _side(role, lf.get_prompt(prompt_source.name_of(role), "production"))
        out["staging"] = _side(role, lf.get_prompt(prompt_source.name_of(role), STAGING))
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        out["editable_reason"] = f"Langfuse에 닿지 못했습니다: {exc}"
        return out
    out["connected"], out["editable_reason"] = True, None
    return out


def save_draft(conn: psycopg.Connection, role: str, actor_id: int, text: str,
               message: str | None) -> dict:
    """고친 글을 검사하고 Langfuse에 staging 새 버전으로 올린다. 검사에 걸리면 올리지 않는다."""
    _role(role)
    name = _actor(conn, actor_id, EDIT_ROLES, "프롬프트 고치기")
    lf = _client()
    text = text.replace("\r\n", "\n")
    reason = prompt_source.check(role, {"type": "text", "prompt": text,
                                        "config": {"code_version": tasks.PROMPTS[role]}})
    if reason:
        slots = sorted(prompt_source.slots(tasks.TEMPLATES[role]))
        need = ", ".join("{{" + x + "}}" for x in slots)
        hints = {"PLACEHOLDERS": f" 자리표시자는 {need}만 그대로 써야 합니다.",
                 "DATA_RULE": " 맨 앞의 문서 본문 규칙 문장을 지우거나 바꾸지 마세요."}
        hint = hints.get(reason, "")
        raise EditorError(400, f"저장하지 않았습니다: {prompt_source.FALLBACKS[reason]}.{hint}")
    now = _get(lf, role, STAGING)
    if now and now.get("prompt") == text:
        raise EditorError(400, "staging 판과 글이 같아 저장하지 않았습니다.")
    try:
        made = lf.create_prompt(prompt_source.name_of(role), text, [STAGING],
                                {"code_version": tasks.PROMPTS[role]},
                                (message or "").strip()[:200] or f"RFP 프롬프트 관리에서 {name}")
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise EditorError(502, f"Langfuse에 저장하지 못했습니다: {exc}") from exc
    prompt_source.clear_cache()
    return {"role": role, "version": int(made["version"]), "label": STAGING}


# ── 화면 평가 ───────────────────────────────────────────────────────────

@dataclass
class EvalJob:
    job_id: int
    role: str
    staging_version: int
    started_by: str
    started_at: str
    status: str = "RUNNING"            # RUNNING | DONE | FAILED
    finished_at: str | None = None
    eval_id: int | None = None
    message: str | None = None         # 실패 이유
    metrics: list[dict] = field(default_factory=list)   # [{name, baseline, now}]
    regression: bool = False
    reasons: list[str] = field(default_factory=list)
    promote_block: str | None = None   # None이면 운영으로 올릴 수 있음
    promoted_version: int | None = None


_jobs: dict[int, EvalJob] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def latest_job(role: str) -> dict | None:
    with _lock:
        mine = [j for j in _jobs.values() if j.role == role]
        return asdict(max(mine, key=lambda j: j.job_id)) if mine else None


def start_eval(conn: psycopg.Connection, role: str, actor_id: int, wait: bool = False) -> dict:
    """staging 판으로 그 역할 문항을 평가하기 시작한다. 한 번에 하나만 돈다."""
    _role(role)
    name = _actor(conn, actor_id, EDIT_ROLES, "평가 돌리기")
    if role not in pe.METRICS:
        raise EditorError(400, "이 역할은 평가 문항이 없어 화면에서 평가할 수 없습니다.")
    if not _ai_ready():
        raise EditorError(409, AI_OFF)
    lf = _client()
    staged = _side(role, _get(lf, role, STAGING))
    if staged is None:
        raise EditorError(400, "staging 판이 없습니다. 먼저 고친 글을 저장하세요.")
    if not staged["usable"]:
        raise EditorError(400, f"staging 판을 쓸 수 없습니다: {staged['problem']}")
    with _lock:
        if any(j.status == "RUNNING" for j in _jobs.values()):
            raise EditorError(409, "다른 평가가 돌고 있습니다. 끝난 뒤 다시 누르세요.")
        job = EvalJob(max(_jobs, default=0) + 1, role, staged["version"], name, _now())
        _jobs[job.job_id] = job
    thread = threading.Thread(target=_run_eval, args=(job,), name=f"prompt-eval-{job.job_id}",
                              daemon=True)
    thread.start()
    if wait:                                   # 시험용
        thread.join()
    return asdict(job)


def _staging_set(role: str) -> prompt_source.PromptSet:
    """평가할 판 묶음: 그 역할은 staging, 나머지는 지금 운영 판."""
    prod = prompt_source.resolve(fresh=True)
    staged = prompt_source.fetch(STAGING)[role]
    if staged.source != "LANGFUSE":
        why = prompt_source.FALLBACKS[staged.fallback]
        raise pe.EvalError(f"staging 판을 쓸 수 없습니다: {why}")
    return prod | {role: staged}


def _baseline(conn: psycopg.Connection, settings) -> dict | None:
    base = pe.db_baseline(conn, EVAL_SET)
    if base is None:                          # DB에 기준선이 없으면 저장소 기준선 파일
        path = settings.seed_dir.parent / "eval" / "baseline.json"
        base = json.loads(path.read_text()) if path.exists() else None
    return base


def _run_eval(job: EvalJob) -> None:
    from rfp_agent.llm.client import ai_mode, make_llm

    settings = get_settings()
    fixture = pe.Fixture()
    try:
        llm = make_llm(settings)
        if llm is None:
            raise pe.EvalError(AI_OFF)
        full = pe.load_set(pe.find_set(EVAL_SET, settings))
        evalset = pe.EvalSet(full.name, full.version, [i for i in full.items if i.role == job.role],
                             [], full.threshold_pp)
        prompts = _staging_set(job.role)
        if prompts[job.role].langfuse_version != job.staging_version:
            raise pe.EvalError("평가를 시작하는 사이 staging 판이 바뀌었습니다. 다시 누르세요.")
        with tempfile.TemporaryDirectory() as tmp:
            names = {i.input["fixture"] for i in evalset.items if i.role == "assistant"}
            if names:
                fixture = pe.open_fixtures(names, settings, Path(tmp))
            with trace.session(None, "eval") as calls, prompt_source.use(prompts):
                result = pe.evaluate(evalset, llm, ai_mode(settings), pe.BASELINE_MIN_REPEAT,
                                     settings.rfp_eval_max_krw, False, fixture)
        with connect() as conn, prompt_source.use(prompts):
            base = _baseline(conn, settings)
            cmp = pe.compare(result, base) if result.status == "DONE" else None
            job.eval_id = pe.save(conn, result, note=f"화면 staging 평가: {job.role} "
                                  f"lf{job.staging_version}", run_by=job.started_by)
            trace.flush(conn, calls)
            conn.commit()
        job.metrics = _main_metrics(base, result)
        job.regression = bool(cmp and cmp.regression)
        job.reasons = list(cmp.reasons) if cmp else []
        job.promote_block = langfuse_ops.promote_block(
            label=STAGING, status=result.status, repeat=result.repeat,
            min_repeat=pe.BASELINE_MIN_REPEAT, has_baseline=bool(cmp and cmp.has_baseline),
            note=cmp.note if cmp else result.skip_reason, regression=job.regression,
            candidates=[prompts[job.role]])
        job.status = "DONE" if result.status == "DONE" else "FAILED"
        if result.status != "DONE":
            job.message = result.skip_reason or "평가를 끝내지 못했습니다."
    except (pe.EvalError, httpx.HTTPError) as exc:
        job.status, job.message = "FAILED", str(exc)
    except Exception as exc:  # noqa: BLE001 - 스레드 밖으로 못 올리니 화면에 실패로 남긴다
        log.exception("화면 프롬프트 평가 실패")
        job.status, job.message = "FAILED", f"평가 중 오류: {exc}"
    finally:
        pe.close_fixtures(fixture)
        job.finished_at = _now()


def _main_metrics(base: dict | None, result) -> list[dict]:
    """주 지표만 화면에: 기준선 값과 이번 반복 최솟값."""
    out = []
    for role, metrics in result.metrics.items():
        main = pe.primary_metric(role)
        cur = metrics.get(main)
        if cur is None:
            continue
        out.append({"name": pe._metric_name(role, main),
                    "now": cur.get("min"),
                    "baseline": ((base or {}).get("metrics", {}).get(role, {})
                                 .get(main) or {}).get("value")})
    return out


def promote(conn: psycopg.Connection, role: str, actor_id: int, job_id: int) -> dict:
    """화면 평가를 통과한 staging 판에 production 표시를 옮긴다(승인자)."""
    _role(role)
    _actor(conn, actor_id, PROMOTE_ROLES, "운영으로 올리기")
    with _lock:
        job = _jobs.get(job_id)
    if job is None or job.role != role:
        raise EditorError(404, "그 평가를 찾지 못했습니다. 다시 평가하세요.")
    if job.status != "DONE":
        raise EditorError(409, "평가가 끝나지 않았습니다.")
    if job.promote_block:
        raise EditorError(409, f"운영으로 올리지 않습니다: {job.promote_block}")
    lf = _client()
    staged = _side(role, _get(lf, role, STAGING))
    if staged is None or staged["version"] != job.staging_version:
        raise EditorError(409, "평가 뒤 staging 판이 바뀌었습니다. 다시 평가하세요.")
    try:
        lf.set_labels(prompt_source.name_of(role), job.staging_version, ["production"])
    except (httpx.TransportError, httpx.HTTPStatusError) as exc:
        raise EditorError(502, f"Langfuse에 표시를 옮기지 못했습니다: {exc}") from exc
    prompt_source.clear_cache()
    job.promoted_version = job.staging_version
    return {"role": role, "version": job.staging_version, "label": "production"}
