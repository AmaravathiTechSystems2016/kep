# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    dotbd_overtime_request_ids = fields.Many2many(
        'hr.overtime.request',
        string='Approved Overtime Requests',
        compute='_compute_dotbd_overtime_request_ids',
        readonly=True,
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_dotbd_overtime_request_ids(self):
        Overtime = self.env['hr.overtime.request'].sudo()
        for slip in self:
            if slip.employee_id and slip.date_from and slip.date_to:
                slip.dotbd_overtime_request_ids = Overtime.search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('overtime_date', '>=', slip.date_from),
                    ('overtime_date', '<=', slip.date_to),
                    ('state', '=', 'approved'),
                ])
            else:
                slip.dotbd_overtime_request_ids = False

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = super().get_inputs(contracts, date_from, date_to)
        try:
            overtime_rule = self.env.ref('dotbd_hr_payroll_suite.dotbd_overtime_salary_rule')
        except (ValueError, Exception):
            return res

        for contract in contracts:
            employee = getattr(contract, 'employee_id', False)
            if not employee:
                continue
            overtime_requests = self.env['hr.overtime.request'].sudo().search([
                ('employee_id', '=', employee.id),
                ('overtime_date', '>=', date_from),
                ('overtime_date', '<=', date_to),
                ('state', '=', 'approved'),
            ])
            if overtime_requests:
                res.append({
                    'name': overtime_rule.name,
                    'code': overtime_rule.code,
                    'amount': sum(overtime_requests.mapped('approved_hours')) or 0.0,
                    'contract_id': contract.id,
                })
        return res
