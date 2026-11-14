import csv
from pathlib import Path
from collections import defaultdict

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.shared import Cm, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "data" / "seed" / "products" / "product_master.csv"
OUT_DIR = ROOT / "data" / "private" / "rfp_docx"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DOCX_OUT = OUT_DIR / "RFP_Product_Master_Evaluative_EN.docx"
XLSX_OUT = OUT_DIR / "RFP_Product_Master_Evaluation_Matrix_EN.xlsx"

with MASTER.open("r", encoding="utf-8-sig", newline="") as f:
    products = list(csv.DictReader(f))

families = defaultdict(list)
for product in products:
    families[product["family"]].append(product)

navy = "1F4E79"
light_blue = "D9EAF7"
grey = "E7E6E6"
white = "FFFFFF"
red = "C00000"

def clean(value):
    return (value or "-").strip() or "-"

def set_cell_text(cell, text, bold=False, size=8.5, color=None, fill=None):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)
    if fill:
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), fill)
        cell._tc.get_or_add_tcPr().append(shading)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

def add_table(doc, headers, rows, widths=None, font_size=8.5):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[index], header, bold=True, size=font_size,
                      color=(255, 255, 255), fill=navy)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            set_cell_text(cells[index], value, size=font_size)
    if widths:
        for table_row in table.rows:
            for index, width in enumerate(widths):
                table_row.cells[index].width = Cm(width)
    return table

# DOCX

doc = Document()
section = doc.sections[0]
section.top_margin = Cm(1.8)
section.bottom_margin = Cm(1.8)
section.left_margin = Cm(1.7)
section.right_margin = Cm(1.7)

normal = doc.styles["Normal"]
normal.font.name = "Aptos"
normal.font.size = Pt(10)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("REQUEST FOR PROPOSAL (RFP)")
r.bold = True
r.font.size = Pt(22)
r.font.color.rgb = RGBColor(31, 78, 121)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Product Master–Based Evaluative Procurement of Electrical Equipment")
r.bold = True
r.font.size = Pt(14)

add_table(doc, ["Control Item", "Value"], [
    ["Source master file", MASTER.name],
    ["Reference products", str(len(products))],
    ["Product families", str(len(families))],
    ["Document purpose", "Competitive technical and commercial evaluation"],
    ["Prepared date", "29 October 2026"],
], widths=[4.0, 12.0], font_size=9)

doc.add_heading("1. Procurement Objective", level=1)
doc.add_paragraph(
    "The Procuring Entity requests proposals for the supply and technical validation of electrical equipment. "
    "Each bidder shall identify eligible products, state compliance with every mandatory requirement, provide objective evidence, "
    "and complete the product-response and evaluation columns in the companion Excel workbook."
)
doc.add_paragraph(
    "The product master is a procurement baseline, not a bidder’s self-declaration and not evidence of compliance. "
    "Where a comparison value is marked as assumed, it must be replaced with verified manufacturer data in the bidder response."
)

doc.add_heading("2. Mandatory Proposal Submission", level=1)
for item in [
    "Completed Excel response matrix for every offered product and product-family requirement.",
    "Manufacturer product datasheet and a complete bill of materials for every offered item.",
    "Applicable IEC/ANSI/UL standards, declarations, certificates, and test reports.",
    "Clause-by-clause compliance statement; “Comply”, “Exception”, or “Not applicable” is required.",
    "Commercial proposal showing unit price, quantity, delivery term, warranty, and validity period.",
    "Manufacturer authorization, production facility information, after-sales organization, and technical support plan.",
    "Factory acceptance, type/routine test plan, packing, inspection, delivery, and commissioning approach.",
    "Evidence for maintenance interval, service life, warranty, spare parts, and lifecycle support.",
]:
    doc.add_paragraph(item, style="List Bullet")

doc.add_heading("3. Product-Family Scope", level=1)
family_rows = []
for family in sorted(families):
    items = families[family]
    name = items[0]["family_name"]
    voltages = []
    currents = []
    for item in items:
        for field, target in (("rated_voltage_kv", voltages), ("short_circuit_ka", currents)):
            try:
                target.append(float(item[field]))
            except (ValueError, TypeError):
                pass
    voltage_text = "-" if not voltages else (str(int(min(voltages))) if min(voltages) == max(voltages) else f"{min(voltages):g}–{max(voltages):g}") + " kV"
    current_text = "-" if not currents else (str(int(min(currents))) if min(currents) == max(currents) else f"{min(currents):g}–{max(currents):g}") + " kA"
    family_rows.append([family, name, len(items), voltage_text, current_text])
