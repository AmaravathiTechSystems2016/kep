{
    'name': 'DotBD CRM Lead Fields',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Configurable lead type, system, and capacity masters with inquiry dates',
    'depends': ['crm', 'base_import'],
    'data': [
        'security/ir.model.access.csv',
        'data/crm_lead_type_data.xml',
        'views/crm_lead_master_views.xml',
        'views/crm_lead_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
