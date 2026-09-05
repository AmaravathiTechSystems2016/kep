# -*- coding: utf-8 -*-

from odoo import fields, models


class HrRecruitmentStage(models.Model):
    _inherit = 'hr.recruitment.stage'

    attendance_category = fields.Selection(
        [
            ('common', 'Common'),
            ('worker', 'Manufacturing Worker'),
            ('office', 'Office Staff'),
            ('other', 'Other'),
        ],
        string='Employee Category',
        default='common',
        help='Stages will be shown only for jobs and applicants matching this employee category. Common stages are shared by all categories.',
    )
