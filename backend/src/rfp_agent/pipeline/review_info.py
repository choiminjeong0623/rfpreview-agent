"""검토 정보(사업명, 검토명, 고객사, 국가, 제출 마감일, 담당 엔지니어) 저장과 고치기.

add-review-info. 사람이 넣는 값이라 원문 위치를 붙이지 않고, 판정·후보 계산에 쓰지 않는다.
빈칸을 시스템이 채우지 않는다 (CR-04).
"""

from datetime import date

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline.review import ReviewError, log

FIELDS = ("project_name", "review_name", "customer_name", "country", "due_date", "engineer_id")
TEXT_LIMITS = {"project_name": 200, "review_name": 200, "customer_name": 200, "country": 60}


def clean(info: dict) -> dict:
    """보낸 칸만 남기고, 빈 문자열은 비우기(None)로 본다. 글자 앞뒤 공백은 지운다."""
    out = {}
    for key in FIELDS:
        if key not in info:
            continue
        value = info[key]
        if isinstance(value, str):
            value = value.strip() or None
        if key in TEXT_LIMITS and value is not None and len(value) > TEXT_LIMITS[key]:
            raise ReviewError(400, f"{key}은(는) {TEXT_LIMITS[key]}자까지입니다.")
        if key == "due_date" and isinstance(value, str):
            try:
                value = date.fromisoformat(value)
            except ValueError as exc:
                raise ReviewError(400, f"마감일 형식이 틀렸습니다: {value} (YYYY-MM-DD)") from exc
        out[key] = value
    return out


NEED_DUE = "제출 마감일을 입력해 주세요."


def require_due(info: dict) -> None:
    """제출 마감일은 시작할 때 꼭 받는다 (update-due-required). 다른 칸은 비어도 된다."""
    if clean(info).get("due_date") is None:
        raise ReviewError(400, NEED_DUE)


def fill_due(conn: psycopg.Connection, due_in: int, actor_id: int) -> list[int]:
    """마감이 빈 검토를 시작일 + due_in일로 채운다. 사람이 개발·시연 DB에서 돌리는 명령용(CR-04)."""
    rows = conn.execute("""UPDATE review_run SET due_date = started_at::date + %s
                           WHERE due_date IS NULL RETURNING run_id, due_date""",
                        (due_in,)).fetchall()
    for run_id, due in rows:
        log(conn, run_id, "review_run", run_id, "EDIT", {"due_date": None},
            {"due_date": due.isoformat()}, "시연 데이터 마감 채움 (rfp-db fill-due)", actor_id)
    conn.commit()
    return [r[0] for r in rows]


def _role(conn: psycopg.Connection, user_id: int) -> str | None:
    row = conn.execute("SELECT role FROM app_user WHERE user_id = %s", (user_id,)).fetchone()
    return row[0] if row else None


def check_engineer(conn: psycopg.Connection, engineer_id: int | None) -> None:
    """담당 엔지니어는 엔지니어 역할 사용자만 될 수 있다."""
    if engineer_id is None:
        return
    role = _role(conn, engineer_id)
    if role is None:
        raise ReviewError(404, f"사용자 {engineer_id}이(가) 없습니다.")
    if role != "ENGINEER":
        raise ReviewError(400, "담당 엔지니어는 엔지니어 역할 사용자만 될 수 있습니다.")


def save_on_start(conn: psycopg.Connection, run_id: int, info: dict, actor_id: int | None) -> None:
    """검토를 시작할 때 받은 검토 정보를 저장한다. 담당이 비고 시작한 사람이 엔지니어면 그 사람."""
    values = clean(info)
    if values.get("engineer_id") is None and actor_id is not None \
            and _role(conn, actor_id) == "ENGINEER":
        values["engineer_id"] = actor_id
    check_engineer(conn, values.get("engineer_id"))
    if values:
        sets = ", ".join(f"{k} = %({k})s" for k in values)
        conn.execute(f"UPDATE review_run SET {sets} WHERE run_id = %(run_id)s",
                     values | {"run_id": run_id})
    conn.commit()


def _as_json(values: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in values.items()}


def current(conn: psycopg.Connection, run_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(f"SELECT {', '.join(FIELDS)} FROM review_run WHERE run_id = %s",
                          (run_id,)).fetchone()
    if row is None:
        raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
    return row


def update(conn: psycopg.Connection, run_id: int, info: dict, actor_id: int | None) -> dict:
    """검토 정보를 고친다. 단계와 관계없이 고칠 수 있고, 바뀐 칸만 이력 한 건으로 남긴다."""
    before = current(conn, run_id)
    values = clean(info)
    if "engineer_id" in values:
        check_engineer(conn, values["engineer_id"])
    if "due_date" in values and values["due_date"] is None:
        raise ReviewError(400, "제출 마감일은 비울 수 없습니다.")
    changed = {k: v for k, v in values.items() if before[k] != v}
    if not changed:
        return {"changed": []}
    if "project_name" in changed and conn.execute(
            "SELECT business_id FROM review_run WHERE run_id = %s", (run_id,)).fetchone()[0]:
        raise ReviewError(400, "사업에 연결된 검토의 사업명은 사업 상세에서 고칩니다.")
    if actor_id is None:
        actor_id = conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'"
                                ).fetchone()[0]
    elif _role(conn, actor_id) is None:
        raise ReviewError(400, f"사용자 {actor_id}이(가) 없습니다.")
    sets = ", ".join(f"{k} = %({k})s" for k in changed)
    conn.execute(f"UPDATE review_run SET {sets} WHERE run_id = %(run_id)s",
                 changed | {"run_id": run_id})
    log(conn, run_id, "review_run", run_id, "EDIT", _as_json({k: before[k] for k in changed}),
        _as_json(changed), "검토 정보 고치기", actor_id)
    conn.commit()
    return {"changed": sorted(changed)}
