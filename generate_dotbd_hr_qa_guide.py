# -*- coding: utf-8 -*-

from datetime import date
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

OUTPUT = Path(r"D:\Downloads\kep19\odoo19\artifacts\dotbd_hr_custom_modules_qa_workflows.docx")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def dxa(inches):
    return int(round(inches * 1440))


def xml_text(value):
    return escape("" if value is None else str(value))


def run(text, bold=False, size=22, color="000000", italic=False):
    parts = []
    parts.append(f'<w:r><w:rPr>')
    parts.append(f'<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>')
    parts.append(f'<w:sz w:val="{size}"/>')
    if color:
        parts.append(f'<w:color w:val="{color}"/>')
    if bold:
        parts.append("<w:b/>")
    if italic:
        parts.append("<w:i/>")
    parts.append(f'</w:rPr><w:t xml:space="preserve">{xml_text(text)}</w:t></w:r>')
    return "".join(parts)


def paragraph(text=None, runs=None, align="left", before=0, after=120, line=280, size=22, bold=False, color="000000"):
    jc = "" if align == "left" else f'<w:jc w:val="{align}"/>'
    p = [f'<w:p><w:pPr>{jc}<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/></w:pPr>']
    if runs is None:
        runs = []
        if text is not None:
            runs = [(text, bold, size, color, False)]
    for item in runs:
        if isinstance(item, str):
            p.append(run(item, size=size, color=color))
        else:
            p.append(run(*item))
    p.append("</w:p>")
    return "".join(p)


def table_cell(text, width, bold=False, size=19, fill=None, align="left"):
    fill_xml = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
    jc = "" if align == "left" else f'<w:jc w:val="{align}"/>'
    return (
        f'<w:tc><w:tcPr>'
        f'<w:tcW w:type="dxa" w:w="{width}"/>'
        f'<w:vAlign w:val="center"/>'
        f'<w:tcMar><w:top w:w="80" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:start w:w="120" w:type="dxa"/><w:end w:w="120" w:type="dxa"/></w:tcMar>'
        f'{fill_xml}'
        f'</w:tcPr>'
        f'<w:p><w:pPr>{jc}<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
        f'{run(text, bold=bold, size=size)}'
        f'</w:p>'
        f'</w:tc>'
    )


def table_row(cells, widths, header=False):
    fill = "E8EEF5" if header else None
    row = ["<w:tr>"]
    for idx, cell_text in enumerate(cells):
        row.append(table_cell(cell_text, widths[idx], bold=header, size=19 if not header else 20, fill=fill, align="center" if header else "left"))
    row.append("</w:tr>")
    return "".join(row)


def make_table(headers, rows, widths):
    tbl = [
        '<w:tbl>',
        '<w:tblPr>',
        f'<w:tblW w:type="dxa" w:w="{sum(widths)}"/>',
        '<w:tblInd w:type="dxa" w:w="120"/>',
        '<w:tblLayout w:type="fixed"/>',
        '<w:tblBorders>',
        '<w:top w:val="single" w:sz="8" w:space="0" w:color="D0D7DE"/>',
        '<w:left w:val="single" w:sz="8" w:space="0" w:color="D0D7DE"/>',
        '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="D0D7DE"/>',
        '<w:right w:val="single" w:sz="8" w:space="0" w:color="D0D7DE"/>',
        '<w:insideH w:val="single" w:sz="8" w:space="0" w:color="D0D7DE"/>',
        '<w:insideV w:val="single" w:sz="8" w:space="0" w:color="D0D7DE"/>',
        '</w:tblBorders>',
        '</w:tblPr>',
        '<w:tblGrid>' + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + '</w:tblGrid>',
        table_row(headers, widths, header=True),
    ]
    for row in rows:
        tbl.append(table_row(row, widths, header=False))
    tbl.append("</w:tbl>")
    return "".join(tbl)


