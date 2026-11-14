"""제품표 엑셀 내보내기 (SCR-16 "내보내기", change add-product-export).

화면 목록과 같은 조건(제품군·검색어·설계 사례 카드)으로 거른 제품을 칸 전체와 함께
엑셀 한 장에 담는다. 빈 칸은 빈 셀 그대로 둔다(CR-04, 값을 채우지 않음).
팀 가정 값이 든 제품은 "팀 가정" 칸에 무엇이 가정인지 적고 그 줄을 옅은 파랑으로 칠한다(CR-06).
내보낸 시각은 넣지 않는다: 같은 제품표면 같은 파일(CR-11).
"""

from io import BytesIO

import psycopg
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from psycopg.rows import dict_row

from rfp_agent.pipeline.reference import _where

# (칸, 머리 이름). 순서는 화면 상세 패널과 같다
COLUMNS = (
    ("product_code", "제품 코드"), ("product_name", "제품 이름"), ("family", "제품군"),
    ("rated_voltage_kv", "정격 전압 (kV)"), ("rated_current_a", "정격 전류 (A)"),
    ("short_circuit_ka", "단시간 견딤 전류 (kA)"), ("rated_frequency", "정격 주파수 (Hz)"),
    ("rated_capacity", "정격 용량"), ("rated_capacity_unit", "정격 용량 단위"),
    ("lightning_impulse_kv", "뇌 임펄스 내전압 (kV)"),
    ("power_freq_withstand_kv", "상용 주파 내전압 (kV)"),
    ("switching_impulse_kv", "개폐 임펄스 내전압 (kV)"),
    ("peak_current_ka", "최대 순간 전류 (kA)"), ("making_current_ka", "투입 전류 (kA)"),
    ("breaking_time_ms", "차단 시간 (ms)"), ("closing_time_ms", "투입 시간 (ms)"),
    ("gas_leakage_percent", "가스 누설률 (%/년)"), ("partial_discharge_pc", "부분 방전 (pC)"),
    ("cooling_type", "냉각 방식"), ("insulation_medium", "절연 매질"),
    ("ip_rating", "보호 등급"), ("operating_temp", "사용 온도"), ("weight_kg", "중량 (kg)"),
    ("maintenance_months", "점검 주기 (개월)"), ("service_life_years", "수명 (년)"),
    ("warranty_months", "보증 기간 (개월)"),
    ("noload_loss_kw", "무부하 손실 (kW)"), ("load_loss_kw", "부하 손실 (kW)"),
    ("aux_loss_kw", "보조 손실 (kW)"), ("standards", "적용 규격"),
)
TAIL = ("팀 가정", "설계 사례 카드", "비교값 출처", "출처 문서", "상태")
ASSUMED_FILL = PatternFill("solid", fgColor="EFF8FF")
HEAD_FILL = PatternFill("solid", fgColor="EEF2F6")


def _assumed(row: dict) -> str:
    """무엇이 팀 가정인지 (CR-06). 없으면 빈 문자열."""
    parts = []
    if row["is_assumed"] == "Y":
        parts.append("제품 전체")
    if row["comparison_values_assumed"] == "Y":
        parts.append("비교값")
    if row["loss_is_assumed"]:
        parts.append("손실값")
    return " · ".join(parts)


def rows(conn: psycopg.Connection, family: str | None = None, q: str | None = None,
         cards: bool = True) -> list[dict]:
    """화면 목록과 같은 거르기, 제품군 → 코드 순서 (CR-11)."""
    where, params = _where(family, q or None, cards)
    cols = ", ".join(f"p.{c}" for c, _ in COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            f"""SELECT {cols}, p.is_assumed, p.comparison_values_assumed, p.loss_is_assumed,
                       p.is_design_card, p.comparison_values_source, p.source_doc,
                       p.lifecycle_status
                FROM product_master p WHERE {where} ORDER BY p.family, p.product_code""",
            params).fetchall()


def products_xlsx(conn: psycopg.Connection, family: str | None = None, q: str | None = None,
                  cards: bool = True) -> tuple[str, bytes, int]:
    """(파일 이름, 엑셀 바이트, 제품 수)."""
    data = rows(conn, family, q, cards)
    wb = Workbook()
    ws = wb.active
    ws.title = "제품표"
    cond = [f"제품군 {family}" if family else "제품군 전체"]
    if q:
        cond.append(f"검색어 \"{q}\"")
    cond.append("설계 사례 카드 포함" if cards else "설계 사례 카드 뺌")
    ws.append([f"제품표 (product_master) — {' · '.join(cond)} · 제품 {len(data)}개"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["빈 칸은 제품표에 값이 없는 칸입니다(확인 필요). "
               "파란 줄은 팀 가정 값이 든 제품이며, \"팀 가정\" 칸에 무엇이 가정인지 적었습니다."])
    ws.append([])
    ws.append([h for _, h in COLUMNS] + list(TAIL))
    head = ws.max_row
    for cell in ws[head]:
        cell.font = Font(bold=True)
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for r in data:
        assumed = _assumed(r)
        ws.append([r[c] for c, _ in COLUMNS] + [
            assumed or None, "예" if r["is_design_card"] else None,
            r["comparison_values_source"], r["source_doc"], r["lifecycle_status"]])
        if assumed:
            for cell in ws[ws.max_row]:
                cell.fill = ASSUMED_FILL
    for i, (c, _) in enumerate(COLUMNS, start=1):
        width = 14 if c == "product_code" else 30 if c in ("product_name", "standards") else 12
        ws.column_dimensions[ws.cell(row=head, column=i).column_letter].width = width
    for i in range(len(COLUMNS) + 1, len(COLUMNS) + len(TAIL) + 1):
        ws.column_dimensions[ws.cell(row=head, column=i).column_letter].width = 22
    ws.row_dimensions[head].height = 32
    ws.freeze_panes = ws.cell(row=head + 1, column=2)
    out = BytesIO()
    wb.save(out)
    return f"제품표_{family or '전체'}.xlsx", out.getvalue(), len(data)