add_table(doc, ["Family Code", "Family", "Reference Products", "Rated Voltage", "Short-Circuit Current"], family_rows,
          widths=[3.0, 6.0, 3.0, 4.0, 4.0], font_size=8.3)

doc.add_heading("4. Technical Requirements and Evidence", level=1)
doc.add_paragraph(
    "The bidder shall complete one response row per offered product. A numeric or text response without a cited source is not accepted as evidence."
)
requirement_rows = [
    ["T1", "Product identity", "Product code, name, family, description, and product datasheet", "Mandatory", "product_code; product_name; family; description; source_doc; doc_ids"],
    ["T2", "Electrical rating", "Rated voltage, rated current, and short-circuit capability with applicable unit", "Mandatory", "rated_voltage_kv; rated_current_a; short_circuit_ka"],
    ["T3", "Standards and certifications", "Current applicable standards and independently verifiable certificates", "Mandatory", "standards; certifications; market"],
    ["T4", "Dielectric performance", "Lightning impulse, power-frequency withstand, and switching impulse as applicable", "Mandatory for applicable family", "lightning_impulse_kv; power_freq_withstand_kv; switching_impulse_kv"],
    ["T5", "Switching duty", "Peak/making current, breaking/closing time, and applicable interrupting evidence", "Mandatory for switchgear", "peak_current_ka; making_current_ka; breaking_time_ms; closing_time_ms"],
    ["T6", "Insulation and leakage", "Insulation medium, cooling, gas leakage (if GIS), and partial discharge", "Mandatory for GIS/higher-voltage equipment", "cooling_type; insulation_medium; gas_leakage_percent; partial_discharge_pc"],
    ["T7", "Lifecycle support", "Maintenance interval, service life, lifecycle status, warranty, and spares plan", "Mandatory", "maintenance_months; service_life_years; lifecycle_status; warranty_months"],
    ["T8", "Supply and logistics", "Weight, dimensions, MOQ, lead time, packing, shipping, and delivery capability", "Mandatory", "weight_kg; dimensions_mm; moq; std_lead_time_weeks"],
    ["T9", "Commercials", "List/offer price basis, currency, validity, payment and delivery terms", "Mandatory", "list_price_usd; market"],
    ["T10", "Environmental/operating limits", "Operating temperature, IP rating and installation limits supported by evidence", "Mandatory where applicable", "operating_temp; ip_rating"],
]
add_table(doc, ["ID", "Requirement", "Required Bidder Response", "Status", "Product-Master Source Columns"], requirement_rows,
          widths=[1.2, 3.0, 7.3, 3.0, 5.5], font_size=7.8)

# Recognizable datasheet-style requirement table for the automated judging pipeline.
doc.add_heading("4.2 Numeric Technical Datasheet Requirements", level=2)
judging_table = doc.add_table(rows=1, cols=4)
judging_table.style = "Table Grid"
judging_table.alignment = WD_TABLE_ALIGNMENT.CENTER
merged_title = judging_table.rows[0].cells[0].merge(judging_table.rows[0].cells[3])
set_cell_text(merged_title, "TS-170-GIS", bold=True, size=8.5, color=(255, 255, 255), fill=navy)
# Insert the header and data rows explicitly because build_tables recognizes the exact column-role headers.
header_cells = judging_table.add_row().cells
for index, header in enumerate(["No.", "Description", "Unit", "Employer's Requirement"]):
    set_cell_text(header_cells[index], header, bold=True, size=8.0,
                  color=(255, 255, 255), fill=navy)
judging_rows = [
    ["1", "Rated voltage", "kV", "≥170 kV"],
    ["2", "Rated continuous current", "A", "≥3150 A"],
    ["3", "Rated short-time withstand current", "kA", "≥50 kA"],
    ["4", "Rated lightning impulse withstand voltage", "kV", "≥750 kV"],
    ["5", "Rated short-duration power-frequency withstand voltage", "kV", "≥395 kV"],
    ["6", "Rated short-circuit making current", "kA", "≥125 kA"],
    ["7", "Total Breaking Time", "ms", "≤60 ms"],
    ["8", "Annual leakage rate for each gas compartment", "%", "≤0.5 %"],
    ["9", "Partial discharge", "pC", "≤5 pC"],
    ["10", "Maintenance period", "months", "≥12 months"],
    ["11", "Service life", "years", "≥30 years"],
]
for row in judging_rows:
    cells = judging_table.add_row().cells
    for index, value in enumerate(row):
        set_cell_text(cells[index], value, size=7.8)
