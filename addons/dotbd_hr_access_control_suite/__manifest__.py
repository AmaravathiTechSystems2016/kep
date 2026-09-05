# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Access Control Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Role and department-based access for HR workflows',
    'description': """
Dot BD HR Access Control Suite
==============================

Centralized access groups and department-based record rules for employees,
attendance, leave, overtime, shifts, payroll, and offboarding.
    """,
    'author': 'Dot BD Solutions Limited',
    'depends': [
        'hr',
        'hr_attendance',
        'hr_holidays',
        'hr_payroll_community',
        'hr_resignation',
        'dotbd_hr_zk_attendance_suite',
        'dotbd_hr_attendance_regularization_suite',
        'dotbd_hr_overtime_request_suite',
        'dotbd_hr_shift_roster_suite',
        'dotbd_hr_leave_policy_suite',
        'dotbd_hr_onboarding_suite',
    ],
    'data': [
        'security/hr_access_groups.xml',
        'security/hr_access_allocation.xml',
        'security/ir.model.access.csv',
        'security/hr_access_rules.xml',
        'security/hr_access_menus.xml',
        'views/hr_access_regularization_views.xml',
    ],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
