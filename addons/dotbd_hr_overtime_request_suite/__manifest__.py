# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Overtime Request Suite',
    'version': '19.0.1.0.1',
    'category': 'Human Resources/Attendances',
    'sequence': 260,
    'summary': 'Manual overtime request and approval workflow',
    'description': """
Manual Overtime Request Suite
=============================

Separate manual overtime request flow for employees, workers, and office staff.
This module keeps human-approved overtime requests apart from ZK/attendance
auto overtime calculations.

Features:
- Manual overtime request form
- Submit / approve / reject workflow
- Duplicate request protection
- Separate from automatic ZK overtime calculation
    """,
    'author': 'Dot BD Solutions Limited',
    'website': 'https://dotbdsolutions.com',
    'depends': [
        'mail',
        'hr',
        'hr_attendance',
        'dotbd_hr_shift_roster_suite',
        'hr_payroll_community',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/hr_overtime_request_views.xml',
        'views/hr_overtime_request_menus.xml',
    ],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
