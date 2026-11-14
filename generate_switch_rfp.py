"""위험 조항 RFP(파일 27)에 24 kV 차단기 데이터시트 표(4.3)를 더한 시연용 RFP(파일 28)를 만든다.

파일 23~27의 판정 표는 170 kV GIS뿐이고 제품표에서 170 kV GIS는 하나라 비교 제품을 바꿀 수 없다.
제품표에서 24 kV·40 kA 진공차단기는 정격 전류만 다른 5개(1250·2000·3150 A)라 코드가 하나로
고르지 못하고(후보 5), 엔지니어가 고르면 정격 전류 2000 A 줄이 1250 A 제품은 일탈 후보,
2000 A 이상은 준수가 된다. 검토 상세 "비교 제품"에서 바꿔 보기를 시연한다
(update-synthetic-product-switch).

실행: cd backend && uv run python ../generate_risk_rfp.py && uv run python ../generate_switch_rfp.py
"""
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent
DOCX_DIR = ROOT / "data" / "private" / "rfp_docx"
src = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Risk_Clauses.docx"
out = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Product_Switch.docx"
doc = Document(str(src))

# 4.2 GIS 표(TS-170-GIS)와 같은 모양: 첫 줄 합친 칸에 표 이름, 둘째 줄 머리
BREAKER_ROWS = [
    ["1", "Rated voltage", "kV", "≥24 kV"],
    ["2", "Rated normal current", "A", "≥2000 A"],
    ["3", "Rated short-circuit breaking current", "kA", "≥40 kA"],
    ["4", "Rated lightning impulse withstand voltage", "kV", "≥125 kV"],
    ["5", "Rated short-duration power-frequency withstand voltage", "kV", "≥50 kV"],
    ["6", "Rated short-circuit making current", "kA", "≥100 kA"],
    ["7", "Total Breaking Time", "ms", "≤60 ms"],
]
gis_table = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "TS-170-GIS")
breaker = doc.add_table(rows=2, cols=4)
breaker.style = gis_table.style
breaker.rows[0].cells[0].merge(breaker.rows[0].cells[3]).text = "TS-24-CB"
for cell, text in zip(breaker.rows[1].cells, ["No.", "Description", "Unit",
                                              "Employer's Requirement"], strict=True):
    cell.text = text
for row in BREAKER_ROWS:
    for cell, text in zip(breaker.add_row().cells, row, strict=True):
        cell.text = text
heading = next(p for p in doc.paragraphs if p.text.startswith("5. Evaluation Methodology"))
heading.insert_paragraph_before("4.3 Numeric Technical Datasheet Requirements — 24 kV Circuit "
                                "Breaker", style="Heading 2")
heading._p.addprevious(breaker._tbl)

# 표지 표의 문서 목적 줄
for t in doc.tables[:1]:
    for row in t.rows:
        if row.cells[0].text.strip() == "Document purpose":
            row.cells[1].text = ("Competitive technical and commercial evaluation, with deviation "
                                 "candidates, cost/quality/commercial review items, contract "
                                 "risk clauses and a 24 kV circuit breaker datasheet")
doc.save(str(out))
print("saved", out)
