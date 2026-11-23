"""평가용 RFP(파일 24)에 부록 B 일탈 후보 데이터시트를 더한 RFP(파일 25)를 만든다.

부록 B 표(TS-170-GIS, D-01~D-11)는 4.2 표와 같은 항목을 더 엄격한 값으로 요구한다.
실제 제품표의 170 kV GIS와 비교하면 여러 줄이 일탈 후보가 된다. 9.3의 가스 누설률 0.5 %와
부록 B의 0.4 %가 달라 값 불일치 후보가 생긴다(generate_risk_rfp.py).

공개본에는 이 파일을 만든 스크립트가 없어, 합성 RFP 28 정답지(data/seed/answer_keys/
synthetic_rfp28_req.csv 40~50번 줄)의 표 줄로 다시 만들었다(add-eval-demo).
판정 줄은 표 줄만 읽으므로 원래 파일과 표 이름·머리·값이 같으면 결과가 같다.

실행: cd backend && uv run python ../generate_evaluative_rfp.py && uv run python ../generate_deviation_rfp.py
"""
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent
DOCX_DIR = ROOT / "data" / "private" / "rfp_docx"
src = DOCX_DIR / "RFP_Product_Master_Evaluative_EN.docx"
out = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Deviation_Candidates.docx"
doc = Document(str(src))

ROWS = [
    ["D-01", "Rated voltage", "kV", "≥180 kV"],
    ["D-02", "Rated continuous current", "A", "≥4000 A"],
    ["D-03", "Rated short-time withstand current", "kA", "≥60 kA"],
    ["D-04", "Rated lightning impulse withstand voltage", "kV", "≥800 kV"],
    ["D-05", "Rated short-duration power-frequency withstand voltage", "kV", "≥420 kV"],
    ["D-06", "Rated short-circuit making current", "kA", "≥130 kA"],
    ["D-07", "Total breaking time", "ms", "≤55 ms"],
    ["D-08", "Annual leakage rate for each gas compartment", "%", "≤0.4 %"],
    ["D-09", "Partial discharge", "pC", "≤3 pC"],
    ["D-10", "Maintenance period", "months", "≥24 months"],
    ["D-11", "Service life", "years", "≥35 years"],
]

gis_table = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "TS-170-GIS")
doc.add_heading("Appendix B — Project-Specific Datasheet", level=1)
table = doc.add_table(rows=2, cols=4)
table.style = gis_table.style
table.rows[0].cells[0].merge(table.rows[0].cells[3]).text = "TS-170-GIS"
for cell, text in zip(table.rows[1].cells, ["No.", "Description", "Unit",
                                            "Employer's Requirement"], strict=True):
    cell.text = text
for row in ROWS:
    for cell, text in zip(table.add_row().cells, row, strict=True):
        cell.text = text

for t in doc.tables[:1]:
    for row in t.rows:
        if row.cells[0].text.strip() == "Document purpose":
            row.cells[1].text = ("Competitive technical and commercial evaluation, with deviation "
                                 "candidates")
doc.save(str(out))
print("saved", out)
