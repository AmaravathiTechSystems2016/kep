# -*- coding: utf-8 -*-

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'artifacts' / 'dotbd_hr_custom_modules_lifecycle_sop.docx'
BLUE = '2E74B5'
DARK_BLUE = '1F4D78'
INK = '0B2545'
MUTED = '555555'
LIGHT_BLUE = 'E8EEF5'
LIGHT_GRAY = 'F2F4F7'
GOLD = 'FFF4CC'
RED = 'FCE8E6'
WIDTH = 9360


def set_font(run, name='Calibri', size=11, color='000000', bold=False, italic=False):
    run.font.name = name
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:ascii'), name)
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:hAnsi'), name)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.bold = bold
    run.italic = italic


def style_document(doc):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.35)

    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal._element.rPr.rFonts.set(qn('w:ascii'), 'Calibri')
    normal._element.rPr.rFonts.set(qn('w:hAnsi'), 'Calibri')
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    for name, size, color, before, after in [
        ('Title', 27, INK, 0, 5),
        ('Heading 1', 17, BLUE, 18, 6),
        ('Heading 2', 13, BLUE, 13, 4),
        ('Heading 3', 11.5, DARK_BLUE, 9, 3),
    ]:
        s = doc.styles[name]
        s.font.name = 'Calibri'
        s._element.rPr.rFonts.set(qn('w:ascii'), 'Calibri')
        s._element.rPr.rFonts.set(qn('w:hAnsi'), 'Calibri')
        s.font.size = Pt(size)
        s.font.color.rgb = RGBColor.from_string(color)
        s.font.bold = True
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(after)
        s.paragraph_format.keep_with_next = True

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = header.add_run('Dot BD HR Custom Modules | Operator SOP')
    set_font(r, size=8.5, color=MUTED)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run('Internal HR operations guide | Update after workflow changes')
    set_font(r, size=8, color=MUTED)


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    node = tc_pr.find(qn('w:shd'))
    if node is None:
        node = OxmlElement('w:shd')
        tc_pr.append(node)
    node.set(qn('w:fill'), fill)


