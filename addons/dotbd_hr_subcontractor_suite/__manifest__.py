# -*- coding: utf-8 -*-
{
    'name': 'Dot BD HR Subcontractor Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Manage subcontractors and their assigned employees',
    'author': 'Dot BD Solutions Limited',
    'license': 'LGPL-3',
    'depends': ['hr', 'dotbd_hr_manpower_requisition_suite', 'dotbd_hr_access_control_suite'],
    'data': [
        'security/ir.model.access.csv',
        'security/hr_subcontractor_rules.xml',
        'data/ir_sequence_data.xml',
        'views/hr_subcontractor_views.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