for row in judging_table.rows:
    for index, width in enumerate([1.2, 7.0, 2.2, 5.6]):
        row.cells[index].width = Cm(width)

doc.add_heading("5. Evaluation Methodology", level=1)
doc.add_paragraph(
    "The Evaluation Committee shall score compliant proposals using the weight model below. Exceptions may be scored lower, made non-compliant, or rejected if they affect safety, certification, warranty, or contract viability."
)
criteria_rows = [
    ["Technical conformance", "40", "Mandatory requirements, standards, ratings, evidence completeness, and family applicability"],
    ["Verified performance", "20", "Manufacturer-backed dielectric, switching, insulation, leakage, and operating data"],
    ["Quality, testing and certification", "15", "Routine/type tests, certificates, independent laboratory evidence, production and QA capability"],
    ["Delivery and lifecycle", "10", "Lead time, warranty, maintenance, service life, spares and lifecycle status"],
    ["Technical support and implementation", "10", "Training, technical support, commissioning, documents and project organization"],
    ["Commercial value", "5", "Evaluated bid price and commercial terms"],
    ["Total", "100", ""],
]
add_table(doc, ["Evaluation Criterion", "Weight", "Scoring Basis"], criteria_rows,
          widths=[5.0, 2.0, 13.0], font_size=8.5)

doc.add_heading("5.1 Technical Scoring Guidance", level=2)
add_table(doc, ["Score", "Treatment"], [
    ["0", "No evidence, materially missing mandatory requirement, or conflicting data"],
    ["1–3", "Partial response, weak evidence, qualification, or significant exception"],
    ["4", "Compliant with evidence; minor improvement or clarification possible"],
    ["5", "Fully compliant with strong objective evidence and no material exception"],
], widths=[3.0, 13.0], font_size=8.5)

doc.add_heading("6. Assumed/Unverified Values", level=1)
p = doc.add_paragraph()
r = p.add_run("Important: ")
r.bold = True
r.font.color.rgb = RGBColor(192, 0, 0)
doc.add_paragraph(
    "Product-master records marked comparison_values_assumed=Y contain demonstration or synthesized comparison values. "
    "These values shall not be treated as guarantees, test results, catalog ratings, or contractual requirements. "
    "The bidder must verify, replace, or reject every applicable assumed value with manufacturer documentation."
)

doc.add_heading("7. Bidder Response Declaration", level=1)
add_table(doc, ["Item", "Bidder Completion"], [
    ["Legal bidder name", ""],
    ["Manufacturer and authorized entity", ""],
    ["Products offered / excluded", ""],
    ["Exceptions / deviations", ""],
    ["Authorized representative and date", ""],
], widths=[7.0, 13.0], font_size=8.5)

# Append concise catalog inventory by family
doc.add_heading("Appendix A — Reference Product Inventory", level=1)
for family in sorted(families):
    items = families[family]
    doc.add_heading(f"A.{sorted(families).index(family)+1} {family} — {items[0]['family_name']}", level=2)
    rows = []
    for product in items:
        rows.append([
            clean(product["product_code"]), clean(product["product_name"]),
            clean(product["rated_voltage_kv"]), clean(product["rated_current_a"]),
            clean(product["short_circuit_ka"]), clean(product["standards"]),
        ])
    add_table(doc, ["Product Code", "Product Name", "Voltage (kV)", "Current (A)", "Short Circuit (kA)", "Standards"], rows,
              widths=[3.0, 5.5, 2.2, 2.0, 2.5, 5.0], font_size=7.0)

props = doc.core_properties
props.title = "Evaluative RFP Based on Product Master"
props.subject = "Electrical equipment technical and commercial evaluation"
props.author = "RFP AI Agent"
doc.save(DOCX_OUT)

# XLSX companion
wb = Workbook()
ws = wb.active
ws.title = "Instructions"
ws.append(["Evaluative RFP — Bidder Response Workbook"])
ws.append(["Source", str(MASTER)])
ws.append(["Reference products", len(products)])
ws.append(["Reference families", len(families)])
ws.append([])
ws.append(["How to use"])
ws.append(["1", "Complete one row per offered product in the Product Response sheet."])
ws.append(["2", "Use the Requirements sheet to record compliance and evidence for each requirement."])
ws.append(["3", "Replace assumed comparison values with manufacturer-backed values and evidence references."])
ws.append(["4", "Attach/refer to page numbers, datasheets, certificates, and test reports in the evidence fields."])
ws.append(["5", "Do not treat master values as evidence without bidder verification."])

