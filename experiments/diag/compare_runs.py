"""같은 문서를 다른 모델로 돌린 두 검토를 비교한다 (읽기만 함, DB를 바꾸지 않음).

실행 (저장소 맨 위 폴더, cmd):
    docker compose exec -T backend /app/backend/.venv/bin/python - 33 34 < experiments\\diag\\compare_runs.py
결과: 화면 요약 + data/private/diag/diff_run33_run34.csv (두 모델 판단이 갈린 요구사항 줄)
"""

import csv
import sys
from collections import Counter
from pathlib import Path

from rfp_agent.db.connection import connect
from rfp_agent.pipeline.req_eval import normalize

A, B = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (33, 34)
OUT = Path("/app/data/private/diag")
OUT.mkdir(parents=True, exist_ok=True)
# 100만 토큰당 달러 (입력, 출력·생각). 3.8 Flash는 시스템 실행 기록과 같은 팀 가정 값
PRICES = {"gemini-3.8-flash": (0.50, 4.00), "gemini-3.5-flash-lite": (0.30, 2.50),
          "gemini-3.1-flash-lite": (0.25, 1.50)}
KRW = 1500


def q(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as exc:  # noqa: BLE001 - 칸이 없는 예전 DB면 그 항목만 건너뜀
        conn.rollback()
        return [("오류", str(exc).splitlines()[0])]


def line(label, a, b):
    print(f"  {label:<34} {str(a):>18} {str(b):>18}")


with connect() as conn:
    runs = {}
    for r in (A, B):
        row = conn.execute(
            """SELECT llm_model, stage, round(extract(epoch FROM finished_at - started_at)/60, 1),
                      llm_calls, llm_retries, llm_input_tokens, llm_output_tokens,
                      llm_thinking_tokens
                 FROM review_run WHERE run_id = %s""", (r,)).fetchone()
        if not row:
            sys.exit(f"검토 run {r}이 없습니다.")
        docs = [d for (d,) in conn.execute(
            "SELECT document_id FROM run_document WHERE run_id = %s", (r,))]
        runs[r] = {"info": row, "docs": docs}

    print(f"\n== 실행 (run {A} vs run {B})")
    line("", f"run {A}", f"run {B}")
    labels = ["모델", "단계", "걸린 시간(분)", "AI 호출", "재시도", "입력 토큰", "출력 토큰", "생각 토큰"]
    for i, lab in enumerate(labels):
        line(lab, runs[A]["info"][i], runs[B]["info"][i])
    costs = []
    for r in (A, B):
        m, *_, it, ot, tt = runs[r]["info"]
        p = PRICES.get(m)
        costs.append(f"{round((it * p[0] + (ot + tt) * p[1]) / 1e6 * KRW)}원" if p else "단가 모름")
    line("추정 비용 (팀 가정 단가)", *costs)

    # ---------- 요구사항 ----------
    reqs = {}
    for r in (A, B):
        rows = conn.execute(
            """SELECT q.text_raw, q.req_kind, q.source_kind, q.extracted_by, s.title,
                      (SELECT t.type_code FROM requirement_type_tag t
                        WHERE t.requirement_id = q.requirement_id AND t.is_primary)
                 FROM requirement q LEFT JOIN section s USING (section_id)
                WHERE q.document_id = ANY(%s)""", (runs[r]["docs"],)).fetchall()
        reqs[r] = rows
    print("\n== 요구사항")
    line("", f"run {A}", f"run {B}")
    for src in ("TABLE_CELL", "SUPPLIER_ANSWER", "SENTENCE"):
        line(f"요구사항 ({src})", *(sum(1 for t, k, s, *_ in reqs[r] if k == "REQUIREMENT" and s == src)
                                   for r in (A, B)))
    line("요구사항 합계", *(sum(1 for t, k, *_ in reqs[r] if k == "REQUIREMENT") for r in (A, B)))
    line("AI가 작성 규칙 등으로 바꾼 줄", *(sum(1 for t, k, s, by, *_ in reqs[r]
                                          if by == "AI" and k != "REQUIREMENT") for r in (A, B)))

    def sentence_map(r):
        out = {}
        for t, k, s, by, title, typ in reqs[r]:
            if s == "SENTENCE":
                out.setdefault(normalize(t), (k, by, title, " ".join(t.split())))
        return out

    sa, sb = sentence_map(A), sentence_map(B)
    req_a = {k for k, v in sa.items() if v[0] == "REQUIREMENT"}
    req_b = {k for k, v in sb.items() if v[0] == "REQUIREMENT"}
    only_a, only_b, both = req_a - req_b, req_b - req_a, req_a & req_b
    union = req_a | req_b
    print(f"\n  문장 요구사항: 둘 다 {len(both)}줄 / run {A}만 {len(only_a)}줄 / run {B}만 {len(only_b)}줄"
          f" → 일치율 {len(both) / len(union):.1%}" if union else "\n  문장 요구사항 없음")
    with (OUT / f"diff_run{A}_run{B}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["요구사항으로 본 쪽", f"run {A} 판단", f"run {B} 판단", "절 제목", "원문(앞 300자)",
                    "진짜 요구사항인가(Y/N, 사람이 채움)"])
        for key in sorted(only_a | only_b):
            va, vb = sa.get(key), sb.get(key)
            w.writerow([f"run {A}만" if key in only_a else f"run {B}만",
                        va[0] if va else "후보 아님", vb[0] if vb else "후보 아님",
                        (va or vb)[2] or "", (va or vb)[3][:300], ""])

    # 같은 줄의 주 유형이 같은가 (두 쪽 모두 요구사항인 줄)
    def type_map(r):
        return {normalize(t): typ for t, k, s, by, title, typ in reqs[r] if k == "REQUIREMENT"}
    ta, tb = type_map(A), type_map(B)
    shared = [k for k in ta if k in tb]
    same_type = sum(ta[k] == tb[k] for k in shared)
    print(f"  유형: 두 쪽 모두 요구사항인 {len(shared)}줄 중 주 유형이 같은 줄 {same_type}"
          f" ({same_type / len(shared):.1%})" if shared else "  유형 비교할 줄 없음")

    # ---------- 판정 ----------
    print("\n== 판정 (코드가 하므로 같아야 정상)")
    line("", f"run {A}", f"run {B}")
    jc = {r: Counter(dict(q(conn, "SELECT result, count(*) FROM judgment WHERE run_id = %s "
                                  "AND is_current GROUP BY result", (r,)))) for r in (A, B)}
    for res in sorted(set(jc[A]) | set(jc[B])):
        line(res, jc[A].get(res, 0), jc[B].get(res, 0))

    # ---------- 위험 설명 ----------
    print("\n== 위험 설명 (AI 설명 + 근거 대조)")
    line("", f"run {A}", f"run {B}")
    for lab, sql in [
        ("위험 후보", "SELECT count(*) FROM risk_flag WHERE run_id = %s"),
        ("설명이 붙은 후보", "SELECT count(*) FROM risk_flag WHERE run_id = %s AND explanation_ai IS NOT NULL"),
        ("근거 대조로 버려진 설명", "SELECT count(*) FROM risk_flag WHERE run_id = %s "
                                    "AND explanation_drop_reason IS NOT NULL"),
    ]:
        line(lab, *(q(conn, sql, (r,))[0][0] for r in (A, B)))
    reasons = {r: dict(q(conn, "SELECT explanation_drop_reason, count(*) FROM risk_flag WHERE run_id = %s "
                               "AND explanation_drop_reason IS NOT NULL GROUP BY 1", (r,))) for r in (A, B)}
    for rs in sorted(set(reasons[A]) | set(reasons[B])):
        line(f"  버린 이유: {rs}", reasons[A].get(rs, 0), reasons[B].get(rs, 0))
    print("\n== 검증 에이전트 (설명 문장마다)")
    line("", f"run {A}", f"run {B}")
    vs = {r: dict(q(conn, "SELECT status, count(*) FROM claim_evidence WHERE run_id = %s "
                          "AND target_table = 'risk_flag' GROUP BY status", (r,))) for r in (A, B)}
    for st in sorted(set(vs[A]) | set(vs[B])):
        line(st, vs[A].get(st, 0), vs[B].get(st, 0))

    # ---------- 문장 초안 ----------
    print("\n== 문장 초안 (AI = AI 문장 통과 / CODE = 검사에 걸려 기본 문장 또는 AI 안 씀)")
    line("", f"run {A}", f"run {B}")
    for table, lab in (("output_item", "일탈·질의 초안"), ("proposal_point", "제안 포인트")):
        d = {r: dict(q(conn, f"SELECT drafted_by, count(*) FROM {table} WHERE run_id = %s GROUP BY 1",
                       (r,))) for r in (A, B)}
        for by in sorted(set(d[A]) | set(d[B])):
            line(f"{lab} {by}", d[A].get(by, 0), d[B].get(by, 0))

print(f"\n저장: {OUT}/diff_run{A}_run{B}.csv (내 컴퓨터: data\\private\\diag\\diff_run{A}_run{B}.csv)")
