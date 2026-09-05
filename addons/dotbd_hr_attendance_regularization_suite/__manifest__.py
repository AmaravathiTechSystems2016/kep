# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Attendance Regularization Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'sequence': 246,
    'summary': 'Employee missed punch and attendance correction workflow',
    'description': """
Attendance Regularization Suite
===============================

Separate workflow for employees to request attendance corrections such as:
- missed check-in
- missed check-out
- both punches missing
- manual attendance corrections

Workflow:
1. Employee submits request
2. Manager reviews and approves/rejects
3. On approval, the module updates or creates hr.attendance
4. Audit trail remains in the request record
    """,
    'author': 'Dot BD Solutions Limited',
    'website': 'https://dotbdsolutions.com',
    'depends': [
        'mail',
        'hr_attendance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/attendance_regularization_security.xml',
        'data/ir_sequence.xml',
        'views/attendance_regularization_views.xml',
        'views/attendance_regularization_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
