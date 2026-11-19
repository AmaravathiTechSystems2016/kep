{
    'name': 'DotBD CRM Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'CRM analytics dashboard: pipeline, owners, engineers, systems, effluent parameters',
    'author': 'DotBD',
    'depends': ['crm', 'dotbd_crm_lead_suite', 'hrms_dashboard'],
    'data': [
        'views/crm_dashboard_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dotbd_crm_dashboard/static/src/css/crm_dashboard.css',
            'dotbd_crm_dashboard/static/src/js/crm_dashboard.js',
            'dotbd_crm_dashboard/static/src/js/hr_dashboard_tab.js',
            'dotbd_crm_dashboard/static/src/xml/crm_dashboard.xml',
            'dotbd_crm_dashboard/static/src/xml/hr_dashboard_tab.xml',
        ],
        'web.assets_tests': [
            'dotbd_crm_dashboard/static/tests/tours/*.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
