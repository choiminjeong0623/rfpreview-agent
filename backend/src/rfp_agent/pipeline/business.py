"""사업 현황 (add-project-status): 사업 만들기·고치기·이력, 검토 연결, 범위별 진행 상태, 내 사업.

사업 정보는 사람이 넣는 값이라 원문 위치를 붙이지 않고 판정·후보 계산에 쓰지 않는다.
빈칸을 시스템이 채우지 않는다 (CR-04). 진행 상태는 저장하지 않고 연결된 검토의 단계와
확인하지 않은 협조 요청에서 코드 규칙으로 계산한다 (CR-01·11). 제출 완료는 사람이 표시한다 (CR-08).
`project` 표(FR-06 값 불일치 비교 범위)와는 잇지 않는다.
"""

import json
from datetime import date

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rfp_agent.pipeline.review import ReviewError, log

FIELDS = ("business_name", "customer_name", "country", "tender_no", "order_mode", "due_date",
          "sales_id")
TEXT_LIMITS = {"business_name": 200, "customer_name": 200, "country": 60, "tender_no": 80,
               "order_mode": 200}

# 사업 번호 PJ-<만든 연도>-<번호 세 자리>
BUSINESS_NO = ("'PJ-' || extract(year FROM b.created_at)::int || '-' "
               "|| lpad(b.business_id::text, 3, '0')")

# 범위(연결 검토) 하나의 진행 상태. 위에서부터 처음 맞는 것 (design 3).
# 협조 대기는 홈 화면 "협조 대기" 열과 같은 기준: 회신 받지 않은(안 보냄·메일 보냄) 협조 요청이
# 남은 담당자 확인 (update-role-handoff-mail)
STATE = """
    CASE WHEN b.submitted_at IS NOT NULL THEN 'done'
         WHEN r.stage = 'PROCESSING' THEN 'an'
         WHEN r.stage = 'FAILED' THEN 'fail'
         WHEN r.stage = 'ENGINEER_REVIEW' AND EXISTS (
              SELECT 1 FROM assignment a WHERE a.run_id = r.run_id AND a.status <> 'DONE')
              THEN 'co'
         WHEN r.stage = 'ENGINEER_REVIEW' THEN 'chk'
         WHEN r.stage = 'APPROVAL' THEN 'ap'
         WHEN r.stage = 'REJECTED' THEN 'rej'
         ELSE 'sub' END"""

# 내 역할: 엔지니어 → 결재자 → 협조 → 영업 → 만든 사람 순으로 하나
ROLE_ORDER = ("ENGINEER", "APPROVER", "HELPER", "SALES", "CREATOR")


def _rows(conn: psycopg.Connection, sql: str, params) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _role(conn: psycopg.Connection, user_id: int) -> str | None:
    row = conn.execute("SELECT role FROM app_user WHERE user_id = %s", (user_id,)).fetchone()
    return row[0] if row else None


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
    if "business_name" in out and out["business_name"] is None:
        raise ReviewError(400, "사업명이 필요합니다.")
    return out


def check_sales(conn: psycopg.Connection, sales_id: int | None) -> None:
    """영업 담당은 영업 역할 사용자만 될 수 있다."""
    if sales_id is None:
        return
    role = _role(conn, sales_id)
    if role is None:
        raise ReviewError(404, f"사용자 {sales_id}이(가) 없습니다.")
    if role != "SALES":
        raise ReviewError(400, "영업 담당은 영업 역할 사용자만 될 수 있습니다.")


def _actor(conn: psycopg.Connection, actor_id: int | None) -> int:
    """로그인이 없어 작업자를 안 보내면 첫 엔지니어로 둔다 (검토 정보 고치기와 같음)."""
    if actor_id is None:
        row = conn.execute("SELECT min(user_id) FROM app_user WHERE role = 'ENGINEER'").fetchone()
        if row[0] is None:
            raise ReviewError(400, "엔지니어 역할 사용자가 없습니다.")
        return row[0]
    if _role(conn, actor_id) is None:
        raise ReviewError(400, f"사용자 {actor_id}이(가) 없습니다.")
    return actor_id


