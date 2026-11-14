"""뜻으로 찾기: 문장 벡터 저장, 사전 추가 후보(B5), 항목 연결 후보(B3) (change add-meaning-search).

벡터는 언어 모델(임베딩)에서 받아 글자 해시로 한 번만 저장한다(새 서버 없음, 코사인은 파이썬).
뜻 찾기는 후보·힌트만 만들고 판정·위험 조건을 바꾸지 않는다(CR-01·08).
같은 입력·같은 벡터면 같은 후보(CR-11).
"""

import hashlib
import logging
import math

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rfp_agent.llm.client import EMBED_MODEL, LLMFailure, embed_with_retry
from rfp_agent.pipeline.queries import _locations

log = logging.getLogger(__name__)


class _Lazy:
    """review가 run을 불러 순환을 피하려고 review 것을 쓸 때 부른다."""

    def __getattr__(self, name):
        from rfp_agent.pipeline import review
        return getattr(review, name)


_review = _Lazy()

RISK_MIN = 0.72             # 사전 추가 후보 문턱 (B5)
RISK_LIMIT = 20
ITEM_MIN = 0.85             # 항목 연결 후보 문턱 (B3)
ITEM_GAP = 0.03             # 1등 항목이 2등보다 앞서야 하는 만큼
MEMORY_MIN = 0.92           # 뜻이 비슷한 지난 확정 문턱 (B4)
CLAUSE_KINDS = ("BLANKET", "OPEN_SCOPE")
RULE_EDITORS = ("ENGINEER", "APPROVER")


def clean(text: str) -> str:
    return " ".join((text or "").split())


def text_hash(text: str) -> str:
    return hashlib.sha256(clean(text).encode()).hexdigest()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


def model_of(llm: object | None) -> str:
    """벡터 모델 이름. 테스트 대역은 embed_model을 둘 수 있다."""
    return getattr(llm, "embed_model", EMBED_MODEL)


def current_model() -> str:
    """화면에서 벡터를 찾을 때 쓰는 모델: 지금 설정의 벡터 모델 (add-ai-mode).

    정해지지 않았으면(AI 끄기 등) Gemini 벡터 이름으로 찾는다.
    DB 안에서만 찾으므로 밖으로 보내지 않는다.
    """
    from rfp_agent.config import get_settings
    from rfp_agent.llm.client import embed_model

    return embed_model(get_settings()) or EMBED_MODEL


def stored(conn: psycopg.Connection, texts: list[str], model: str = EMBED_MODEL
           ) -> dict[str, list[float]]:
    """저장된 벡터만 (글 → 벡터). 화면에서 물을 때는 언어 모델을 부르지 않는다."""
    hashes = {text_hash(t): t for t in texts if clean(t)}
    out = {}
    for h, vec in conn.execute("SELECT text_hash, vec FROM text_vector "
                               "WHERE model = %s AND text_hash = ANY(%s)", (model, list(hashes))):
        out[hashes[h]] = vec
    return out


def vectors(conn: psycopg.Connection, llm, texts: list[str]) -> dict[str, list[float]]:
    """글마다 벡터. 저장된 것은 다시 묻지 않고, 없는 것만 묻고 저장한다."""
    model = model_of(llm)
    unique = list(dict.fromkeys(clean(t) for t in texts if clean(t)))
    have = stored(conn, unique, model)
    missing = [t for t in unique if t not in have]
    if missing:
        got = dict(zip(missing, embed_with_retry(llm, missing), strict=True))
        # 글 해시 순서로 넣는다: 문서를 동시에 처리할 때 같은 글을 넣는 연결끼리 서로 기다리며
        # 막히지 않게(잠금 순서를 하나로) (add-document-processors)
        for text in sorted(got, key=text_hash):
            conn.execute("INSERT INTO text_vector (model, text_hash, vec) VALUES (%s, %s, %s) "
                         "ON CONFLICT DO NOTHING",
                         (model, text_hash(text), [float(x) for x in got[text]]))
            have[text] = got[text]
    return have


def _best(vec: list[float], pool: list[tuple[str, str, list[float]]]) -> tuple[float, str, str]:
    """(점수, 대상, 가까운 글) 중 가장 가까운 것. 같은 점수면 먼저 온 것."""
    best = (-1.0, "", "")
    for target, text, other in pool:
        score = cosine(vec, other)
        if score > best[0]:
            best = (score, target, text)
    return best