thin = Side(style="thin", color="B7B7B7")
for row in ws.iter_rows():
    for cell in row:
        cell.border = Border(bottom=thin)
        cell.alignment = Alignment(vertical="top", wrap_text=True)
ws["A1"].font = Font(bold=True, size=16, color=white)
ws["A1"].fill = PatternFill("solid", fgColor=navy)
ws.merge_cells("A1:D1")
ws.column_dimensions["A"].width = 18
ws.column_dimensions["B"].width = 100

# Evaluation criteria
crit = wb.create_sheet("Evaluation Criteria")
crit.append(["Criterion", "Weight (%)", "Basis", "Minimum Evidence"])
for row in [
    ["Technical conformance", 40, "Ratings, standards, required functions and complete response", "Datasheet, clauses, certificates"],
    ["Verified performance", 20, "Dielectric, switching, insulation and operating performance", "Manufacturer data and test reports"],
    ["Quality, testing and certification", 15, "Type/routine tests, certificates, production QA", "Reports, certificates, QA plan"],
    ["Delivery and lifecycle", 10, "Lead time, warranty, maintenance, service life and spares", "Schedule and lifecycle terms"],
    ["Technical support and implementation", 10, "Support, training, commissioning and documents", "Organization and support plan"],
    ["Commercial value", 5, "Evaluated price and commercial terms", "Priced bid and terms"],
    ["Total", 100, "", ""],
]:
    crit.append(row)

# Requirements response
req = wb.create_sheet("Requirements Response")
req_headers = ["Requirement ID", "Requirement", "Status", "Bidder Response", "Evidence Reference", "Evaluator Finding", "Evaluator Score (0–5)"]
req.append(req_headers)
for requirement in requirement_rows:
    req.append([requirement[0], requirement[2], "Comply/Exception/N/A", "", "Datasheet/report page", "", ""])

# Product response: source master columns plus bidder response/evaluation columns
response_fields = list(products[0].keys()) if products else []
product = wb.create_sheet("Product Response")
headers = response_fields + ["Bidder Offered?", "Bidder Product/Version", "Compliance Status", "Exception/Deviation", "Evidence Reference", "Evaluator Score (0–5)", "Evaluator Comment"]
product.append(headers)
for p in products:
    product.append([clean(p.get(field)) for field in response_fields] + ["", "", "Comply/Exception/N/A", "", "", "", ""])

# Assumed-value register
assumed = wb.create_sheet("Assumed Value Register")
assumed.append(["Product Code", "Column", "Master Value", "Assumed?", "Bidder Verified Value", "Evidence Reference", "Evaluator Finding"])
assumed_fields = [
    "lightning_impulse_kv", "power_freq_withstand_kv", "switching_impulse_kv",
    "peak_current_ka", "making_current_ka", "breaking_time_ms", "closing_time_ms",
    "gas_leakage_percent", "partial_discharge_pc", "cooling_type",
    "insulation_medium", "maintenance_months", "service_life_years",
]
for p in products:
    if clean(p.get("comparison_values_assumed")).upper() == "Y":
        for field in assumed_fields:
            assumed.append([p["product_code"], field, clean(p.get(field)), "Y", "", "", ""])

# Formatting helper
for sheet in wb.worksheets:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=navy)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=Side(style="hair", color="D9E2F3"))
    max_widths = {}
    for row in sheet.iter_rows():
        for cell in row:
            value = "" if cell.value is None else str(cell.value)
            max_widths[cell.column] = min(max(max_widths.get(cell.column, 0), len(value)), 45)
    for col, width in max_widths.items():
        sheet.column_dimensions[chr(64 + col) if col <= 26 else "A"].width = width if width else 10

# Correct wider columns and add tables where useful
for sheet_name in ["Evaluation Criteria", "Requirements Response", "Product Response", "Assumed Value Register"]:
    sheet = wb[sheet_name]
    if sheet.max_row >= 2:
        ref = f"A1:{chr(64 + sheet.max_column)}{sheet.max_row}" if sheet.max_column <= 26 else sheet.dimensions
        # avoid tables over 26 columns for exotic references; Excel tables can use full dimensions
        if sheet_name != "Product Response":
            table = Table(displayName="Table_" + sheet_name.replace(" ", ""), ref=sheet.dimensions)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False, showLastColumn=False)
            sheet.add_table(table)
product.column_dimensions["A"].width = 14
product.column_dimensions["B"].width = 35
product.auto_filter.ref = product.dimensions

wb.save(XLSX_OUT)
print(f"Generated: {DOCX_OUT}")
print(f"Generated: {XLSX_OUT}")
print(f"Products: {len(products)}, Families: {len(families)}")
