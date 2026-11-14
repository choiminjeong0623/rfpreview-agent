"""검토 도우미: 읽기 도구만 쓰는 에이전트 (change add-review-assistant, FR-17).

AI는 읽기 도구(요구사항 찾기·판정 찾기·한 줄 보기)를 고르고 답 문장을 쓰기만 한다.
도구는 이 모듈의 함수이고 DB를 읽기만 한다. 값을 바꾸거나 판정하는 도구는 없다 (CR-01·08).
코드가 답 문장마다 근거 번호와 숫자를 대조해 어긋난 문장은 뺀다 (CR-02·07).
"""

import re

import psycopg
from psycopg.rows import dict_row

from rfp_agent.llm.client import LLM, LLMConfigError, LLMFailure
from rfp_agent.llm.tasks import NUMBER, TYPE_CODES, assistant_step, one_line
from rfp_agent.pipeline.queries import _locations
from rfp_agent.pipeline.review import ReviewError

MAX_SEARCHES = 3            # AI가 도구를 쓰는 최대 횟수
LIMIT = 15                  # 도구 한 번에 돌려주는 최대 줄 수
CLOSED_STAGES = ("PROCESSING", "FAILED")
NOT_FOUND = "근거를 찾지 못했습니다."
# AI 답이 없어 글자로 찾을 때 알리는 까닭 (update-assistant-panel, CR-12).
# "맞는 줄 없음"은 화면이 정한다.
NO_AI = "AI를 쓰지 않는 설정"
AI_CONFIG = "AI 키·모델 설정 오류 — 설정 확인"
AI_FAILED = "AI가 답하지 못함"
JUDGMENT_RESULTS = ("COMPLY", "DEVIATION_CANDIDATE", "QUERY_CANDIDATE", "NEEDS_REVIEW",
                    "WARRANTY_TO_FILL")
_WORD = re.compile(r"[\w.\-/]{2,}", re.UNICODE)

_REQ = """
    SELECT q.requirement_id, q.text_raw, tt.type_code
      FROM requirement q
      JOIN run_document rd ON rd.document_id = q.document_id AND rd.run_id = %(run)s
      LEFT JOIN requirement_type_tag tt ON tt.requirement_id = q.requirement_id AND tt.is_primary
     WHERE q.req_kind = 'REQUIREMENT'"""


def _words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text or "")][:8]


def _like(words: list[str], column: str, joiner: str) -> tuple[str, dict]:
    parts, params = [], {}
    for i, w in enumerate(words):
        params[f"w{i}"] = f"%{w}%"
        parts.append(f"{column} ILIKE %(w{i})s")
    return (f" AND ({joiner.join(parts)})" if parts else ""), params


def _fetch(conn: psycopg.Connection, sql: str, params: dict) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _requirement_items(conn: psycopg.Connection, run_id: int, rows: list[dict]) -> list[dict]:
    locs = _locations(conn, [r["requirement_id"] for r in rows], run_id)
    return [{"ref": f"R{r['requirement_id']}", "kind": "REQUIREMENT",
             "requirement_id": r["requirement_id"], "judgment_id": None,
             "text_raw": r["text_raw"], "type_code": r["type_code"], "result": None,
             "item_name": None, "req_value_raw": None, "product_value_raw": None,
             "locations": locs.get(r["requirement_id"], [])}
            for r in rows if locs.get(r["requirement_id"])]       # 위치 없으면 내지 않음


def search_requirements(conn: psycopg.Connection, run_id: int, words: str,
                        type_code: str | None = None, any_word: bool = False) -> list[dict]:
    """도구 1: 이 검토 요구사항 원문에서 낱말이 모두(any_word면 하나라도) 들어간 줄."""
    found = _words(words)
    where, params = _like(found, "q.text_raw", " OR " if any_word else " AND ")
    if not found and not type_code:
        return []
    if type_code and type_code not in TYPE_CODES:
        type_code = None
    rows = _fetch(conn, _REQ + where + """
          AND (%(type)s::text IS NULL OR EXISTS (SELECT 1 FROM requirement_type_tag t
               WHERE t.requirement_id = q.requirement_id AND t.type_code = %(type)s))
          AND EXISTS (SELECT 1 FROM requirement_location rl
                      WHERE rl.requirement_id = q.requirement_id)
     ORDER BY q.requirement_id LIMIT %(limit)s""",
        {"run": run_id, "type": type_code, "limit": LIMIT} | params)
    return _requirement_items(conn, run_id, rows)


