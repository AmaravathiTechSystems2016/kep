# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Shift Roster Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'sequence': 245,
    'summary': 'Shift templates, employee allocation, and shift roster planning',
    'description': """
Shift Roster Suite
==================

Separate shift management layer for manufacturing workers and office staff.

Features:
- Shift templates for General / A / B / custom shifts
- Employee or department based shift allocation
- Department-wise roster generation
- Weekly off support
- Ready for attendance integration
    """,
    'author': 'Dot BD Solutions Limited',
    'website': 'https://dotbdsolutions.com',
    'depends': [
        'mail',
        'hr',
        'hr_attendance',
        'dotbd_hr_zk_attendance_suite',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/shift_weekday_data.xml',
        'data/shift_roster_sequence.xml',
        'views/hr_shift_template_views.xml',
        'views/hr_shift_assignment_views.xml',
        'views/hr_shift_holiday_views.xml',
        'views/hr_shift_roster_views.xml',
        'views/hr_shift_roster_revision_views.xml',
        'views/hr_shift_roster_bulk_update_wizard_views.xml',
        'views/hr_shift_planning_dashboard_views.xml',
        'views/hr_employee_views.xml',
        'views/shift_roster_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}