def styles_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="280" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr>
    <w:pPr><w:spacing w:after="120" w:line="280" w:lineRule="auto"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:qFormat/>
    <w:basedOn w:val="Normal"/>
    <w:link w:val="TitleChar"/>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="32"/><w:b/></w:rPr>
    <w:pPr><w:spacing w:before="0" w:after="60" w:line="280" w:lineRule="auto"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:qFormat/>
    <w:basedOn w:val="Normal"/>
    <w:uiPriority w:val="9"/>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="28"/><w:b/><w:color w:val="2E74B5"/></w:rPr>
    <w:pPr><w:spacing w:before="360" w:after="120" w:line="280" w:lineRule="auto"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:qFormat/>
    <w:basedOn w:val="Normal"/>
    <w:uiPriority w:val="9"/>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="26"/><w:b/><w:color w:val="2E74B5"/></w:rPr>
    <w:pPr><w:spacing w:before="240" w:after="100" w:line="280" w:lineRule="auto"/></w:pPr>
  </w:style>
</w:styles>'''


def content_types_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CT_NS}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''


def rels_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def core_xml():
    today = date(2026, 8, 31).isoformat()
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="{CP_NS}" xmlns:dc="{DC_NS}" xmlns:dcterms="{DCTERMS_NS}" xmlns:dcmitype="{DCTERMS_NS}" xmlns:xsi="{XSI_NS}">
  <dc:title>DotBD HR Custom Modules - Workflows and QA Test Cases</dc:title>
  <dc:subject>QA workflow guide</dc:subject>
  <dc:creator>OpenAI Codex</dc:creator>
  <cp:keywords>Odoo, HR, QA, workflows, test cases</cp:keywords>
  <dc:description>Consolidated workflows and QA test cases for DotBD HR custom modules.</dc:description>
  <cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{today}T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{today}T00:00:00Z</dcterms:modified>
</cp:coreProperties>'''


