# -*- coding: utf-8 -*-
{
    'name': 'DotBD HR Leave Policy Suite',
    'version': '19.0.1.2.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Leave policy automation by employee category',
    'description': """
Leave Policy Automation Suite
=============================

This module keeps leave rules separate from attendance logic.
It helps HR define different leave policies for manufacturing workers
and office staff, then auto-assigns policies and generates yearly
leave allocations to reduce manual work.
""",
    'author': 'Dot BD Solutions Limited',
    'website': 'https://www.dotbd.com',
    'license': 'OPL-1',
    'depends': [
        'mail',
        'hr_holidays',
        'dotbd_hr_zk_attendance_suite',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/leave_policy_demo.xml',
        'data/ir_cron.xml',
        'views/leave_policy_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_leave_views.xml',
        'views/hr_leave_type_views.xml',
        'views/hr_leave_allocation_views.xml',
        'views/hr_leave_encashment_views.xml',
        'views/hr_leave_balance_views.xml',
        'views/hr_leave_balance_import_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
