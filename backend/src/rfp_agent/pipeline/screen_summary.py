"""요약 상자 문장 (change add-screen-summary, 결정 Q1).

검토 상세(SCR-08)와 홈(SCR-03) 맨 위 "요약" 상자의 2~4문장을
정해진 틀에 숫자·이름·날짜를 채워 만든다.
언어 모델은 부르지 않는다(CR-01·07). 같은 데이터면 같은 문장이다(CR-11). 응답의 made_at만 달라진다.

문장 하나는 조각 목록: {"t": 글자, "kind": text|link|strong, "href": 화면 주소 또는 None}.
"""

from datetime import UTC, date, datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from rfp_agent.pipeline import datasheet, queries
from rfp_agent.pipeline.numbers import josa
from rfp_agent.pipeline.review import assignments_for
from rfp_agent.pipeline.tbe import with_unit

MAX_SENTENCES = 4
HOME_LIMIT = 200                       # 홈 화면이 부르는 검토 목록 수와 같다 (api.runs 기본 200)
REVIEWING = ("ENGINEER_REVIEW", "REJECTED", "FAILED")
# 내 차례 검토에서 먼저 할 일 (홈 오늘 할 일과 같은 말)
TODO_OF = {"ENGINEER_REVIEW": "판정 확인", "REJECTED": "반려 사유 확인", "FAILED": "다시 시도",
           "APPROVAL": "결재"}
DEPT_NAMES = {"COST": "견적", "QUALITY": "품질", "SALES": "영업"}


def T(t: str) -> dict:
    return {"t": t, "kind": "text", "href": None}


def A(t: str, href: str) -> dict:
    return {"t": t, "kind": "link", "href": href}


def S(t: str) -> dict:
    return {"t": t, "kind": "strong", "href": None}


def _after(name: str, pair: str) -> str:
    """이름 뒤 조사만: _after('GIS', '은(는)') → '는'."""
    return josa(name + pair)[len(name):]


def _by(who: str | None, rest: str, alone: str) -> str:
    """'최민정이 반려했습니다.' 사람 이름이 없으면 alone."""
    return f"{who}{_after(who, '이(가)')} {rest}" if who else alone


def day_text(d: date, today: date | None = None) -> str:
    """화면 dueText와 같다: 올해면 MM-DD, 아니면 YYYY-MM-DD."""
    today = today or date.today()
    return d.strftime("%m-%d") if d.year == today.year else d.isoformat()


def submit_by(due: date) -> date:
    """상신 권장일 = 제출 마감 2일 전 (화면 submitBy와 같음)."""
    return due - timedelta(days=2)


def title(r: dict) -> str:
    """화면 reviewTitle과 같은 이름. 사업명이 없으면 검토 번호."""
    if r.get("project_name"):
        return " · ".join(x for x in (r["project_name"], r.get("review_name")) if x)
    return r["review_no"]


def _result(sentences: list[list[dict]], meta: str | None = None) -> dict:
    return {"sentences": [s for s in sentences if s][:MAX_SENTENCES], "meta": meta,
            "written_by": "CODE", "made_at": datetime.now(UTC)}


# ---- 검토 요약 (SCR-08) ----

def _elapsed(run: dict) -> str | None:
    if not run.get("finished_at"):
        return None
    sec = int((run["finished_at"] - run["started_at"]).total_seconds())
    return f"{sec // 60}분 {sec % 60}초"


def _meta(run: dict) -> str:
    text = (f"문서 {run['documents']}개에서 요구사항 {run['requirements']}줄을 찾아 "
            f"{run['judgments']}줄 비교")
    took = _elapsed(run)
    return text + (f" · 분석 {took}" if took else "")


