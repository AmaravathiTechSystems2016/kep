# -*- coding: utf-8 -*-

from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    probation_end_date = fields.Date(
        string='Probation End Date',
        related='trial_date_end',
        readonly=False,
        help='Probation tracking date for confirmation purposes. Earned leave eligibility is based on service completion.',
    )