def _as_json(value):
    return Jsonb(json.loads(json.dumps(value, default=str)))


def _log(conn: psycopg.Connection, business_id: int, field: str, before, after,
         actor_id: int) -> None:
    conn.execute("""INSERT INTO business_log (business_id, field, before_value, after_value,
                                              actor_id) VALUES (%s, %s, %s, %s, %s)""",
                 (business_id, field, _as_json(before), _as_json(after), actor_id))


def _get(conn: psycopg.Connection, business_id: int) -> dict:
    rows = _rows(conn, f"SELECT {', '.join(FIELDS)}, submitted_at FROM business "
                       "WHERE business_id = %s", (business_id,))
    if not rows:
        raise ReviewError(404, f"사업 {business_id}이(가) 없습니다.")
    return rows[0]


def create(conn: psycopg.Connection, info: dict, actor_id: int | None,
           commit: bool = True) -> int:
    values = clean(info)
    if not values.get("business_name"):
        raise ReviewError(400, "사업명이 필요합니다.")
    check_sales(conn, values.get("sales_id"))
    values["created_by"] = _actor(conn, actor_id)
    cols = ", ".join(values)
    business_id = conn.execute(
        f"INSERT INTO business ({cols}) VALUES ({', '.join(f'%({k})s' for k in values)}) "
        "RETURNING business_id", values).fetchone()[0]
    if commit:
        conn.commit()
    return business_id


def _sync_names(conn: psycopg.Connection, business_id: int, name: str, actor_id: int) -> None:
    """연결된 검토의 사업명을 사업명에 맞춘다 (홈 "사업별"·검토 목록이 같은 이름을 보인다)."""
    for run_id, before in conn.execute(
            "SELECT run_id, project_name FROM review_run WHERE business_id = %s "
            "AND project_name IS DISTINCT FROM %s", (business_id, name)).fetchall():
        conn.execute("UPDATE review_run SET project_name = %s WHERE run_id = %s", (name, run_id))
        log(conn, run_id, "review_run", run_id, "EDIT", {"project_name": before},
            {"project_name": name}, "사업명에 맞춤", actor_id)


def update(conn: psycopg.Connection, business_id: int, info: dict,
           actor_id: int | None) -> dict:
    """사업 정보를 고친다. 바뀐 칸마다 이력 한 건."""
    before = _get(conn, business_id)
    values = clean(info)
    if "sales_id" in values:
        check_sales(conn, values["sales_id"])
    changed = {k: v for k, v in values.items() if before[k] != v}
    if not changed:
        return {"changed": []}
    actor = _actor(conn, actor_id)
    sets = ", ".join(f"{k} = %({k})s" for k in changed)
    conn.execute(f"UPDATE business SET {sets} WHERE business_id = %(id)s",
                 changed | {"id": business_id})
    for key, value in changed.items():
        _log(conn, business_id, key, before[key], value, actor)
    if "business_name" in changed:
        _sync_names(conn, business_id, changed["business_name"], actor)
    conn.commit()
    return {"changed": sorted(changed)}


def link(conn: psycopg.Connection, run_id: int, business_id: int | None,
         actor_id: int | None, commit: bool = True) -> None:
    """검토를 사업에 연결하거나(business_id) 해제한다(None). 검토 이력에 남는다.

    연결하면 검토의 사업명을 사업명으로 맞춘다. FR-06 비교 범위(project_id)는 바꾸지 않는다.
    """
    row = conn.execute("SELECT business_id, project_name FROM review_run WHERE run_id = %s",
                       (run_id,)).fetchone()
    if row is None:
        raise ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
    old_id, old_name = row
    name = old_name
    if business_id is not None:
        found = conn.execute("SELECT business_name FROM business WHERE business_id = %s",
                             (business_id,)).fetchone()
        if found is None:
            raise ReviewError(404, f"사업 {business_id}이(가) 없습니다.")
        name = found[0]
    if old_id == business_id and old_name == name:
        return
    actor = _actor(conn, actor_id)
    conn.execute("UPDATE review_run SET business_id = %s, project_name = %s WHERE run_id = %s",
                 (business_id, name, run_id))
    log(conn, run_id, "review_run", run_id, "EDIT",
        {"business_id": old_id, "project_name": old_name},
        {"business_id": business_id, "project_name": name},
        "사업 연결" if business_id is not None else "사업 연결 해제", actor)
    if commit:
        conn.commit()


