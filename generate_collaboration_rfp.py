"""일탈 후보 RFP(파일 25)에 협조 요청 항목(8장)을 더한 시험용 RFP(파일 26)를 만든다.

8.1은 견적(COST: "evaluated price", "spare parts"), 8.2는 품질(TEST: "Type Test", "Routine Test",
"test report"), 8.3은 영업(MAKER_QUAL: "ISO 9001", "experience", "authorization letter")
유형 규칙(data/seed/type_rules.csv)에 걸리는 문장이다.
분석이 끝나면 협조 요청 화면에 견적·품질·영업 담당별로 3건씩 생긴다.

실행: cd backend && uv run python ../generate_collaboration_rfp.py
"""
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent
DOCX_DIR = ROOT / "data" / "private" / "rfp_docx"
src = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Deviation_Candidates.docx"
out = DOCX_DIR / "RFP_Product_Master_Evaluative_EN_With_Collaboration_Requests.docx"
doc = Document(str(src))
anchor = next(p for p in doc.paragraphs if p.text.startswith("Appendix A"))

SECTIONS = [
    ("8. Quotation, Quality and Supplier Qualification Requirements", "Heading 1", [
        "The requirements in this section are reviewed by the Procuring Entity's cost, quality "
        "and commercial teams together with the technical evaluation.",
    ]),
    # 견적 (COST): evaluated price, spare parts
    ("8.1 Quotation and Evaluated Price", "Heading 2", [
        "The evaluated price shall include transportation, insurance, installation supervision "
        "and commissioning for each offered GIS bay.",
        "The bidder shall submit a separately priced list of recommended spare parts for five (5) "
        "years of operation.",
        "The evaluated price shall state the currency, price validity period and payment "
        "milestones for the complete scope of supply.",
    ]),
    # 품질 (TEST): Type Test, Routine Test, test report
    ("8.2 Testing and Quality Assurance", "Heading 2", [
        "Type Test reports issued by an independent accredited laboratory shall be submitted for "
        "the offered GIS.",
        "Routine Test shall be performed on every GIS bay at the factory and shall be witnessed "
        "by the Procuring Entity.",
        "The bidder shall submit the factory test report and the inspection and test plan at "
        "least four (4) weeks before shipment.",
    ]),
    # 영업 (MAKER_QUAL): ISO 9001, experience, authorization letter
    ("8.3 Supplier Qualification", "Heading 2", [
        "The manufacturer shall hold a valid ISO 9001 certificate for the production facility of "
        "the offered equipment.",
        "The bidder shall have at least ten (10) years of experience in manufacturing and "
        "supplying gas-insulated switchgear.",
        "An authorization letter from the manufacturer shall be submitted with the proposal.",
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
                                 "candidates and cost/quality/commercial review items")
doc.save(str(out))
print("saved", out)
