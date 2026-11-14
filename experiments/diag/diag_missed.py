"""요구사항 정답지에서 시스템이 놓친 줄을 나눠 본다 (읽기만 함, DB를 바꾸지 않음).

실행 (저장소 맨 위 폴더, cmd):
    docker compose exec -T backend python - 30 공급사답안_RFP18 < experiments\\diag\\diag_missed.py
결과: data/private/diag/missed_run<번호>.csv (원문이 들어 있어 git에 올리지 않는 폴더)
"""

import csv
import sys
from collections import Counter
from pathlib import Path

from rfp_agent.db.connection import connect
from rfp_agent.pipeline.req_eval import normalize, same_line, scope_documents

run_id = int(sys.argv[1]) if len(sys.argv) > 1 else 30
key_name = sys.argv[2] if len(sys.argv) > 2 else "공급사답안_RFP18"
out_dir = Path("/app/data/private/diag")
out_dir.mkdir(parents=True, exist_ok=True)

with connect() as conn:
    row = conn.execute("SELECT key_id, doc_name FROM answer_key WHERE key_name = %s",
                       (key_name,)).fetchone()
    if not row:
        sys.exit(f"정답지가 없습니다: {key_name}")
    key_id, doc_name = row
    docs = scope_documents(conn, [run_id], doc_name)
    answers = conn.execute("SELECT row_no, text_raw, note FROM answer_key_row WHERE key_id = %s "
                           "AND expected = 'REQUIREMENT' ORDER BY row_no", (key_id,)).fetchall()
    reqs = conn.execute(
        """SELECT requirement_id, text_raw, req_kind, source_kind, extracted_by
             FROM requirement WHERE document_id = ANY(%s) ORDER BY requirement_id""",
        (docs,)).fetchall()
    rows = conn.execute(
        """SELECT tr.row_id, concat_ws(' / ', tr.item_no, tr.item_name_raw, tr.required_raw,
                                      tr.warranted_raw), tr.supplier_mark
             FROM table_row tr JOIN doc_table t USING (table_id)
            WHERE t.document_id = ANY(%s)""", (docs,)).fetchall()

norm_reqs = [(rid, normalize(t), kind, src, by) for rid, t, kind, src, by in reqs]
norm_rows = [(rid, normalize(t), mark) for rid, t, mark in rows]
result, counts = [], Counter()
for no, text, note in answers:
    key = normalize(text)
    marked = "표시 있음" if note else "표시 없음"
    hits = [r for r in norm_reqs if same_line(key, r[1])]
    req_hits = [r for r in hits if r[2] == "REQUIREMENT"]
    if req_hits:
        status, detail = "찾음", f"{req_hits[0][3]}/{req_hits[0][4]}"
    elif hits:
        status, detail = "다른 종류로 뽑힘", f"{hits[0][2]}/{hits[0][3]}/{hits[0][4]}"
    else:
        row_hits = [r for r in norm_rows if r[1] and same_line(key, r[1])]
        if row_hits:
            status = "표 줄은 있으나 요구사항 아님"
            detail = f"row {row_hits[0][0]}, 표시={row_hits[0][2] or '없음'}"
        else:
            status, detail = "추출 안 됨", ""
    counts[(status, marked)] += 1
    result.append([no, status, marked, note or "", detail, " ".join(text.split())[:300]])

out = out_dir / f"missed_run{run_id}.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["번호", "상태", "공급사 표시", "메모", "자세히", "정답 원문(앞 300자)"])
    w.writerows(result)

print(f"검토 run {run_id}, 정답지 {key_name}: 정답 {len(answers)}줄, 시스템 줄 {len(reqs)}개, "
      f"표 줄 {len(rows)}개 (표시 있는 표 줄 {sum(1 for r in rows if r[2])}개)")
for (status, marked), n in sorted(counts.items()):
    print(f"  {status:<22} {marked}: {n}")
print(f"저장: {out} (내 컴퓨터: data\\private\\diag\\{out.name})")