def check_start(conn: psycopg.Connection, business_id: int | None,
                new_business_name: str | None) -> None:
    """검토를 시작하기 전에 사업 칸을 검사한다 (실행을 만들기 전에 막는다)."""
    if business_id is not None and new_business_name:
        raise ReviewError(400, "기존 사업과 새 사업 중 하나만 고릅니다.")
    if business_id is not None and conn.execute(
            "SELECT 1 FROM business WHERE business_id = %s", (business_id,)).fetchone() is None:
        raise ReviewError(404, f"사업 {business_id}이(가) 없습니다.")
    if new_business_name is not None and not new_business_name.strip():
        raise ReviewError(400, "사업명이 필요합니다.")


def link_on_start(conn: psycopg.Connection, run_id: int, business_id: int | None,
                  new_business_name: str | None, info: dict, actor_id: int | None) -> None:
    """검토를 시작할 때 사업에 연결한다. 새 사업은 검토 정보의 고객사·국가·마감으로 만든다."""
    if new_business_name:
        values = {k: info[k] for k in ("customer_name", "country", "due_date") if info.get(k)}
        business_id = create(conn, values | {"business_name": new_business_name}, actor_id,
                             commit=False)
    if business_id is not None:
        link(conn, run_id, business_id, actor_id, commit=False)
    conn.commit()


def set_submitted(conn: psycopg.Connection, business_id: int, submitted: bool,
                  actor_id: int | None) -> None:
    """제출 완료 표시·취소. 연결 검토가 하나 이상이고 모두 승인되었을 때만 표시한다."""
    before = _get(conn, business_id)["submitted_at"]
    if submitted:
        stages = [r[0] for r in conn.execute(
            "SELECT stage FROM review_run WHERE business_id = %s", (business_id,))]
        if not stages or any(s != "APPROVED" for s in stages):
            raise ReviewError(409, "연결된 검토가 모두 승인되어야 제출 완료로 표시할 수 있습니다.")
        if before is not None:
            return
    elif before is None:
        return
    actor = _actor(conn, actor_id)
    after = conn.execute(
        "UPDATE business SET submitted_at = CASE WHEN %(on)s THEN now() END, "
        "submitted_by = CASE WHEN %(on)s THEN %(actor)s END WHERE business_id = %(id)s "
        "RETURNING submitted_at", {"on": submitted, "actor": actor, "id": business_id}
    ).fetchone()[0]
    _log(conn, business_id, "submitted", before, after, actor)
    conn.commit()


def _roles(conn: psycopg.Connection, user_id: int) -> dict[int, list[str]]:
    """사용자가 관여한 사업 → 역할 목록 (ROLE_ORDER 순)."""
    rows = conn.execute("""
        SELECT r.business_id, 'ENGINEER' FROM review_run r
         WHERE r.business_id IS NOT NULL AND r.engineer_id = %(u)s
        UNION SELECT r.business_id, 'APPROVER' FROM review_run r JOIN approval p USING (run_id)
         WHERE r.business_id IS NOT NULL AND p.approver_id = %(u)s AND p.withdrawn_at IS NULL
        UNION SELECT r.business_id, 'HELPER' FROM review_run r JOIN assignment a USING (run_id)
         WHERE r.business_id IS NOT NULL AND a.assignee_id = %(u)s
        UNION SELECT business_id, 'SALES' FROM business WHERE sales_id = %(u)s
        UNION SELECT business_id, 'CREATOR' FROM business WHERE created_by = %(u)s""",
                        {"u": user_id}).fetchall()
    out: dict[int, list[str]] = {}
    for business_id, role in rows:
        out.setdefault(business_id, []).append(role)
    return {k: sorted(v, key=ROLE_ORDER.index) for k, v in out.items()}