def find_judgments(conn: psycopg.Connection, run_id: int, result: str | None = None,
                   words: str = "") -> list[dict]:
    """도구 2: 이 검토의 지금 판정. 판정 값, 항목 이름·원문 글자로 거른다. 일탈·질의 먼저."""
    if result not in JUDGMENT_RESULTS:
        result = None
    found = _words(words)
    where, params = _like(found, "(coalesce(k.name_ko, '') || ' ' || coalesce(tr.item_name_raw, "
                                 "'') || ' ' || q.text_raw)", " AND ")
    rows = _fetch(conn, """
        SELECT j.judgment_id, j.requirement_id, j.result, q.text_raw, tt.type_code,
               coalesce(k.name_ko, tr.item_name_raw) AS item_name, v.raw_text AS req_value_raw,
               j.product_value_raw
          FROM judgment j
          JOIN req_value v ON v.value_id = j.value_id
          JOIN requirement q ON q.requirement_id = j.requirement_id
          LEFT JOIN table_row tr ON tr.row_id = q.row_id
          LEFT JOIN item_key k ON k.item_key = v.item_key
          LEFT JOIN requirement_type_tag tt ON tt.requirement_id = j.requirement_id
                                           AND tt.is_primary
         WHERE j.run_id = %(run)s AND j.is_current
           AND (%(result)s::text IS NULL OR j.result = %(result)s)""" + where + """
         ORDER BY CASE j.result WHEN 'DEVIATION_CANDIDATE' THEN 1 WHEN 'QUERY_CANDIDATE' THEN 2
                  WHEN 'NEEDS_REVIEW' THEN 3 WHEN 'WARRANTY_TO_FILL' THEN 4 ELSE 5 END,
                  j.judgment_id
         LIMIT %(limit)s""", {"run": run_id, "result": result, "limit": LIMIT} | params)
    locs = _locations(conn, [r["requirement_id"] for r in rows], run_id)
    return [{"ref": f"J{r['judgment_id']}", "kind": "JUDGMENT",
             "requirement_id": r["requirement_id"], "judgment_id": r["judgment_id"],
             "text_raw": r["text_raw"], "type_code": r["type_code"], "result": r["result"],
             "item_name": r["item_name"], "req_value_raw": r["req_value_raw"],
             "product_value_raw": r["product_value_raw"],
             "locations": locs.get(r["requirement_id"], [])}
            for r in rows if locs.get(r["requirement_id"])]


def get_requirement(conn: psycopg.Connection, run_id: int, ref: str) -> list[dict]:
    """도구 3: 근거 번호 하나(R12)의 원문. 이 검토 문서의 줄만."""
    m = re.fullmatch(r"R?(\d+)", (ref or "").strip(), re.IGNORECASE)
    if not m:
        return []
    rows = _fetch(conn, _REQ + " AND q.requirement_id = %(id)s",
                  {"run": run_id, "id": int(m.group(1))})
    return _requirement_items(conn, run_id, rows)


def _evidence_text(e: dict) -> str:
    """근거 원문: 요구사항 원문, 판정은 항목 이름·요구값·제품값까지."""
    return " ".join(str(x) for x in (e["text_raw"], e["item_name"], e["req_value_raw"],
                                     e["product_value_raw"]) if x)


def _observation(e: dict) -> str:
    head = f"[{e['ref']}]"
    if e["kind"] == "JUDGMENT":
        head += (f" 판정 {e['result']} · 항목 {e['item_name'] or '—'} · 요구값 "
                 f"{e['req_value_raw'] or '—'} · 제품값 {e['product_value_raw'] or '—'} ·")
    elif e["type_code"]:
        head += f" 유형 {e['type_code']} ·"
    return f"{head} {one_line(e['text_raw'])[:400]}"