def app_xml():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>'''


def build_document_xml():
    headers = ["Module", "Implemented workflow", "QA must verify"]
    widths = [1700, 4100, 3560]
    rows = [
        [
            "Manpower Requisition",
            "Draft -> Submit -> Budget Verify -> Approve or Reject. Partial approval is supported. Approved requests can create or update linked job positions.",
            "Submit validation, budget verify action, approval or rejection, partial approval, job position creation, duplicate protection, reset flow.",
        ],
        [
            "Leave Policy",
            "Policies are driven by employee category. The module supports yearly allocation, probation allocations, earned leave eligibility, carry-forward, and old balance import.",
            "Probation allowance, earned leave trigger after service, carry-forward cap, policy-line matching, balance generation, import and reset, multi-company access.",
        ],
        [
            "Shift Roster",
            "Shift templates generate roster lines. Roster states move Draft -> Generated -> Confirmed -> Done or Cancelled. Assignments and weekly off are handled by employee and department/category.",
            "Generate lines, confirm or reset, employee/category filtering, department roster, correct dates and times, count refresh, no missing field or view errors.",
        ],
        [
            "ZK Attendance",
            "Biometric attendance updates check-in and check-out data and computes late arrival, early exit, overtime, and roster-based attendance behavior.",
            "Check-in/out import, overtime, late check-in, missing punch scenario, roster linkage, no undefined column errors, employee form opens cleanly.",
        ],
        [
            "Attendance Regularization",
            "Employee submits a missed punch or attendance correction request. Manager approves or rejects. Approved requests update hr.attendance; rejected requests do not.",
            "Create request, submit, approve, reject, duplicate-request handling, no duplicate attendance, approved attendance update on the correct day.",
        ],
        [
            "Overtime Request",
            "Manual overtime request is separate from automatic ZK overtime. After approval, OT can be consumed by payroll or attendance logic.",
            "Request creation, manager approval, rejection, payroll-ready status, no double counting with automatic ZK OT.",
        ],
        [
            "Onboarding",
            "Onboarding templates create checklist steps, documents, notes, attachments, and progress tracking for newly hired employees.",
            "Template lines, checklist order, attachments, note placement, progress calculation, document upload, stage completion flow.",
        ],
    ]

    body = []
    body.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    body.append(f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}"><w:body>')
    body.append('<w:p><w:pPr><w:jc w:val="left"/><w:spacing w:before="0" w:after="60" w:line="280" w:lineRule="auto"/></w:pPr>'
                + run("DotBD HR Custom Modules - Workflows and QA Test Cases", bold=True, size=32)
                + '</w:p>')
    body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="80" w:line="260" w:lineRule="auto"/></w:pPr>'
                + run("Scope: dotbd_hr_manpower_requisition_suite, dotbd_hr_leave_policy_suite, dotbd_hr_shift_roster_suite, dotbd_hr_zk_attendance_suite, dotbd_hr_attendance_regularization_suite, dotbd_hr_overtime_request_suite, dotbd_hr_onboarding_suite.", size=21)
                + '</w:p>')
    body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="80" w:line="260" w:lineRule="auto"/></w:pPr>'
                + run("Purpose: Give QA one consolidated guide for the implemented workflows, key business rules, and the most important test cases to verify after upgrades.", size=22)
                + '</w:p>')

    body.append('<w:p><w:pPr><w:spacing w:before="360" w:after="120" w:line="280" w:lineRule="auto"/></w:pPr>' + run("1. Workflow Summary by Module", bold=True, size=28, color="2E74B5") + '</w:p>')
    body.append(make_table(headers, rows, widths))

    body.append('<w:p><w:pPr><w:spacing w:before="240" w:after="120" w:line="280" w:lineRule="auto"/></w:pPr>' + run("2. Cross-Module Regression Checks", bold=True, size=28, color="2E74B5") + '</w:p>')
    checks = [
        "Employee form opens without access errors, missing field errors, or undefined SQL columns.",
        "Probation end date is auto-derived from joining date if not manually set.",
        "During probation, leave requests are limited to the allowed leave types and monthly cap configured in the policy.",
        "Leave balance import uses CSV or manual lines only, and blank lines are not created automatically.",
        "Reset Imported removes only opening-balance records created by the import flow, not manual balances.",
        "Generated leave balances display Year, Opening Balance, Accrued Leave, Utilized Leave, and Closing Balance clearly.",
        "Company and multi-company rules do not block the correct leave types for the employee's company.",
        "Leave and attendance actions do not create duplicates when the same employee and day are processed twice.",
    ]
    for item in checks:
        body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="60" w:line="260" w:lineRule="auto"/></w:pPr>'
                    + run("QA check: ", bold=True, size=21)
                    + run(item, size=21)
                    + '</w:p>')

    body.append('<w:p><w:pPr><w:spacing w:before="240" w:after="120" w:line="280" w:lineRule="auto"/></w:pPr>' + run("3. Suggested QA Test Priority", bold=True, size=28, color="2E74B5") + '</w:p>')
    body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="60" w:line="260" w:lineRule="auto"/></w:pPr>' + run("High priority: ", bold=True, size=22) + run("Leave policy, leave balance import, attendance regularization, and shift roster generation.", size=22) + '</w:p>')
    body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="60" w:line="260" w:lineRule="auto"/></w:pPr>' + run("Medium priority: ", bold=True, size=22) + run("Manpower requisition, overtime request, and onboarding template flows.", size=22) + '</w:p>')
    body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="60" w:line="260" w:lineRule="auto"/></w:pPr>' + run("Test data note: ", bold=True, size=22) + run("Use employees from both worker and office categories, and test both new joiners and old employees with carry-forward balances.", size=22) + '</w:p>')

    body.append(
        '<w:sectPr>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="708"/>'
        '</w:sectPr>'
    )
    body.append('</w:body></w:document>')
    return "".join(body)


def write_docx():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml())
        zf.writestr("_rels/.rels", rels_xml())
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("docProps/app.xml", app_xml())
        zf.writestr("word/document.xml", build_document_xml())
        zf.writestr("word/styles.xml", styles_xml())
        zf.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="' + PKG_REL_NS + '"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')


if __name__ == "__main__":
    write_docx()
    print(OUTPUT)
