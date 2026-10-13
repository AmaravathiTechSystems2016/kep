
{
    'name': 'Performance Appraisal',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Manage employee performance appraisals',
    'description': """
        This module provides a structured Performance Appraisal system for employees in Odoo. 
        It allows administrators to assign multiple appraisers, distribute evaluation weights, 
        and manage a complete appraisal workflow with controlled finalization..
    """,
    'author': 'Musleh Uddin Juned',
    'website': 'http://www.zachai-bachhai.com',
    'depends': ['base', 'hr', 'mail'],
    'data': [
        'security/appraisal_security.xml',
        'security/ir.model.access.csv',
        'reports/report.xml',
        'reports/report_performance_appraisal.xml',
        'views/performance_appraisal_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
