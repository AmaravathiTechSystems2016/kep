# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Payroll Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'sequence': 270,
    'summary': 'Custom payroll profiles and overtime payslip inputs',
    'description': """
Dot BD HR Payroll Suite
=======================

Custom payroll foundation for Dot BD HR modules.

Features:
- Payroll profiles by employee category
- Payroll configuration on employee form
- Overtime input integration for payslips
- Payroll structure template for worker and office staff
    """,
    'author': 'Dot BD Solutions Limited',
    'website': 'https://dotbdsolutions.com',
    'depends': [
        'base_setup',
        'hr',
        'hr_payroll_community',
        'dotbd_hr_zk_attendance_suite',
        'dotbd_hr_overtime_request_suite',
        'dotbd_hr_leave_policy_suite',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/payroll_data.xml',
        'views/payroll_profile_views.xml',
        'views/hr_employee_views.xml',
    ],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
