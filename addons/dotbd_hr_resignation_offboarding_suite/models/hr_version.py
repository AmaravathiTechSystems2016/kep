# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    notice_days = fields.Integer(
        string='Notice Period',
        compute='_compute_employee_notice_days',
        help='Notice period entered on the employee form, with the company setting as fallback.',
    )

    @api.depends('employee_id', 'employee_id.notice_period_days', 'company_id')
    def _compute_employee_notice_days(self):
        for contract in self:
            employee_notice = contract.employee_id.notice_period_days
            contract.notice_days = employee_notice or contract.company_id.contract_expiration_notice_period or 0
