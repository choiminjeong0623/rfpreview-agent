"""정답지·채점 (change add-evaluation, 명세 evaluation, SCR-19).

사람이 확정·수정한 판정과 유형 정답지로 지표(기획서 2-2)를 코드로만 잰다(CR-01).
같은 검토·같은 정답지면 같은 점수(CR-11). AI는 쓰지 않는다.
"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from rfp_agent.llm.tasks import TYPE_CODES
from rfp_agent.pipeline import code_version, req_eval
from rfp_agent.pipeline.review import ReviewError, _user_role, default_user

# 정답지 CSV 열: Claude 초안 열 이름과 영어 열 이름을 모두 받는다
COLUMNS = {
    "row_no": ("번호", "row_no"),
    "text": ("text",),
    "context": ("context",),
    "draft": ("Claude초안", "expected"),
    "ambiguous": ("애매함(Y)", "ambiguous"),
    "note": ("이유", "note"),
    "human": ("사람 확인(맞으면 비움, 다르면 코드)", "human"),
}
# 기획서 2-2 목표(가안). better: 높을수록(up) / 낮을수록(down) 좋음
TARGETS = {"K1": 85.0, "K2": 80.0, "K3": 90.0, "K10": 80.0, "K4": 100.0, "K5": 80.0,
           "K6": 80.0, "K11": 0, "K12": 0, "K13": 70.0, "TIME": 15.0}
# 요구사항 정답지(add-requirement-answer-key)를 고르면 재는 지표. 고르지 않으면 "재지 않음"
REQ_METRICS = [("K1", "요구사항 추출 재현율"), ("K2", "요구사항 추출 정확도"),
               ("K3", "값·단위 정확도"), ("K10", "위험 조건 탐지 재현율")]
NOT_MEASURED = [("K8", "손실 환산 계산 일치"), ("K9", "숫자 불일치 경고 누락")]
VISIBLE = ("ENGINEER_REVIEW", "APPROVAL", "APPROVED", "REJECTED")


@dataclass
class LoadReport:
    key_id: int
    rows: int
    human_checked: int
    skipped: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    """글자 맞추기: 공백 하나, 앞뒤 공백 없음, 소문자."""
    return " ".join((text or "").split()).lower()


def _cell(row: dict, name: str) -> str:
    for col in COLUMNS[name]:
        if col in row and row[col] is not None:
            return row[col].strip()
    return ""


def load_key(conn: psycopg.Connection, path: Path, name: str, human: bool = False) -> LoadReport:
    """유형 정답지 CSV를 넣는다. 같은 이름이면 줄을 바꾼다. 유형 코드가 아닌 줄은 건너뛴다."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    made_by = "HUMAN" if human else "CLAUDE_DRAFT"
    key_id = conn.execute(
        """INSERT INTO answer_key (key_name, made_by) VALUES (%s, %s)
           ON CONFLICT (key_name) DO UPDATE SET made_by = EXCLUDED.made_by, created_at = now()
           RETURNING key_id""", (name, made_by)).fetchone()[0]
    conn.execute("DELETE FROM answer_key_row WHERE key_id = %s", (key_id,))
    report = LoadReport(key_id, 0, 0)
    for i, row in enumerate(rows, start=1):
        no = _cell(row, "row_no") or str(i)
        text, human_code = _cell(row, "text"), _cell(row, "human").upper()
        expected = human_code or _cell(row, "draft").upper()
        if not text:
            report.skipped.append(f"{no}번: 원문이 비었습니다")
            continue
        if expected not in TYPE_CODES:
            report.skipped.append(f"{no}번: 유형 코드가 아닙니다 ({expected or '빈칸'})")
            continue
        conn.execute(
            """INSERT INTO answer_key_row (key_id, row_no, text_raw, context, expected, ambiguous,
                                           human_checked, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (key_id, int(no) if no.isdigit() else i, text, _cell(row, "context") or None, expected,
             _cell(row, "ambiguous").upper() == "Y", bool(human_code or human),
             _cell(row, "note") or None))
        report.rows += 1
        report.human_checked += bool(human_code or human)
    conn.commit()
    return report


def keys(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT k.key_id, k.key_name, k.key_kind, k.made_by, k.doc_name, k.created_at,
                      count(r.row_no)::int AS rows,
                      count(*) FILTER (WHERE r.human_checked)::int AS human_checked,
                      count(*) FILTER (WHERE r.ambiguous)::int AS ambiguous
                 FROM answer_key k LEFT JOIN answer_key_row r USING (key_id)
                GROUP BY k.key_id ORDER BY k.key_id""").fetchall()