def _ranges(conn: psycopg.Connection, business_ids: list[int]) -> dict[int, list[dict]]:
    rows = _rows(conn, f"""
        SELECT r.business_id, r.run_id,
               'RV-' || extract(year FROM r.started_at)::int || '-' || lpad(r.run_id::text, 3, '0')
                   AS review_no,
               r.review_name, r.stage, r.due_date, r.started_at, r.engineer_id,
               (SELECT user_name FROM app_user WHERE user_id = r.engineer_id) AS engineer_name,
               (SELECT count(*) FROM assignment a WHERE a.run_id = r.run_id
                  AND a.status <> 'DONE') AS open_requests,
               {STATE} AS state
        FROM review_run r JOIN business b USING (business_id)
        WHERE r.business_id = ANY(%s) ORDER BY r.run_id""", (business_ids,))
    out: dict[int, list[dict]] = {i: [] for i in business_ids}
    for row in rows:
        out[row.pop("business_id")].append(row)
    return out


def _base(conn: psycopg.Connection, where: str, params) -> list[dict]:
    return _rows(conn, f"""
        SELECT b.business_id, {BUSINESS_NO} AS business_no, b.business_name, b.customer_name,
               b.country, b.tender_no, b.order_mode, b.due_date AS business_due_date,
               COALESCE(b.due_date, (SELECT min(r.due_date) FROM review_run r
                                      WHERE r.business_id = b.business_id)) AS due_date,
               b.sales_id, (SELECT user_name FROM app_user WHERE user_id = b.sales_id)
                   AS sales_name,
               b.created_by, (SELECT user_name FROM app_user WHERE user_id = b.created_by)
                   AS created_by_name,
               b.created_at, b.submitted_at
        FROM business b WHERE {where} ORDER BY b.business_id""", params)


def _finish(rows: list[dict], ranges: dict[int, list[dict]], roles: dict[int, list[str]] | None,
            today: date) -> list[dict]:
    for row in rows:
        due = row["due_date"]
        row["days_left"] = (due - today).days if due else None
        row["ranges"] = ranges[row["business_id"]]
        mine = roles.get(row["business_id"], []) if roles is not None else []
        row["my_role"] = mine[0] if mine else None
    return rows


def business_list(conn: psycopg.Connection, user_id: int | None = None,
                  scope: str = "all") -> dict:
    """사업 목록과 요약. scope=mine이면 user_id가 관여한 사업만."""
    today = conn.execute("SELECT CURRENT_DATE").fetchone()[0]
    roles = _roles(conn, user_id) if user_id is not None else None
    rows = _base(conn, "TRUE", ())
    if scope == "mine":
        rows = [r for r in rows if roles and r["business_id"] in roles]
    items = _finish(rows, _ranges(conn, [r["business_id"] for r in rows]), roles, today)
    open_items = [r for r in items if r["submitted_at"] is None]
    summary = {
        "open": len(open_items),
        "due3": sum(1 for r in open_items if r["days_left"] is not None
                    and 0 <= r["days_left"] <= 3),
        "overdue": sum(1 for r in open_items if r["days_left"] is not None
                       and r["days_left"] < 0),
    }
    return {"summary": summary, "items": items}


def detail(conn: psycopg.Connection, business_id: int, user_id: int | None = None) -> dict:
    today = conn.execute("SELECT CURRENT_DATE").fetchone()[0]
    rows = _base(conn, "b.business_id = %s", (business_id,))
    if not rows:
        raise ReviewError(404, f"사업 {business_id}이(가) 없습니다.")
    roles = _roles(conn, user_id) if user_id is not None else None
    item = _finish(rows, _ranges(conn, [business_id]), roles, today)[0]
    item["people"] = _people(conn, business_id)
    item["schedule"] = _schedule(conn, business_id, item)
    item["documents"] = _rows(conn, """
        SELECT r.run_id,
               'RV-' || extract(year FROM r.started_at)::int || '-' || lpad(r.run_id::text, 3, '0')
                   AS review_no,
               r.review_name, d.file_name, d.doc_kind, d.bundle
        FROM review_run r JOIN run_document rd USING (run_id) JOIN document d USING (document_id)
        WHERE r.business_id = %s ORDER BY r.run_id, d.file_no""", (business_id,))
    return item


