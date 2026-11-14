"""협조 요청 RFP(파일 26)에 위험 조항(9장)을 더한 시연용 RFP(파일 27)를 만든다 (add-synthetic-risk-rfp).

위험 조건은 표현이 맞는 절 제목 안에 있어야 후보가 된다(backend risk.CONTEXT_WORDS).
9.1은 계약·일탈 조항의 포괄 조항(BLANKET: "deemed", "no deviations"),
9.2는 공급 범위 조항의 범위 모호(OPEN_SCOPE: "including but not limited to")와
비용 전가(COST_SHIFT: "at no extra cost"),
9.3은 부록 B 데이터시트(가스 누설률 0.4 %)와 다른 값(0.5 %)으로 값 불일치(VALUE_MISMATCH)다.
분석이 끝나면 위험 조건 탭에 세 종류가 모두 보인다.

실행: cd backend && uv run python ../generate_risk_rfp.py
"""
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent
DOCX_DIR = ROOT / "data" / "private" / "rfp_docx"
src = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Collaboration_Requests.docx"
out = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Risk_Clauses.docx"
doc = Document(str(src))
anchor = next(p for p in doc.paragraphs if p.text.startswith("Appendix A"))

SECTIONS = [
    ("9. Contract Conditions, Deviations and Scope of Supply", "Heading 1", [
        "The conditions in this section form part of the contract and apply to the complete "
        "scope of supply of the offered equipment.",
    ]),
    # 포괄 조항 (BLANKET): deemed, no deviation(s)
    ("9.1 Deviations and Clarifications", "Heading 2", [
        "Any deviation that is not listed in the bidder's deviation schedule shall be deemed to "
        "be accepted by the bidder.",
        "No deviations from the technical requirements will be accepted after contract award.",
    ]),
    # 범위 모호 (OPEN_SCOPE): including but not limited to / 비용 전가 (COST_SHIFT): at no extra cost
    ("9.2 Scope of Supply", "Heading 2", [
        "The scope of supply shall cover all accessories required for safe operation, including "
        "but not limited to special tools, earthing devices and gas handling equipment.",
        "Any item that is not explicitly mentioned but is necessary for the complete installation "
        "shall be supplied at no extra cost to the Procuring Entity.",
    ]),
    # 값 불일치 (VALUE_MISMATCH): 부록 B 데이터시트는 0.4 %
    ("9.3 Technical Clarifications", "Heading 2", [
        "The annual gas leakage rate of each gas compartment of the GIS shall not exceed 0.5 %.",
    ]),
]

for title, style, sentences in SECTIONS:
    anchor.insert_paragraph_before(title, style=style)
    for s in sentences:
        anchor.insert_paragraph_before(s, style="Normal")

# 표지 표의 문서 목적 줄
for t in doc.tables[:1]:
    for row in t.rows:
        if row.cells[0].text.strip() == "Document purpose":
            row.cells[1].text = ("Competitive technical and commercial evaluation, with deviation "
                                 "candidates, cost/quality/commercial review items and contract "
                                 "risk clauses")
doc.save(str(out))
print("saved", out)