def candidate_runs(conn: psycopg.Connection) -> list[dict]:
    """채점에 넣을 수 있는 검토: 분석을 마친 검토. reviewed = 사람이 확정·수정한 판정 줄 수.

    판정 줄이 없는 검토(묶음 C 문서만)도 요구사항 정답지 채점에 쓴다(add-requirement-answer-key).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT r.run_id, r.review_name, r.stage,
                      'RV-' || extract(year FROM r.started_at)::int || '-'
                          || lpad(r.run_id::text, 3, '0') AS review_no,
                      count(j.judgment_id)::int AS reviewed,
                      (SELECT u.user_name FROM review_log l
                         JOIN app_user u ON u.user_id = l.actor_id
                        WHERE l.run_id = r.run_id AND l.target_table = 'judgment'
                          AND l.action IN ('CONFIRM', 'EDIT')
                        ORDER BY l.acted_at DESC, l.log_id DESC LIMIT 1) AS reviewer,
                      (SELECT max(l.acted_at) FROM review_log l
                        WHERE l.run_id = r.run_id AND l.target_table = 'judgment'
                          AND l.action IN ('CONFIRM', 'EDIT')) AS last_reviewed_at
                 FROM review_run r LEFT JOIN judgment j ON j.run_id = r.run_id AND j.is_current
                      AND j.review_status IN ('CONFIRMED', 'EDITED')
                WHERE r.stage = ANY(%s)
                GROUP BY r.run_id ORDER BY r.run_id DESC""", (list(VISIBLE),)).fetchall()


def _pct(num: int, den: int) -> float | None:
    return round(num / den * 100, 1) if den else None


def _metric(code: str, name: str, measure: str, unit: str, value, num=None, den=None,
            better: str = "up", note: str | None = None) -> dict:
    target = TARGETS.get(code)
    if value is None or target is None:
        passed = None
    else:
        passed = value >= target if better == "up" else value <= target
    return {"code": code, "name": name, "measure": measure, "unit": unit, "value": value,
            "num": num, "den": den, "target": target, "better": better, "passed": passed,
            "note": note}


def _judgment_scores(conn: psycopg.Connection, run_ids: list[int]) -> tuple[dict, dict]:
    """K5: 사람이 본 판정 중 시스템 판정이 같은 비율. K6: 사람이 일탈로 정한 줄 중 시스템도 일탈."""
    rows = conn.execute(
        """SELECT j.result, j.review_status,
                  (SELECT l.before_value->>'result' FROM review_log l
                    WHERE l.target_table = 'judgment' AND l.target_id = j.judgment_id
                      AND l.action = 'EDIT' ORDER BY l.log_id LIMIT 1) AS system_result
             FROM judgment j
            WHERE j.run_id = ANY(%s) AND j.is_current
              AND j.review_status IN ('CONFIRMED', 'EDITED')
            ORDER BY j.judgment_id""", (run_ids,)).fetchall()
    pairs, unknown = [], 0
    for human, status, edited_from in rows:
        system = human if status == "CONFIRMED" else edited_from
        if system is None:
            unknown += 1                # 이력이 없는 수정(문서 추가로 이어받음) → 모름
            continue
        pairs.append((system, human))
    same = sum(s == h for s, h in pairs)
    dev = [(s, h) for s, h in pairs if h == "DEVIATION_CANDIDATE"]
    found = sum(s == "DEVIATION_CANDIDATE" for s, _ in dev)
    note = f"수정 이력 없는 줄 {unknown}개 뺌" if unknown else None
    k5 = _metric("K5", "적합성 판정 정확도", "사람이 확정·수정한 판정 중 시스템 판정이 같은 비율",
                 "%", _pct(same, len(pairs)), same, len(pairs), note=note)
    k6 = _metric("K6", "일탈 목록 재현율", "사람이 일탈로 정한 줄 중 시스템도 일탈 후보로 낸 비율",
                 "%", _pct(found, len(dev)), found, len(dev), note=note)
    return k5, k6