def _risk_texts(conn: psycopg.Connection, run_id: int, document_ids: list[int]):
    """(대상 문장, 비교할 문장·표현). 대상 = 위험 조건에 들지 않은 문장 요구사항."""
    flagged = conn.execute(
        """SELECT DISTINCT f.risk_kind, q.requirement_id, q.text_raw
             FROM risk_flag f JOIN risk_flag_member m USING (risk_id)
             JOIN requirement q USING (requirement_id)
            WHERE f.run_id = %s ORDER BY q.requirement_id""", (run_id,)).fetchall()
    # 같은 문장이 다른 문서의 대표 행으로 위험 조건에 들 수 있어 글자로도 뺀다
    in_risk = {rid for _, rid, _ in flagged} | {clean(t).lower() for _, _, t in flagged}
    examples = [(kind, text) for kind, _, text in flagged if kind in CLAUSE_KINDS]
    examples += [tuple(r) for r in conn.execute(
        "SELECT risk_kind, expression FROM risk_expression WHERE active AND risk_kind = ANY(%s) "
        "ORDER BY expr_id", (list(CLAUSE_KINDS),))]
    targets = [(rid, text) for rid, text in conn.execute(
        """SELECT requirement_id, text_raw FROM requirement
            WHERE document_id = ANY(%s) AND req_kind = 'REQUIREMENT' AND source_kind = 'SENTENCE'
            ORDER BY requirement_id""", (document_ids,))
        if rid not in in_risk and clean(text).lower() not in in_risk]
    return targets, examples


def _item_texts(conn: psycopg.Connection, document_ids: list[int]):
    """(항목키가 빈 표 항목 이름, 항목 표현). 판정 대상 문서(묶음 A·B)만."""
    names = conn.execute(
        """SELECT min(q.requirement_id), tr.item_name_raw
             FROM requirement q
             JOIN document d ON d.document_id = q.document_id AND d.judge_target
             JOIN table_row tr ON tr.row_id = q.row_id
            WHERE q.document_id = ANY(%s) AND tr.item_name_raw IS NOT NULL
              AND btrim(tr.item_name_raw) <> ''
              AND EXISTS (SELECT 1 FROM req_value v WHERE v.requirement_id = q.requirement_id)
              AND NOT EXISTS (SELECT 1 FROM req_value v WHERE v.requirement_id = q.requirement_id
                                AND v.item_key IS NOT NULL)
            GROUP BY tr.item_name_raw ORDER BY 1""", (document_ids,)).fetchall()
    known = {clean(a).lower() for (a,) in conn.execute("SELECT alias_text FROM item_alias")}
    out, seen = [], set(known)
    for rid, name in names:                         # 공백·대소문자만 다른 이름은 한 번
        if clean(name).lower() not in seen:
            seen.add(clean(name).lower())
            out.append((rid, clean(name)))
    names = out
    aliases = [tuple(r) for r in conn.execute(
        """SELECT k.item_key, a.alias_text FROM item_alias a
             JOIN item_key k ON k.item_key = a.item_key AND k.active
           UNION ALL SELECT item_key, name_ko FROM item_key WHERE active
           ORDER BY 1, 2""")]
    return names, aliases


def _item_candidate(vec, pool) -> tuple | None:
    """항목마다 최대 점수 → 1등 ≥ ITEM_MIN, 1등 − 2등 ≥ ITEM_GAP이면 후보."""
    per: dict[str, tuple[float, str]] = {}
    for key, text, other in pool:
        score = cosine(vec, other)
        if key not in per or score > per[key][0]:
            per[key] = (score, text)
    ranked = sorted(per.items(), key=lambda kv: (-kv[1][0], kv[0]))
    if not ranked:
        return None
    (key, (score, text)), second = ranked[0], ranked[1] if len(ranked) > 1 else None
    second_score = second[1][0] if second else 0.0
    if score < ITEM_MIN or score - second_score < ITEM_GAP:
        return None
    return key, score, text, second[0] if second else None, second_score if second else None


