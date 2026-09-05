# -*- coding: utf-8 -*-
{
    'name': 'DotBD HR Manpower Requisition Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Manpower requisition and planning workflow for worker and office staffing',
    'description': """
Manpower Requisition Suite
===========================

This module manages manpower requisitions for both manufacturing workers and
computer/office staff. It provides a clean request, approval, and planning flow
with separate requisition lines, budget checks, and state-based processing.
""",
    'author': 'Dot BD Solutions Limited',
    'website': 'https://www.dotbd.com',
    'license': 'OPL-1',
    'depends': [
        'mail',
        'hr',
        'dotbd_hr_zk_attendance_suite',
        'hr_recruitment',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/manpower_dashboard_views.xml',
        'views/manpower_requisition_views.xml',
        'views/manpower_partial_approval_wizard_views.xml',
        'views/hr_applicant_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_job_views.xml',
        'views/hr_recruitment_stage_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