def _type_score(conn: psycopg.Connection, run_ids: list[int], key_id: int) -> tuple[dict, dict]:
    """K13: 정답지 줄과 글자가 같은 요구사항의 주 유형이 정답과 같은 비율."""
    reqs = conn.execute(
        """SELECT q.requirement_id, q.text_raw,
                  (SELECT t.type_code FROM requirement_type_tag t
                    WHERE t.requirement_id = q.requirement_id AND t.is_primary) AS primary_type
             FROM requirement q
            WHERE q.req_kind = 'REQUIREMENT' AND q.document_id IN
                  (SELECT document_id FROM run_document WHERE run_id = ANY(%s))
            ORDER BY q.requirement_id""", (run_ids,)).fetchall()
    by_text: dict[str, str] = {}
    for _, text, primary in reqs:
        by_text.setdefault(normalize(text), primary or "NONE")   # 번호가 가장 작은 줄 (CR-11)
    answers = conn.execute(
        "SELECT expected, ambiguous, text_raw FROM answer_key_row WHERE key_id = %s "
        "ORDER BY row_no", (key_id,)).fetchall()
    hit = miss = not_found = amb_hit = amb_total = 0
    for expected, ambiguous, text in answers:
        got = by_text.get(normalize(text))
        if got is None:
            not_found += 1
            continue
        if ambiguous:
            amb_total += 1
            amb_hit += got == expected
            continue
        if got == expected:
            hit += 1
        else:
            miss += 1
    detail = {"rows": len(answers), "matched": hit + miss, "hit": hit, "miss": miss,
              "not_found": not_found, "ambiguous": amb_total, "ambiguous_hit": amb_hit}
    notes = [f"못 찾은 줄 {not_found}개"] if not_found else []
    if amb_total:
        notes.append(f"애매한 줄 {amb_hit}/{amb_total} 따로")
    k13 = _metric("K13", "유형 분류 정확도", "정답지 줄 중 시스템의 주 유형이 정답과 같은 비율",
                  "%", _pct(hit, hit + miss), hit, hit + miss, note=" · ".join(notes) or None)
    return k13, detail


def metrics(conn: psycopg.Connection, run_ids: list[int], key_id: int | None,
            req_key_id: int | None = None) -> dict:
    """지표를 잰다. 결과는 같은 입력이면 같다."""
    k4_num, k4_den = conn.execute(
        """SELECT count(*) FILTER (WHERE EXISTS (SELECT 1 FROM requirement_location rl
                                                 WHERE rl.requirement_id = j.requirement_id)),
                  count(*)
             FROM judgment j
            WHERE j.run_id = ANY(%s) AND j.is_current AND j.review_status <> 'REJECTED'""",
        (run_ids,)).fetchone()
    k11 = conn.execute(
        """SELECT count(*) FROM warranty_candidate w JOIN judgment j USING (judgment_id)
            WHERE w.run_id = ANY(%s) AND j.is_current AND w.candidate_value IS NOT NULL
              AND w.status = 'CANDIDATE'
              AND NOT (w.source_kind = 'PM' AND w.product_code IS NOT NULL
                       AND w.pm_column IS NOT NULL)
              AND NOT (w.source_kind = 'FIXED' AND w.fixed_key IS NOT NULL)""",
        (run_ids,)).fetchone()[0]
    k12 = conn.execute(
        """SELECT count(*) FROM proposal_point p
            WHERE p.run_id = ANY(%s) AND p.status <> 'DISCARDED'
              AND NOT EXISTS (SELECT 1 FROM requirement_location rl
                              WHERE rl.requirement_id = p.requirement_id)""",
        (run_ids,)).fetchone()[0]
    minutes = conn.execute(
        """SELECT avg(extract(epoch FROM finished_at - started_at)) / 60 FROM review_run
            WHERE run_id = ANY(%s) AND finished_at IS NOT NULL""", (run_ids,)).fetchone()[0]
    k5, k6 = _judgment_scores(conn, run_ids)
    items = [
        _metric("K4", "원문 위치 정확도", "판정 줄 중 원문 위치가 붙은 비율", "%",
                _pct(k4_num, k4_den), k4_num, k4_den),
        k5, k6,
        _metric("K11", "보증값 지어냄", "제품표·회사 고정값에 없는 보증값 후보 수", "건", k11,
                better="down"),
        _metric("K12", "근거 없는 제안 포인트", "요구 원문 위치가 없는 제안 포인트 수", "건", k12,
                better="down"),
    ]
    types = None
    if key_id is not None:
        k13, types = _type_score(conn, run_ids, key_id)
        items.append(k13)
    requirements = None
    if req_key_id is not None:
        req_items, requirements = req_eval.scores(conn, run_ids, req_key_id, _metric)
        items = req_items + items
    items.append(_metric("TIME", "처리 시간", "검토 한 건 분석에 걸린 평균 시간", "분",
                         None if minutes is None else round(float(minutes), 1), better="down"))
    missing = (REQ_METRICS if req_key_id is None else []) + NOT_MEASURED
    return {"items": items, "types": types, "requirements": requirements,
            "not_measured": [{"code": c, "name": n, "note": "요구사항 정답지가 있어야 잽니다"
                              if (c, n) in REQ_METRICS else "아직 재는 방법이 없습니다"}
                             for c, n in missing]}