def _judged_texts(conn: psycopg.Connection, run_id: int) -> list[str]:
    """뜻이 비슷한 지난 확정(B4)에 쓸 판정 줄 요구 원문."""
    return [t for (t,) in conn.execute(
        "SELECT DISTINCT q.text_raw FROM judgment j JOIN requirement q USING (requirement_id) "
        "WHERE j.run_id = %s AND j.is_current ORDER BY 1", (run_id,))]


def _set_status(conn: psycopg.Connection, run_id: int, status: str) -> None:
    conn.execute("UPDATE review_run SET graph_state = graph_state || %s WHERE run_id = %s",
                 (Jsonb({"meaning": status}), run_id))


def build(conn: psycopg.Connection, run_id: int, document_ids: list[int], llm) -> int:
    """분석 단계: 벡터를 저장하고 후보를 만든다. 후보 수를 돌려준다.

    언어 모델이 없으면 NO_AI, 실패하면 SKIPPED로 남기고 분석은 계속한다.
    """
    conn.execute("DELETE FROM meaning_candidate WHERE run_id = %s AND status = 'OPEN'", (run_id,))
    if llm is None or not hasattr(llm, "embed"):
        _set_status(conn, run_id, "NO_AI")
        return 0
    targets, examples = _risk_texts(conn, run_id, document_ids)
    names, aliases = _item_texts(conn, document_ids)
    texts = ([t for _, t in targets] + [t for _, t in examples] + [n for _, n in names]
             + [a for _, a in aliases] + _judged_texts(conn, run_id))
    try:
        vec = vectors(conn, llm, texts)
    except LLMFailure as exc:
        log.warning("검토 %s 뜻 찾기 건너뜀: %s", run_id, exc)
        _set_status(conn, run_id, "SKIPPED")
        return 0
    rows = []
    pool = [(kind, clean(t), vec[clean(t)]) for kind, t in examples if clean(t) in vec]
    risk = []
    for rid, text in targets:
        score, kind, near = _best(vec[clean(text)], pool) if pool else (-1.0, "", "")
        if score >= RISK_MIN:
            risk.append((-round(score, 3), rid, text, near, kind, score))
    for _, rid, text, near, kind, score in sorted(risk)[:RISK_LIMIT]:
        rows.append(("RISK_SENTENCE", rid, text, near, kind, score, None, None))
    item_pool = [(key, clean(a), vec[clean(a)]) for key, a in aliases if clean(a) in vec]
    for rid, name in names:
        found = _item_candidate(vec[name], item_pool)
        if found:
            key, score, near, second, second_score = found
            rows.append(("ITEM_LINK", rid, name, near, key, score, second, second_score))
    hidden = {(k, clean(t).lower()) for k, t in conn.execute(
        """SELECT kind, text_raw FROM meaning_candidate
            WHERE status <> 'OPEN' AND (run_id = %s OR kind = 'ITEM_LINK')""", (run_id,))}
    for kind, rid, text, near, target, score, second, second_score in rows:
        if (kind, clean(text).lower()) in hidden:
            continue
        conn.execute(
            """INSERT INTO meaning_candidate (run_id, kind, requirement_id, text_raw, near_text,
                   target, score, second_target, second_score)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (run_id, kind, rid, text, near, target, round(score, 3), second,
             None if second_score is None else round(second_score, 3)))
    _set_status(conn, run_id, "DONE")
    return len(rows)


def status(conn: psycopg.Connection, run_id: int) -> str | None:
    row = conn.execute("SELECT graph_state->>'meaning' FROM review_run WHERE run_id = %s",
                       (run_id,)).fetchone()
    if row is None:
        raise _review.ReviewError(404, f"검토 실행 {run_id}이(가) 없습니다.")
    return row[0]


_SELECT = """
    SELECT c.candidate_id, c.run_id, c.kind, c.requirement_id, c.text_raw, c.near_text,
           c.target, c.score::float AS score, c.second_target,
           c.second_score::float AS second_score, c.status,
           'RV-' || extract(year FROM r.started_at)::int || '-' || lpad(r.run_id::text, 3, '0')
               AS review_no
      FROM meaning_candidate c JOIN review_run r ON r.run_id = c.run_id"""


def _with_locations(conn: psycopg.Connection, rows: list[dict]) -> list[dict]:
    for row in rows:
        row["locations"] = _locations(conn, [row["requirement_id"]], row["run_id"]).get(
            row["requirement_id"], [])
    return [r for r in rows if r["locations"]]          # 위치가 없으면 내지 않는다 (CR-02)


def risk_candidates(conn: psycopg.Connection, run_id: int) -> dict:
    """위험 조건 탭: 뜻 찾기 상태와 사전 추가 후보."""
    state = status(conn, run_id)
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(_SELECT + """ WHERE c.run_id = %s AND c.kind = 'RISK_SENTENCE'
                                          AND c.status = 'OPEN'
                                        ORDER BY c.score DESC, c.requirement_id""",
                           (run_id,)).fetchall()
    return {"status": state, "items": _with_locations(conn, rows)}


def item_candidates(conn: psycopg.Connection) -> list[dict]:
    """판정 규칙 화면: 열린 항목 연결 후보. 같은 이름은 가장 최근 검토의 것 하나.

    이미 사전에 들어간 이름은 뺀다.
    """
    known = {clean(a).lower() for (a,) in conn.execute("SELECT alias_text FROM item_alias")}
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(_SELECT + """ WHERE c.kind = 'ITEM_LINK' AND c.status = 'OPEN'
                                        ORDER BY c.run_id DESC, c.score DESC,
                                                 c.candidate_id""").fetchall()
    seen, out = set(), []
    for row in rows:
        name = clean(row["text_raw"]).lower()
        if name in known or name in seen:
            continue
        seen.add(name)
        out.append(row)
    return _with_locations(conn, out)


def _candidate(conn: psycopg.Connection, candidate_id: int, kind: str) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(_SELECT + " WHERE c.candidate_id = %s AND c.kind = %s",
                          (candidate_id, kind)).fetchone()
    if row is None:
        raise _review.ReviewError(404, f"후보 {candidate_id}이(가) 없습니다.")
    if row["status"] != "OPEN":
        raise _review.ReviewError(409, "이미 처리한 후보입니다.")
    return row


def _editor(conn: psycopg.Connection, actor_id: int | None) -> int:
    actor_id = actor_id or _review.default_user(conn, "ENGINEER")
    if _review._user_role(conn, actor_id) not in RULE_EDITORS:
        raise _review.ReviewError(403, "규칙 사전은 검토 엔지니어·승인자만 고칠 수 있습니다.")
    return actor_id


def _close(conn: psycopg.Connection, kind: str, text: str, status_: str, actor_id: int) -> None:
    """같은 이름의 열린 후보를 모두 닫는다(다른 검토 포함)."""
    conn.execute(
        """UPDATE meaning_candidate SET status = %s, decided_by = %s, decided_at = now()
            WHERE kind = %s AND status = 'OPEN' AND lower(btrim(text_raw)) = lower(btrim(%s))""",
        (status_, actor_id, kind, text))


def accept_item(conn: psycopg.Connection, candidate_id: int, actor_id: int | None = None) -> dict:
    """항목 연결 후보를 받아들인다: 항목의 같은 뜻 표현에 이름을 더한다(고침 이력)."""
    from rfp_agent.pipeline import rule_edit

    row = _candidate(conn, candidate_id, "ITEM_LINK")
    actor_id = _editor(conn, actor_id)
    d = rule_edit.dictionary("items")
    current = d.by_id(conn, row["target"])
    if current is None:
        raise _review.ReviewError(409, f"항목 {row['target']}이(가) 사전에 없습니다.")
    value = d.value_of(current)
    value["aliases"] = [*value.get("aliases", []), row["text_raw"]]
    try:
        reason = f"뜻으로 찾은 연결 후보 (점수 {row['score']:.3f}, {row['review_no']})"
        edit = rule_edit.update(conn, "items", row["target"], value, reason, actor_id)
    except rule_edit.RuleEditError as exc:
        raise _review.ReviewError(exc.status, str(exc)) from exc
    _close(conn, "ITEM_LINK", row["text_raw"], "ACCEPTED", actor_id)
    conn.commit()
    return edit


def hide_item(conn: psycopg.Connection, candidate_id: int, actor_id: int | None = None) -> None:
    row = _candidate(conn, candidate_id, "ITEM_LINK")
    actor_id = _editor(conn, actor_id)
    _close(conn, "ITEM_LINK", row["text_raw"], "HIDDEN", actor_id)
    conn.commit()