def _deviations(conn: psycopg.Connection, run_id: int) -> list[dict]:
    """먼저 볼 일탈 후보: 반려하지 않은 현재 일탈 후보, 판정 번호 순."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("""
            SELECT j.judgment_id, COALESCE(k.name_ko, tr.item_name_raw) AS item,
                   v.raw_text AS req, v.unit_raw AS req_unit, j.product_value_raw AS prod,
                   j.product_value_unit AS prod_unit
            FROM judgment j JOIN req_value v ON v.value_id = j.value_id
            JOIN requirement q ON q.requirement_id = j.requirement_id
            LEFT JOIN table_row tr ON tr.row_id = q.row_id
            LEFT JOIN item_key k ON k.item_key = v.item_key
            WHERE j.run_id = %s AND j.is_current AND j.result = 'DEVIATION_CANDIDATE'
              AND j.review_status <> 'REJECTED'
            ORDER BY j.judgment_id""", (run_id,)).fetchall()


def _decider(conn: psycopg.Connection, run_id: int) -> str | None:
    row = conn.execute("""
        SELECT u.user_name FROM approval a LEFT JOIN app_user u ON u.user_id = a.approver_id
        WHERE a.run_id = %s AND a.decision IS DISTINCT FROM 'WITHDRAWN'
        ORDER BY a.approval_id DESC LIMIT 1""", (run_id,)).fetchone()
    return row[0] if row else None


def _compare(j: dict) -> str:
    """'(요구 4000 A · 제품 3150 A)'. 단위는 원문 그대로(CR-10), 원문에 단위가 이미 있으면
    다시 붙이지 않는다(tbe.with_unit, 화면 withUnit과 같게). 없는 값은 뺀다."""
    req, prod = with_unit(j["req"], j["req_unit"]), with_unit(j["prod"], j["prod_unit"])
    inner = " · ".join(x for x in (req and f"요구 {req}", prod and f"제품 {prod}") if x)
    return f"({inner})" if inner else ""


def review_summary(conn: psycopg.Connection, run_id: int) -> dict | None:
    run = queries.run_summary(conn, run_id)
    if run is None:
        return None
    if run["stage"] == "PROCESSING":
        return _result([[T("분석 중이라 아직 요약할 판정이 없습니다.")]])
    if run["stage"] == "FAILED":
        return _result([[T("분석이 멈춰 판정이 없습니다. 다시 시도해야 판정이 나옵니다.")]])
    base = f"/reviews/{run_id}"
    out: list[list[dict]] = []

    who = _decider(conn, run_id)
    if run["stage"] == "REJECTED":
        out.append([T(_by(who, "반려했습니다. ", "결재가 반려되었습니다. ")),
                    A("이력", f"{base}?tab=log"),
                    T("에서 사유를 확인하고 판정을 고친 뒤 다시 상신해 주세요.")])
    elif run["stage"] == "APPROVED":
        out.append([T("결재가 승인되었습니다. "), A("제출본", f"{base}?tab=subm"),
                    T(" 탭에서 인계 패키지를 내려받을 수 있습니다.")])
    elif run["stage"] == "APPROVAL":
        out.append([T(_by(who, "결재 중입니다.", "결재 중입니다."))])

    n = queries.judgment_counts(conn, run_id)["by_result"]
    d, q, r = (n.get(k, 0) for k in ("DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW"))
    if d + q + r:
        s = [T(f"꼭 볼 것 {d + q + r}줄은 일탈 후보 {d}건, 질의 후보 {q}건, "
               f"확인 필요 {r}건입니다.")]
    else:
        s = [T("꼭 볼 판정이 없습니다.")]
    if run.get("due_date"):
        s += [T(" 상신 권장일은 "), S(day_text(submit_by(run["due_date"]))), T("입니다.")]
    out.append(s)

    devs = _deviations(conn, run_id)
    if devs:
        s = [T("먼저 볼 일탈 후보는 ")]
        for i, j in enumerate(devs[:2]):
            if i:
                s.append(T(", "))
            name = j["item"] or f"판정 {j['judgment_id']}"
            s.append(A(name, f"{base}/judgments/{j['judgment_id']}"))
            s.append(T(_compare(j)))
        s.append(T(f" 외 {len(devs) - 2}건입니다." if len(devs) > 2 else "입니다."))
        out.append(s)

    rev = run.get("revision")
    if rev:
        no = str(rev["no"])
        out.append([T(f"개정 {no}{_after(no, '을(를)')} 반영해 바뀐 줄 {rev['changed']}, "
                      f"추가된 줄 {rev['added']}, 사라진 줄 {rev['removed']}이 있습니다. "),
                    A("바뀐 줄 보기", f"{base}?rev=1")])

    empty = sum(s["empty"] for s in datasheet.datasheets(conn, run_id))
    if empty:
        out.append([T(f"데이터시트에 비어 있는 작성 칸이 {empty}개 있습니다. "),
                    A("데이터시트 채우기", f"{base}/datasheet"), T("에서 값을 넣어 주세요.")])
    return _result(out, _meta(run))


# ---- 홈 요약 (SCR-03) ----

def my_turn(user: dict | None, r: dict) -> bool:
    """홈 "내가 처리할 건"과 같은 규칙 (frontend components/myWork.ts myTurn)."""
    if user is None:
        return r["stage"] in REVIEWING
    me = user["user_id"]
    if user["role"] == "ENGINEER":
        return ((r["engineer_id"] == me and r["stage"] in REVIEWING)
                or (r["stage"] == "APPROVAL" and r["approver_id"] == me))
    if user["role"] == "APPROVER":
        return r["stage"] == "APPROVAL" and r["approver_id"] in (me, None)
    return False


def _by_due(r: dict) -> tuple:
    """오늘 할 일 순서: 마감 빠른 순(없으면 뒤), 같으면 검토 번호."""
    return (r["due_date"] or date.max, r["review_no"])


def _names(rows: list[dict], pair: str) -> list[dict]:
    """'A·B는' 처럼 검토 이름 링크를 잇고 마지막 이름에 조사를 붙인다."""
    parts: list[dict] = []
    for i, r in enumerate(rows):
        if i:
            parts.append(T("·"))
        parts.append(A(title(r), f"/reviews/{r['run_id']}"))
    parts.append(T(_after(title(rows[-1]), pair)))
    return parts


def home_summary(conn: psycopg.Connection, user_id: int | None) -> dict:
    user = None
    if user_id is not None:
        row = conn.execute("SELECT user_id, user_name, role FROM app_user WHERE user_id = %s",
                           (user_id,)).fetchone()
        user = {"user_id": row[0], "user_name": row[1], "role": row[2]} if row else None
    runs = queries.run_list(conn, HOME_LIMIT)
    mine = sorted((r for r in runs if my_turn(user, r)), key=_by_due)
    out: list[list[dict]] = []

    if mine:
        first = mine[0]
        s = [T(f"내 차례인 검토는 {len(mine)}건입니다. 오늘은 "),
             A(title(first), f"/reviews/{first['run_id']}"),
             T(f" {TODO_OF[first['stage']]}부터 하세요.")]
        if first["due_date"]:
            s += [T(" 상신 권장일은 "), S(day_text(submit_by(first["due_date"]))),
                  T(f", 제출 마감은 {day_text(first['due_date'])}입니다.")]
        out.append(s)
    else:
        out.append([T("지금 내 차례인 검토는 없습니다.")])

    role = user["role"] if user else None
    if role in DEPT_NAMES:
        left = [a for a in assignments_for(conn, role) if a["status"] != "DONE"]
        if left:
            out.append([T(f"회신하지 않은 {DEPT_NAMES[role]} 협조 요청이 {len(left)}건입니다. "),
                        A("협조 요청", "/todo"), T("에서 확인해 주세요.")])
        return _result(out)

    own = [r for r in runs if user is None or r["engineer_id"] == user["user_id"]]
    fails = [r for r in own if r["stage"] == "FAILED"]
    if fails:
        out.append(_names(fails[:3], "은(는)") + [T(" 분석이 멈춰 있어 다시 시도해야 합니다.")])

    wait = []
    ap = sorted((r for r in own if r["stage"] == "APPROVAL"), key=_by_due)
    if ap:
        who = ap[0]["approver"]
        wait += _names(ap[:1], "은(는)") + [T(" " + _by(who, "결재 중입니다.", "결재 중입니다."))]
    pending: dict[int, int] = {}
    for a in assignments_for(conn, None):
        if a["status"] != "DONE":
            pending[a["run_id"]] = pending.get(a["run_id"], 0) + 1
    co = sorted((r for r in own if r["stage"] == "ENGINEER_REVIEW" and pending.get(r["run_id"])),
                key=_by_due)
    if co:
        if wait:
            wait.append(T(" "))
        n = pending[co[0]["run_id"]]
        wait += _names(co[:1], "은(는)") + [T(f" 협조 회신 {n}건을 기다리고 있습니다.")]
    if wait:
        out.append(wait)
    return _result(out)