def _check_key(conn: psycopg.Connection, key_id: int | None, kind: str, label: str) -> None:
    if key_id is None:
        return
    row = conn.execute("SELECT key_kind FROM answer_key WHERE key_id = %s", (key_id,)).fetchone()
    if row is None:
        raise ReviewError(404, f"정답지 {key_id}이(가) 없습니다.")
    if row[0] != kind:
        raise ReviewError(400, f"정답지 {key_id}은(는) {label}가 아닙니다.")


def score(conn: psycopg.Connection, run_ids: list[int], key_id: int | None = None,
          note: str | None = None, actor_id: int | None = None,
          req_key_id: int | None = None) -> dict:
    """채점하고 기록한다."""
    ids = sorted(set(run_ids))
    if not ids:
        raise ReviewError(400, "채점할 검토를 하나 이상 고르세요.")
    found = {r[0] for r in conn.execute(
        "SELECT run_id FROM review_run WHERE run_id = ANY(%s) AND stage = ANY(%s)",
        (ids, list(VISIBLE)))}
    if missing := [i for i in ids if i not in found]:
        raise ReviewError(404, f"채점할 수 없는 검토입니다 ({', '.join(map(str, missing))}).")
    _check_key(conn, key_id, "TYPE", "유형 정답지")
    _check_key(conn, req_key_id, "REQ", "요구사항 정답지")
    actor_id = actor_id or default_user(conn, "ENGINEER")
    _user_role(conn, actor_id)
    result = metrics(conn, ids, key_id, req_key_id)
    score_id = conn.execute(
        """INSERT INTO eval_score (run_ids, key_id, req_key_id, metrics, note, code_version,
                                   scored_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING score_id""",
        (ids, key_id, req_key_id, json.dumps(result, ensure_ascii=False),
         (note or "").strip() or None, code_version(), actor_id)).fetchone()[0]
    conn.commit()
    return history(conn, score_id)[0]


def history(conn: psycopg.Connection, score_id: int | None = None) -> list[dict]:
    """채점 기록, 최근 것부터."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT s.score_id, s.run_ids, s.key_id, k.key_name, k.made_by AS key_made_by,
                      s.req_key_id, rk.key_name AS req_key_name, rk.made_by AS req_key_made_by,
                      s.metrics, s.note, s.code_version, s.scored_by, u.user_name AS scored_by_name,
                      s.scored_at
                 FROM eval_score s LEFT JOIN answer_key k USING (key_id)
                 LEFT JOIN answer_key rk ON rk.key_id = s.req_key_id
                 LEFT JOIN app_user u ON u.user_id = s.scored_by
                WHERE %(id)s::int IS NULL OR s.score_id = %(id)s
                ORDER BY s.scored_at DESC, s.score_id DESC""", {"id": score_id}).fetchall()
