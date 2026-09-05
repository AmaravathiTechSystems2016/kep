{
    'name': 'DotBD HR Onboarding Suite',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Separate HR onboarding workflow for joining, verification, and probation tracking',
    'depends': ['hr', 'mail', 'dotbd_hr_manpower_requisition_suite'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/onboarding_demo.xml',
        'data/onboarding_email_templates.xml',
        'views/hr_onboarding_template_views.xml',
        'views/hr_employee_onboarding_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_onboarding_menus.xml',
    ],
    'application': False,
    'license': 'LGPL-3',
}