def _people(conn: psycopg.Connection, business_id: int) -> list[dict]:
    """사내 담당자: 연결 검토의 엔지니어, 결재자, 협조 요청 받은 사람, 영업. 사람·역할마다 한 줄."""
    rows = _rows(conn, """
        WITH parts AS (
          SELECT r.engineer_id AS user_id, 'ENGINEER' AS part, r.run_id, r.review_name
            FROM review_run r WHERE r.business_id = %(b)s AND r.engineer_id IS NOT NULL
          UNION SELECT p.approver_id, 'APPROVER', r.run_id, r.review_name
            FROM review_run r JOIN approval p USING (run_id)
           WHERE r.business_id = %(b)s AND p.approver_id IS NOT NULL AND p.withdrawn_at IS NULL
          UNION SELECT a.assignee_id, 'HELPER', r.run_id, r.review_name
            FROM review_run r JOIN assignment a USING (run_id)
           WHERE r.business_id = %(b)s AND a.assignee_id IS NOT NULL
          UNION SELECT sales_id, 'SALES', NULL, NULL FROM business
           WHERE business_id = %(b)s AND sales_id IS NOT NULL)
        SELECT p.user_id, u.user_name, u.role, p.part,
               array_agg(DISTINCT p.run_id) FILTER (WHERE p.run_id IS NOT NULL) AS run_ids,
               string_agg(DISTINCT p.review_name, ', ') AS scope
        FROM parts p JOIN app_user u USING (user_id)
        GROUP BY p.user_id, u.user_name, u.role, p.part""", {"b": business_id})
    for row in rows:
        row["run_ids"] = sorted(row["run_ids"] or [])
    return sorted(rows, key=lambda r: (ROLE_ORDER.index(r["part"]), r["user_name"]))


def _schedule(conn: psycopg.Connection, business_id: int, item: dict) -> list[dict]:
    """일정: 사업 마감, 검토 시작·상신·결정, 제출 완료. 날짜 순."""
    rows = _rows(conn, """
        SELECT r.started_at::date AS day, 'START' AS kind, r.run_id FROM review_run r
         WHERE r.business_id = %(b)s
        UNION ALL SELECT p.requested_at::date, 'REQUEST', r.run_id
          FROM review_run r JOIN approval p USING (run_id)
         WHERE r.business_id = %(b)s AND p.withdrawn_at IS NULL
        UNION ALL SELECT p.decided_at::date, p.decision, r.run_id
          FROM review_run r JOIN approval p USING (run_id)
         WHERE r.business_id = %(b)s AND p.decided_at IS NOT NULL
        UNION ALL SELECT r.due_date, 'RUN_DUE', r.run_id FROM review_run r
         WHERE r.business_id = %(b)s AND r.due_date IS NOT NULL""", {"b": business_id})
    if item["business_due_date"] is not None:
        rows.append({"day": item["business_due_date"], "kind": "DUE", "run_id": None})
    if item["submitted_at"] is not None:
        rows.append({"day": item["submitted_at"].date(), "kind": "SUBMITTED", "run_id": None})
    nos = {r["run_id"]: r["review_no"] for r in item["ranges"]}
    for row in rows:
        row["review_no"] = nos.get(row["run_id"])
    return sorted(rows, key=lambda r: (r["day"], r["kind"], r["run_id"] or 0))


def history(conn: psycopg.Connection, business_id: int) -> list[dict]:
    _get(conn, business_id)
    return _rows(conn, """
        SELECT l.log_id, l.field, l.before_value, l.after_value, l.actor_id,
               u.user_name AS actor_name, l.acted_at
        FROM business_log l JOIN app_user u ON u.user_id = l.actor_id
        WHERE l.business_id = %s ORDER BY l.log_id DESC""", (business_id,))