def cell_margins(cell, top=90, bottom=90, start=120, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in('w:tcMar')
    if margins is None:
        margins = OxmlElement('w:tcMar')
        tc_pr.append(margins)
    for side, value in [('top', top), ('bottom', bottom), ('start', start), ('end', end)]:
        node = margins.find(qn(f'w:{side}'))
        if node is None:
            node = OxmlElement(f'w:{side}')
            margins.append(node)
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')


def table_geometry(table, widths):
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    props = table._tbl.tblPr
    width = props.find(qn('w:tblW'))
    if width is None:
        width = OxmlElement('w:tblW')
        props.append(width)
    width.set(qn('w:type'), 'dxa')
    width.set(qn('w:w'), str(sum(widths)))
    indent = props.find(qn('w:tblInd'))
    if indent is None:
        indent = OxmlElement('w:tblInd')
        props.append(indent)
    indent.set(qn('w:type'), 'dxa')
    indent.set(qn('w:w'), '120')
    layout = props.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout')
        props.append(layout)
    layout.set(qn('w:type'), 'fixed')
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for w in widths:
        col = OxmlElement('w:gridCol')
        col.set(qn('w:w'), str(w))
        grid.append(col)
    for row in table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = Inches(w / 1440)
            tc_w = cell._tc.get_or_add_tcPr().find(qn('w:tcW'))
            if tc_w is None:
                tc_w = OxmlElement('w:tcW')
                cell._tc.get_or_add_tcPr().append(tc_w)
            tc_w.set(qn('w:type'), 'dxa')
            tc_w.set(qn('w:w'), str(w))
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell_margins(cell)


def borders(table, color='B7C9DF'):
    props = table._tbl.tblPr
    border = props.first_child_found_in('w:tblBorders')
    if border is None:
        border = OxmlElement('w:tblBorders')
        props.append(border)
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        node = border.find(qn(f'w:{edge}'))
        if node is None:
            node = OxmlElement(f'w:{edge}')
            border.append(node)
        node.set(qn('w:val'), 'single')
        node.set(qn('w:sz'), '6')
        node.set(qn('w:space'), '0')
        node.set(qn('w:color'), color)


def add_table(doc, headers, rows, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    for cell, text in zip(table.rows[0].cells, headers):
        shade(cell, LIGHT_BLUE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text)
        set_font(r, size=9, color=INK, bold=True)
    for row_data in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, row_data):
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(str(text))
            set_font(r, size=8.8, color='000000')
    table_geometry(table, widths)
    borders(table)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def para(doc, text='', bold_prefix=None, style=None):
    p = doc.add_paragraph(style=style)
    if bold_prefix and text.startswith(bold_prefix):
        r = p.add_run(bold_prefix)
        set_font(r, bold=True)
        r = p.add_run(text[len(bold_prefix):])
        set_font(r)
    else:
        r = p.add_run(text)
        set_font(r)
    return p


def heading(doc, text, level=1):
    return doc.add_heading(text, level=level)


def bullet(doc, text):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    set_font(r, size=10)
    return p


def number(doc, text):
    p = doc.add_paragraph(style='List Number')
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    set_font(r, size=10)
    return p


def callout(doc, label, text, fill=LIGHT_BLUE):
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    table.cell(0, 0).width = Inches(6.5)
    shade(table.cell(0, 0), fill)
    cell_margins(table.cell(0, 0), top=110, bottom=110, start=150, end=150)
    p = table.cell(0, 0).paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(label + ': ')
    set_font(r, color=INK, bold=True, size=10)
    r = p.add_run(text)
    set_font(r, size=10)
    table_geometry(table, [9360])
    doc.add_paragraph().paragraph_format.space_after = Pt(1)


def module_section(doc, name, purpose, menu, owner, steps, checks, notes=None):
    heading(doc, name, 1)
    para(doc, purpose)
    add_table(doc, ['Owner', 'Menu / entry point', 'Primary result'], [[owner, menu, 'Use the workflow and record the outcome.']], [1800, 3000, 4560])
    heading(doc, 'How to use', 2)
    for step in steps:
        number(doc, step)
    heading(doc, 'Acceptance checks', 2)
    for check in checks:
        bullet(doc, check)
    if notes:
        callout(doc, 'Implementation note', notes, GOLD)


def build():
    doc = Document()
    style_document(doc)
    p = doc.add_paragraph(style='Title')
    r = p.add_run('Dot BD HR Custom Modules')
    set_font(r, size=27, color=INK, bold=True)
    p = doc.add_paragraph()
    r = p.add_run('Consolidated SOP: setup, usage, access control, and QA')
    set_font(r, size=15, color=BLUE, bold=True)
    para(doc, 'Version 1.0 | 05 September 2026 | Odoo 19 | Database: kep2')
    callout(doc, 'Purpose', 'This guide explains what has been implemented in the custom HR modules, how each role uses the system, and how QA should verify the workflows. It is written for HR, department managers, employees, payroll users, and testers.')

    heading(doc, 'Start here: learn the system', 1)
    para(doc, 'A new user should first learn the role assigned to their account. The same Odoo screen can show different records and buttons depending on the role. Follow the learning path below, then use the module sections for the detailed procedure.')
    add_table(doc, ['Learning step', 'What to learn', 'Where to practice'], [
        ['1. Sign in', 'Identify the user account, company and assigned HR role.', 'User menu and application switcher'],
        ['2. Understand the employee', 'Employee master data is the source for department, manager, category, joining date, work location, notice period and payroll profile.', 'Employees -> Employees -> employee form'],
        ['3. Understand requests', 'Draft records are prepared first, then submitted or confirmed for approval.', 'Leave, Regularization, Overtime, Manpower and Resignation'],
        ['4. Understand approvals', 'Managers approve only records inside their department; HR handles company-wide processing.', 'Requests to Approve and department lists'],
        ['5. Understand records', 'Attendance, leave balances, payslips, onboarding progress and offboarding statuses are reviewed after processing.', 'Dashboards, reports and employee smart buttons'],
        ['6. Practice safely', 'Use a test employee and test department. Never test approval or deletion on live payroll records.', 'QA database only'],
    ], [1900, 4400, 3160])
    heading(doc, 'What has been developed', 2)
    for item in [
        'A single employee master record with personal, statutory, employment, attendance, leave, payroll and offboarding information.',
        'Department-based access so employees see their own records, managers see their department and HR sees the company scope.',
        'Attendance dashboard, biometric/ZK data, check-in/check-out history, late check-in and regularization workflow.',
        'Category-based leave policy and allocation support for Manufacturing Workers and Computer/Office Staff.',
        'Shift templates, employee assignments and generated roster lines.',
        'Payroll profiles and salary-rule inputs for worker and computer-worker categories, including PF/ESI flags and overtime input.',
        'Onboarding checklist and manpower requisition workflows.',
        'A separate resignation offboarding module for handover, clearance, settlement inputs, exit interview, documents and PF/ESI transfer tracking.',
    ]:
        bullet(doc, item)
    heading(doc, 'What is not automatic yet', 2)
    for item in [
        'Gratuity, leave encashment and final settlement amounts require HR/Finance entry.',
        'PF/ESI transfer is tracked as a status and note; the online transfer is not performed inside Odoo.',
        'Relieving and experience certificates are tracked as issued/not issued; automatic certificate PDF generation is not included.',
        'Payroll policy items such as HRA formulas, PF/ESI ceilings, complete PT/TDS rules and exact 2x gross daily overtime need further salary-rule automation if required.',
    ]:
        bullet(doc, item)

    heading(doc, '1. Scope', 1)
    para(doc, 'The current solution extends Odoo HR for employee master data, department-based access, biometric attendance, leave policy, shift roster, overtime, payroll, onboarding, manpower requisitions, regularization, and resignation offboarding.')
    add_table(doc, ['Custom module', 'Implemented capability', 'Main users'], [
        ['Access Control Suite', 'Role and department-based access for HR workflows and employee data.', 'Employees, department managers, HR, executives'],
        ['Manpower Requisition Suite', 'Worker/office categories, master employee fields, requisition workflow.', 'HR, managers'],
        ['ZK Attendance Suite', 'Biometric sync, attendance dashboard, late check-in, reports.', 'Employees, managers, HR, attendance officer'],
        ['Attendance Regularization Suite', 'Requests for missing or incorrect punches.', 'Employees, managers, HR'],
        ['Leave Policy Suite', 'Category-based leave policy, probation allocation, balances, carry-forward.', 'Employees, managers, HR'],
        ['Shift Roster Suite', 'Shift templates, assignments, roster generation and confirmation.', 'Managers, HR, attendance officer'],
        ['Payroll Suite', 'Payroll profiles, allowances, PF/ESI flags, overtime input.', 'Payroll, HR'],
        ['Onboarding Suite', 'Employee onboarding templates, checklist, progress and documents.', 'HR, managers'],
        ['Resignation Offboarding Suite', 'Handover, clearance, settlement inputs, exit interview and documents.', 'Employee, manager, HR, Finance, Admin'],
    ], [2200, 4800, 2360])

    heading(doc, '2. Roles and access', 1)
    add_table(doc, ['Role', 'Expected access'], [
        ['Employee', 'Own attendance history, own dashboard data, leave requests, own payslips, own resignation request. No approval actions.'],
        ['Manufacturing Worker', 'Employee access plus worker category behavior, shift/biometric identification where configured.'],
        ['Department Manager', 'Employees assigned to the manager department; attendance, leave, overtime, regularization and resignation approvals for that department.'],
        ['HR Officer', 'Company-wide HR operational access, approvals, employee master data, payroll and offboarding records.'],
        ['HR Manager', 'HR Officer access plus manager-level contract and configuration access.'],
        ['CEO / Managing Director', 'Executive access to company-wide HR workflows.'],
        ['Attendance Officer', 'Attendance operations and biometric device administration.'],
    ], [2300, 7060])
    callout(doc, 'Security rule', 'Record rules are the real protection. Hiding a menu or button alone is not sufficient. Always test access by logging in as the actual role.')

    heading(doc, '2A. Access setup example', 1)
    para(doc, 'Use this example when creating the first test users. The user must be linked to an employee, and the employee must be linked to the correct department and department manager.')
    add_table(doc, ['Record', 'Example value', 'Why it matters'], [
        ['Company', 'KEP Engineering Services Pvt. Ltd.', 'Controls company scope and currency.'],
        ['Department', 'Management', 'The manager rule uses this department.'],
        ['Department Manager', 'Akhil Office', 'Set as the Manager on the Management department.'],
        ['Department Employee', 'Akhil Test', 'Set Department = Management and Manager = Akhil Office.'],
        ['Employee User', 'Akhil Test User', 'Set the Related User on the employee record.'],
        ['Manager User', 'Akhil Office User', 'Set the Related User on the manager employee record.'],
    ], [2200, 3100, 4160])
    heading(doc, 'Assign an Employee role', 2)
    for step in [
        'Open Settings -> Users & Companies -> Users and open the employee user.',
        'In the HR Access section, select HR Access: Employee. Do not select Department Manager, HR Officer, HR Manager or CEO unless required.',
        'Confirm the user is linked to the correct employee record and that the employee has a company.',
        'Log out and log in again so the new groups and menus are loaded.',
        'Test Employees -> Attendances and Time Off. The user should see own permitted records only.',
    ]:
        number(doc, step)
    heading(doc, 'Assign a Department Manager role', 2)
    for step in [
        'Open the manager user in Settings -> Users & Companies -> Users.',
        'Select HR Access: Department Manager. This group includes the employee and HR user base access needed for the manager workflow.',
        'Open Employees -> Departments -> Management and set Manager = Akhil Office.',
        'Open Akhil Test employee and set Department = Management and Related User = the employee login.',
        'Log in as the manager and test a Management employee plus an employee from another department. Only Management records should be available.',
    ]:
        number(doc, step)
    callout(doc, 'Access example', 'Akhil Test can submit a leave request for himself. Akhil Office can approve or reject Akhil Test because Akhil Test belongs to Management and Management is managed by Akhil Office. Akhil Office must not approve an Operations employee request.', LIGHT_BLUE)

    heading(doc, '2B. Complete leave example', 1)
    para(doc, 'This example shows the complete employee-to-manager process. Use a one-day Casual Leave request for 10 September 2026 in the QA database.')
    add_table(doc, ['Stage', 'Login / menu', 'Action', 'Expected result'], [
        ['1. Policy setup', 'HR -> Time Off -> Leave Policies', 'Create or verify Casual Leave policy and the employee category line.', 'The employee has a matching policy and balance.'],
        ['2. Allocation', 'HR -> Time Off -> Allocations', 'Allocate one or more days to Akhil Test, or run the configured policy allocation.', 'Available balance is visible to the employee.'],
        ['3. Apply', 'Akhil Test -> Time Off -> My Time Off -> New', 'Select Casual Leave, From 10 Sep, To 10 Sep, add a reason, then click Submit Request.', 'Request changes from Draft to To Approve.'],
        ['4. Manager review', 'Akhil Office -> Time Off -> Requests to Approve', 'Open the request, check employee, department, dates and balance.', 'Only the Management request is visible.'],
        ['5A. Approve', 'Manager request form', 'Click Approve.', 'Status becomes Approved and balance is reduced.'],
        ['5B. Reject', 'Manager request form', 'Click Refuse/Reject and enter a note if available.', 'Status becomes Refused/Rejected and balance is not consumed.'],
        ['6. Employee check', 'Akhil Test -> My Time Off', 'Reopen the request and review status and remaining balance.', 'Employee sees the final status but cannot approve it.'],
    ], [1700, 2850, 3000, 1810])
    callout(doc, 'Leave rule', 'Do not approve the same request from two browser tabs. After approval or rejection, refresh the list and verify the status once. For a new test, create a new date/request rather than reusing an approved record.', GOLD)

    heading(doc, '2D. Complete employee lifecycle', 1)
    para(doc, 'Use this sequence from the first staffing request through employee separation. Each stage creates information used by the next stage. Do not create a second employee record when the applicant becomes an employee.')
    add_table(doc, ['Stage', 'Responsible role', 'UI operation', 'Output used by next stage'], [
        ['1. Workforce need', 'Department Manager / HR', 'Manpower -> Requisitions -> New. Enter department, category, headcount, designation, qualification and justification. Submit for approval.', 'Approved headcount and job requirement.'],
        ['2. Requisition approval', 'HR / authorized approver', 'Open the submitted requisition. Review shortfall and lines. Approve, partially approve or reject.', 'Approved requisition and job-position planning.'],
        ['3. Recruitment', 'Recruiter / HR', 'Create or open the job position and applicants. Record applicant details, qualification, source and interview stages.', 'Selected applicant ready for hiring.'],
        ['4. Hire employee', 'HR', 'From the selected applicant, create the employee. Open Employees -> Employees and complete the employee master form.', 'One employee master record with user, department and category.'],
        ['5. Onboarding', 'HR / Department Manager', 'Employees -> Onboarding -> New. Select employee and template. Complete tasks, documents and progress.', 'Completed joining checklist and evidence.'],
        ['6. Work setup', 'HR / Manager', 'Set work location, manager, shift, ZK device ID, payroll profile, leave policy, grade, cost centre and notice period.', 'Employee ready for attendance, leave and payroll.'],
        ['7. Daily operation', 'Employee / Manager / HR', 'Employee checks attendance and requests leave. Manager reviews department requests. HR monitors payroll and compliance.', 'Attendance, leave, overtime and payslip records.'],
        ['8. Separation', 'Employee / Manager / HR', 'Create resignation. Confirm notice period, approve request, complete handover, clearances, settlement inputs, interview and documents.', 'Completed offboarding record and inactive employee when effective.'],
    ], [1700, 2100, 4000, 1560])
    heading(doc, 'Recruitment to employee conversion example', 2)
    for step in [
        'HR approves a Management requisition for one Office Staff position.',
        'Recruiter creates the job position and applicant record, then records interview and selection information.',
        'HR converts the selected applicant into one employee record. Verify the employee name is not duplicated.',
        'HR assigns the employee to Management, sets the department manager, and selects Computer Worker With ESI or Computer Worker Without ESI.',
        'HR enters joining date, probation end date, grade/band, cost centre, work location, payroll profile, leave policy and notice period.',
        'HR creates onboarding from the appropriate template and completes the joining checklist.',
        'The employee signs in and checks attendance, requests leave and views the own payslip when available.',
        'At separation, the employee submits resignation. The manager approves it and HR completes every offboarding section before closing the lifecycle.',
    ]:
        number(doc, step)
    callout(doc, 'Lifecycle control', 'The employee master is the central record. Department, manager, category, joining date, notice period, payroll profile and leave policy should be maintained there and reused by downstream workflows.', LIGHT_BLUE)

    heading(doc, '2C. Approval examples by module', 1)
    add_table(doc, ['Request type', 'Employee/requester does', 'Department Manager does', 'HR does'], [
        ['Leave', 'Creates request and submits.', 'Approves or rejects department request.', 'Allocates balance and handles company-wide exceptions.'],
        ['Attendance Regularization', 'Enters date, missing punch, reason and submits.', 'Checks evidence and approves/rejects department request.', 'Handles all departments and corrections.'],
        ['Overtime', 'Creates overtime request if permitted.', 'Reviews hours and approves/rejects department request.', 'Reviews policy/payroll impact and company-wide requests.'],
        ['Manpower', 'Requester enters headcount and justification.', 'Reviews department need and submits/approves according to assigned rights.', 'Approves, partially approves, rejects and creates job planning records.'],
        ['Resignation', 'Enters last day and reason, then confirms.', 'Reviews and approves/rejects department resignation.', 'Completes clearance, settlement, documents and final offboarding.'],
    ], [2100, 2460, 2460, 2340])

    heading(doc, '3. Initial setup', 1)
    for step in [
        'Install the required custom modules and restart Odoo after installation.',
        'Update the Apps list and verify the custom modules are installed.',
        'Create users and assign only the required HR Access groups.',
        'Create departments and assign one manager to each department.',
        'Create employees and assign department, manager, category, joining date, work location and employee user.',
        'For biometric employees, set a unique ZK Device User ID and verify the company.',
        'Configure leave policies and payroll profiles for Manufacturing Worker, Computer Worker With ESI, and Computer Worker Without ESI.',
        'Configure shift templates and assignments where shifts are used.',
        'Run one end-to-end test in a non-production database before entering live records.',
    ]:
        number(doc, step)
    callout(doc, 'Upgrade reminder', 'After Python or XML changes, restart Odoo and upgrade the affected module. If Odoo reports an UndefinedColumn error, the module upgrade did not complete.')

    module_section(doc, '4. Employee Master Data', 'The employee form stores common personal, statutory, employment, attendance, leave and payroll information. HR should maintain one employee record as the source of truth.', 'Employees -> Employees -> employee form', 'HR', [
        'Enter identity, personal, emergency, statutory, bank and nominee details.',
        'On the Work page, enter department, job position, manager, work location, category and additional employment details.',
        'Enter grade/band, confirmation date, status, notice period, cost centre and joining source.',
        'For manufacturing workers, enter machine/production line, contractor code, safety certification and PPE issue log when applicable.',
        'Use Education, Skills, Certifications and Documents for qualifications and supporting records.',
        'Save the employee and reopen the form to confirm the values persist.',
    ], [
        'Work Location is used for workplace/workstation context; do not create a duplicate workstation field.',
        'Notice Period (Days) is the single source for contract and resignation calculations.',
        'Employees must not receive access errors when viewing their own permitted information.',
        'HR can view and edit HR-only fields; employees see only fields allowed by their role.',
    ])

    module_section(doc, '5. Attendance and ZK biometric', 'Attendance receives check-in/check-out records and presents dashboard, history, late check-in and reporting views.', 'Attendances -> Dashboard or Attendances', 'Attendance Officer / HR', [
        'Set the employee ZK Device User ID before synchronizing users.',
        'Synchronize or import device attendance records.',
        'For an employee test, check in and check out once and confirm the timestamps.',
        'Open Dashboard and select Department, Employee, Month and Year filters.',
        'Use the manager login to confirm only the manager department is shown.',
        'Use the employee login to confirm only the employee own attendance history is shown.',
        'Use Late Check-in and download the Excel report when a report is required.',
    ], [
        'Employee can read own check-in/check-out but cannot edit attendance.',
        'Department Manager sees only employees in the manager department.',
        'HR or Attendance Officer sees the company-wide attendance scope.',
        'Dashboard, Attendances, Late Check-in and Regularization are kept under one Attendance section.',
        'There is only one visible top-level Attendance menu.',
    ], 'The barcode null-target error was guarded in the barcode service. If it returns, collect the browser console error and the scanned page/action.')

    module_section(doc, '6. Attendance Regularization', 'Employees request correction for missing punches or incorrect attendance. The manager or HR approves or rejects the request.', 'Attendances -> Attendance Regularization', 'Employee submits; Manager/HR approves', [
        'Employee creates a request, selects the date and request type, enters check-in/check-out and reason, then submits.',
        'Department Manager opens requests for the department and checks the evidence.',
        'Manager clicks Approve or Reject. HR can process company-wide requests according to access.',
        'Verify approval updates the correct attendance date and rejection does not create a correction.',
    ], [
        'Employee cannot see Approve, Reject or Revoke actions.',
        'Manager cannot approve a request from another department.',
        'Duplicate requests for the same employee/date are prevented or clearly reported.',
        'The original biometric record is not duplicated.',
    ])

    module_section(doc, '7. Leave Policy and Time Off', 'Leave is assigned by employee category and policy. Probation employees receive the configured probation entitlement, and balances are maintained by policy.', 'Time Off -> My Time Off / Allocations / Leave Policies', 'HR configures; Employee requests; Manager approves', [
        'Create or verify policy lines for Manufacturing Worker and Computer/Office Staff.',
        'Assign the correct leave policy to the employee or allow the category-based default.',
        'Set joining date and probation end date. Verify the six-month probation date where configured.',
        'Generate or import yearly allocations and review the employee balance.',
        'Employee submits leave. Department Manager approves or rejects the request.',
        'Verify the available balance, validity date, probation eligibility and carry-forward behavior.',
    ], [
        'Employee can request leave but cannot allocate leave or administer policy.',
        'Manager approves only requests in the manager department.',
        'HR can allocate and reset balances.',
        'Leave validity and probation end date are shown without exposing protected contract fields.',
    ], 'If an employee sees an Access Error for probation or contract fields, check field groups and upgrade the relevant custom module.')

    module_section(doc, '8. Shift Roster', 'Shift templates and assignments generate employee roster lines for attendance calculations and planning.', 'Attendances -> Shift Roster / Shift Templates', 'Department Manager / HR', [
        'Create a shift template with code, start time, end time, break, grace and overtime settings.',
        'Create a roster for department/category and date range.',
        'Generate roster lines, review employee assignments and weekly offs, then confirm the roster.',
        'Verify attendance and late calculations use the expected working hours.',
        'Reset or cancel only when the role and workflow permit it.',
    ], [
        'Roster lines contain the correct employee, date, shift and department.',
        'Managers cannot change another department roster.',
        'Weekly off and public holiday behavior is correct.',
        'Generated lines do not duplicate when the action is run twice.',
    ])

    module_section(doc, '9. Payroll', 'Payroll profiles configure category-based salary components and deductions. Payslips consume salary rules and approved overtime inputs.', 'Payroll -> Payroll Profiles / Payslips', 'Payroll / HR', [
        'Create or verify profiles for Manufacturing Worker, Computer Worker With ESI and Computer Worker Without ESI.',
        'Set basic mode, basic percentage, HRA percentage, allowance values, PF and ESI rates, and overtime multiplier.',
        'Assign the payroll profile to the employee and verify the employee Payroll section.',
        'Create the employee contract/payroll record and select the appropriate structure.',
        'Create a payslip, compute it, and review Basic, allowances, PF, ESI, overtime and net pay.',
        'Use approved overtime requests only; do not count the same hours again as manual overtime.',
    ], [
        'Basic, HRA, allowances, PF and ESI fields are present and readable by Payroll/HR.',
        'PF and ESI deductions appear only when the applicable flag is enabled.',
        'Approved overtime input is included once.',
        'Employee can view/download own payslip only.',
    ], 'Current implementation uses configured values and rules. Automatic HRA formulas, PF/ESI ceilings, complete PT/TDS rules, and manufacturing 2x gross-per-day overtime still require dedicated rule implementation if required by policy.')

    module_section(doc, '10. Onboarding', 'Onboarding templates create checklists and progress tracking for new employees.', 'Employees -> Onboarding', 'HR / Department Manager', [
        'Create a template with ordered onboarding steps and responsible users.',
        'Create onboarding for the employee and select the template.',
        'Complete checklist lines, attach documents and add notes.',
        'Review progress and close the onboarding when all required tasks are complete.',
    ], [
        'Employee and template are linked correctly.',
        'Checklist order and progress are correct.',
        'Attachments and notes are visible to authorized HR users.',
        'Employees cannot administer onboarding templates unless explicitly authorized.',
    ])

    module_section(doc, '11. Manpower Requisition', 'Manpower requisitions support department staffing requests, approval, partial approval and job-position planning.', 'Manpower -> Requisitions', 'Requester submits; HR/Manager approves', [
        'Requester creates a requisition with department, category, headcount, designation, qualification and justification.',
        'Submit the requisition for approval.',
        'Approver verifies requested headcount, shortfall and requisition lines.',
        'Approve, partially approve, reject or reset according to the workflow.',
        'Verify linked job-position creation or update after approval.',
    ], [
        'Employee users do not see the Manpower menu.',
        'Requester sees only requests permitted by the access rules.',
        'Approver can process submitted requests but not unrelated confidential data.',
        'Partial approval values and status are preserved.',
    ])

    module_section(doc, '12. Resignation and Offboarding', 'The resignation process records notice period, approval, handover, clearances, settlement inputs, exit interview, documents and PF/ESI transfer.', 'Employees -> Resignation -> Resignation Request', 'Employee submits; Manager/HR approves; HR coordinates exit', [
        'Employee creates a resignation request, enters requested last working day and reason, then confirms it.',
        'The notice period is read from Employee Form -> Additional Employment Details -> Notice Period (Days).',
        'Confirm that the Contract Notice Period and Resignation Notice Period show the same value.',
        'Department Manager reviews and approves or rejects the request.',
        'HR completes Knowledge Transfer and selects the handover employee.',
        'Complete Department, Stores/PPE, Admin/Asset, HR, Finance and Contractor clearances as applicable.',
        'Enter Full & Final settlement values and mark the settlement status.',
        'Complete the exit interview and feedback.',
        'Mark relieving, experience, service and trade-skill certificates when issued.',
        'Record PF/ESI transfer assistance and notes.',
        'After approval and the effective last day, verify the employee status and user deactivation behavior.',
    ], [
        'Employee can submit own resignation without contract-field Access Error.',
        'Manager can approve only the department employee request.',
        'HR can complete all offboarding sections.',
        'A 90-day employee notice value appears consistently in Employee, Contract and Resignation.',
        'Manufacturing workers can record PPE, stores and trade-skill clearance.',
        'Computer workers can record asset return, project handover and service certificate.',
    ], 'The new module stores offboarding data and tracks completion status. Automatic gratuity, leave encashment and final settlement calculations are not yet implemented.')

    heading(doc, '13. Daily UI operation guide', 1)
    para(doc, 'Use the application switcher grid to open an app. Use the purple top navigation for the main area and the list view New button to create records. A gear icon opens configuration or technical options only for authorized users.')
    add_table(doc, ['Task', 'UI path', 'Operation / expected action'], [
        ['Open employee', 'Employees -> Employees', 'Search the employee, open the row, edit fields, then click Save. Use Work, Personal, Resume and Payroll pages.'],
        ['Record employee notice', 'Employee form -> Work -> Additional Employment Details', 'Enter Notice Period (Days). This value flows to Contract and Resignation.'],
        ['Check attendance', 'Attendances -> Dashboard', 'Choose Department, Employee, Month and Year. Review Present, Absent, Leave and Late totals.'],
        ['Read punch history', 'Attendances -> Attendances', 'Open an employee attendance row and read Check In, Check Out, Worked Hours and Overtime.'],
        ['Submit regularization', 'Attendances -> Attendance Regularization -> New', 'Select date and request type, enter times and reason, then click Submit.'],
        ['Approve regularization', 'Attendances -> Attendance Regularization', 'Open a submitted request and click Approve or Reject.'],
        ['Request leave', 'Time Off -> My Time Off -> New', 'Select leave type and dates, enter description, then click Submit Request.'],
        ['Approve leave', 'Time Off -> Requests to Approve', 'Open the request, check balance and dates, then click Approve or Refuse.'],
        ['Create payslip', 'Payroll -> Payslips -> New', 'Select employee and period, verify contract and structure, click Compute Sheet, review lines, then confirm.'],
        ['Create onboarding', 'Employees -> Onboarding -> New', 'Select employee and template, complete checklist items, attach evidence and update progress.'],
        ['Create manpower request', 'Manpower -> Requisitions -> New', 'Enter department, category, headcount, requisition lines and justification, then Submit.'],
        ['Submit resignation', 'Employees -> Resignation -> Resignation Request -> New', 'Select employee, enter requested last day and reason, check notice period, then Confirm.'],
        ['Complete offboarding', 'Resignation form -> offboarding sections', 'Update handover, clearance, settlement, interview, documents and PF/ESI statuses, then Save.'],
    ], [2100, 3200, 4060])
    heading(doc, 'Button and status guide', 2)
    add_table(doc, ['Button / status', 'Meaning', 'Who normally uses it'], [
        ['New', 'Creates a new record.', 'Employee, Manager or HR according to menu access'],
        ['Save', 'Stores entered changes.', 'The user who has write access'],
        ['Submit / Confirm', 'Moves a request from draft to the approval queue.', 'Employee or requester'],
        ['Approve', 'Accepts the request and applies the workflow result.', 'Department Manager or HR'],
        ['Reject / Refuse', 'Declines the request.', 'Department Manager or HR'],
        ['Reset to Draft', 'Returns an eligible record to draft for correction.', 'HR Manager or authorized approver'],
        ['Compute Sheet', 'Calculates payslip salary rules and totals.', 'Payroll / HR'],
        ['Generate', 'Creates roster lines, allocations or checklist records.', 'HR or Manager'],
    ], [2200, 4300, 2860])
    callout(doc, 'UI rule', 'If a menu, button or field is missing, first verify the user role and module upgrade. Do not give Administrator access as a workaround for a normal role.', RED)

    heading(doc, '14. New user quick reference', 1)
    add_table(doc, ['If you need to...', 'Open this menu', 'Then do this'], [
        ['View your punch time', 'Attendances -> Attendances', 'Search your name and read Check In and Check Out.'],
        ['Request a missed punch correction', 'Attendances -> Attendance Regularization', 'Click New, enter the date, times and reason, then Submit.'],
        ['Request leave', 'Time Off -> My Time Off', 'Click New, select leave type and dates, then Submit Request.'],
        ['Approve your department request', 'Relevant Requests to Approve menu', 'Open the submitted record and click Approve or Reject.'],
        ['Review attendance totals', 'Attendances -> Dashboard', 'Select department, employee, month and year filters.'],
        ['View a payslip', 'Payroll -> Payslips', 'Open your payslip and use the print/download option if permitted.'],
        ['Submit resignation', 'Employees -> Resignation -> Resignation Request', 'Click New, enter requested last day and reason, then Confirm.'],
        ['Complete an employee exit', 'Resignation record', 'Update each offboarding section and Save after each review.'],
    ], [2900, 3000, 3560])
    callout(doc, 'Learning tip', 'New users should complete one supervised test for their role: employee request, manager approval, and HR review. This demonstrates the full handoff without changing live records.', LIGHT_BLUE)

    heading(doc, '15. Resignation offboarding field guide', 1)
    add_table(doc, ['Section', 'What HR enters', 'Manufacturing worker focus', 'Computer/office focus'], [
        ['Knowledge Transfer', 'Status, handover employee, notes', 'SOP, machine and responsibility transfer', 'Project, documentation and client transition'],
        ['Exit Clearance', 'Department, Stores/PPE, Admin/Asset, HR, Finance, Contractor', 'PPE, tools, stores and contractor clearance', 'Laptop, access cards, assets and admin clearance'],
        ['Full & Final', 'Status, leave encashment, gratuity, dues, ESOP clawback, notes', 'Leave, gratuity, dues and contractor settlement', 'Leave, gratuity, dues and ESOP where applicable'],
        ['Exit Interview', 'Completed flag and feedback', 'Safety, shift and working conditions', 'Management, growth, culture and work-life balance'],
        ['Documents', 'Issued flags', 'Relieving, experience and trade-skill certificate', 'Relieving, experience and service certificate'],
        ['PF / ESI', 'Status and notes', 'Online transfer assistance', 'Online transfer assistance'],
    ], [1900, 2700, 2380, 2380])

    heading(doc, '16. QA test execution', 1)
    para(doc, 'Create a test sheet with one account for each role. Use separate test employees in at least two departments so department filtering can be proven.')
    add_table(doc, ['Test', 'Action', 'Expected result'], [
        ['Employee attendance', 'Open Attendance and view history.', 'Own check-in/check-out only; read-only.'],
        ['Manager attendance', 'Open Dashboard and filter department.', 'Only manager department employees.'],
        ['Leave', 'Submit and approve leave.', 'Employee submits; manager/HR approves within scope.'],
        ['Payroll', 'Compute payslip.', 'Configured components and deductions appear once.'],
        ['Resignation', 'Submit, approve and complete offboarding.', 'Notice value is consistent and all sections save.'],
        ['Negative access', 'Employee opens approval action or another employee.', 'Access denied or action hidden.'],
        ['Menu audit', 'Open app switcher and Attendance menus.', 'One Attendance section; no technical XML IDs visible.'],
        ['Upgrade', 'Upgrade changed modules.', 'No ParseError, UndefinedColumn or missing-field error.'],
    ], [1700, 3900, 3760])
    callout(doc, 'Evidence standard', 'For each test record the login role, menu path, expected result, actual result, Pass/Fail, screenshot, and any server/browser error text.', LIGHT_GRAY)

    heading(doc, '17. Troubleshooting', 1)
    add_table(doc, ['Error / symptom', 'Likely cause', 'Action'], [
        ['UndefinedColumn: hr_employee.<field>', 'Python field loaded but module schema was not upgraded.', 'Restart Odoo and upgrade the module using the correct config and database.'],
        ['ParseError: string as selector', 'View XPath selects a translated string attribute.', 'Use a stable name/id/field selector and upgrade again.'],
        ['Access Error for contract_date_start/end or probation', 'Employee request reads protected contract fields.', 'Use the custom resignation module calculation and confirm it is upgraded.'],
        ['Two Attendance menus', 'Duplicate or orphaned root menu exists.', 'Upgrade access-control menus and verify parent/action in Technical -> Menu Items.'],
        ['Employee sees all attendance', 'Dashboard controller or record rule is not scoped.', 'Check department manager relation, employee user link and role assignment.'],
        ['Payslip component is zero', 'Profile value, structure rule or employee assignment is missing.', 'Check payroll profile, contract structure, rule inclusion and compute the sheet again.'],
        ['Application stops after 120 seconds', 'Long/idle HTTP request or blocked request thread.', 'Review stack trace and URL; stop the stale request, then investigate slow code/database query if repeated.'],
    ], [2600, 3300, 3460])

    heading(doc, '18. Current implementation boundaries', 1)
    para(doc, 'The following items are captured as fields or workflow inputs but are not fully automated calculations or external integrations: gratuity calculation, leave encashment amount calculation, dues recovery calculation, PF/ESI online transfer, certificate PDF generation, automatic PT/TDS rules in the custom payroll structure, PF/ESI ceiling enforcement, and manufacturing overtime at exactly two times gross daily salary.')
    callout(doc, 'Change control', 'Before adding a new field, check the standard Odoo employee/contract fields and installed custom modules. Reuse Work Location, Education, Skills, Certifications, Documents, Department and Manager fields instead of creating duplicates.', GOLD)

    heading(doc, '19. Module and file reference', 1)
    add_table(doc, ['Area', 'Module / key files'], [
        ['Access control', 'addons/dotbd_hr_access_control_suite/security and controllers'],
        ['Employee master data', 'addons/dotbd_hr_manpower_requisition_suite/models/hr_employee.py and views/hr_employee_views.xml'],
        ['Attendance', 'addons/dotbd_hr_zk_attendance_suite and addons/dotbd_hr_attendance_regularization_suite'],
        ['Leave policy', 'addons/dotbd_hr_leave_policy_suite'],
        ['Payroll', 'addons/dotbd_hr_payroll_suite and addons/hr_payroll_community'],
        ['Onboarding/manpower', 'addons/dotbd_hr_onboarding_suite and addons/dotbd_hr_manpower_requisition_suite'],
        ['Resignation offboarding', 'addons/dotbd_hr_resignation_offboarding_suite'],
    ], [2200, 7160])
    para(doc, 'End of SOP.')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == '__main__':
    build()
