# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Resignation Offboarding Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Handover, clearance, settlement, exit interview, and exit documents',
    'author': 'Dot BD Solutions Limited',
    'license': 'LGPL-3',
    'depends': [
        'hr_resignation',
        'hr_employee_updation',
        'dotbd_hr_access_control_suite',
        'dotbd_hr_zk_attendance_suite',
        'dotbd_hr_manpower_requisition_suite',
    ],
    'data': [
        'views/hr_resignation_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
