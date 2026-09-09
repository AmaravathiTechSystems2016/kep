# -*- coding: utf-8 -*-
{
    'name': 'DotBD HR Leave Planner',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Plan and review employee leave on a shared calendar',
    'description': """
DotBD HR Leave Planner
======================

Provides a planning calendar over the existing Odoo leave requests. It does
not create duplicate leave records or change the existing approval workflow.
""",
    'author': 'Dot BD Solutions Limited',
    'website': 'https://www.dotbd.com',
    'license': 'LGPL-3',
    'depends': [
        'hr_holidays',
        'dotbd_hr_access_control_suite',
        'dotbd_hr_leave_policy_suite',
    ],
    'data': [
        'views/leave_planner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