def verify(sentences: list[dict], seen: dict[str, dict]) -> tuple[list[dict], int]:
    """답 문장 검증: 근거 번호가 본 줄이고, 숫자가 근거 원문에 있어야 한다. 어긋나면 뺀다."""
    kept, dropped = [], 0
    for s in sentences:
        text = (s.get("text") or "").strip()
        ids = [i.strip().upper() for i in s.get("evidence_ids") or []]
        if not text:
            continue
        if not ids or any(i not in seen for i in ids):
            dropped += 1                    # 주지 않은 근거를 댔거나 근거가 없다
            continue
        allowed = {n.replace(",", "") for e in (seen[i] for i in ids)
                   for n in NUMBER.findall(_evidence_text(e))}
        if any(n.replace(",", "") not in allowed for n in NUMBER.findall(text)):
            dropped += 1                    # 근거에 없는 숫자
            continue
        kept.append({"text": text, "evidence_ids": list(dict.fromkeys(ids))})
    return kept, dropped


def _search_only(conn: psycopg.Connection, run_id: int, question: str, reason: str) -> dict:
    """AI 답 없이 질문 낱말로 찾는다. note에는 AI 답이 없는 까닭만 담는다."""
    items = search_requirements(conn, run_id, question) or \
        search_requirements(conn, run_id, question, any_word=True)
    return {"mode": "SEARCH", "sentences": [], "evidence": items, "dropped": 0,
            "steps": [{"tool": "search_requirements", "words": " ".join(_words(question)),
                       "type_code": None, "result": None, "ref": None, "found": len(items)}],
            "note": reason}


def ask(conn: psycopg.Connection, run_id: int, question: str, llm: LLM | None) -> dict:
    """질문 하나에 답한다. 저장하지 않는다."""
    question = " ".join((question or "").split())
    if not 2 <= len(question) <= 500:
        raise ReviewError(400, "질문은 2자 이상 500자 이하로 넣어 주세요.")
    stage = conn.execute("SELECT stage FROM review_run WHERE run_id = %s", (run_id,)).fetchone()
    if stage is None:
        raise ReviewError(404, f"검토 {run_id}이(가) 없습니다.")
    if stage[0] in CLOSED_STAGES:
        raise ReviewError(409, "분석이 끝난 검토에만 물을 수 있습니다.")
    if llm is None:
        return _search_only(conn, run_id, question, NO_AI)

    seen: dict[str, dict] = {}
    order: list[str] = []
    steps: list[dict] = []
    try:
        for n in range(MAX_SEARCHES + 1):
            obs = "\n".join(_observation(seen[r]) for r in order)
            for s in steps:
                if s["found"] == 0:
                    obs += f"\n({s['tool']} {s['words'] or s['result'] or s['ref']}: 0줄)"
            step = assistant_step(llm, question, obs.strip(), n < MAX_SEARCHES)
            action = step["action"]
            if action == "answer":
                break
            words, kind = step.get("words") or "", step.get("type_code") or None
            result, ref = step.get("result") or None, step.get("ref") or None
            if action == "search_requirements":
                items = search_requirements(conn, run_id, words, kind)
            elif action == "find_judgments":
                items = find_judgments(conn, run_id, result, words)
            else:
                items = get_requirement(conn, run_id, ref or "")
            steps.append({"tool": action, "words": " ".join(_words(words)) or None,
                          "type_code": kind if action == "search_requirements" else None,
                          "result": result if action == "find_judgments" else None,
                          "ref": ref if action == "get_requirement" else None,
                          "found": len(items)})
            for e in items:
                if e["ref"] not in seen:
                    seen[e["ref"]] = e
                    order.append(e["ref"])
        else:
            step = {"sentences": []}
    except LLMConfigError:              # 키·권한·모델 이름 오류: 다시 물어도 같다
        return _search_only(conn, run_id, question, AI_CONFIG)
    except LLMFailure:                  # 연결·시간 초과(재시도 끝)·형식 오류
        return _search_only(conn, run_id, question, AI_FAILED)

    sentences, dropped = verify(step.get("sentences") or [], seen)
    cited = list(dict.fromkeys(i for s in sentences for i in s["evidence_ids"]))
    return {"mode": "AI", "sentences": sentences, "evidence": [seen[i] for i in cited],
            "dropped": dropped, "steps": steps, "note": None if sentences else NOT_FOUND}
