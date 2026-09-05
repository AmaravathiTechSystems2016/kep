# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#
################################################################################
from odoo import api, fields, models, SUPERUSER_ID


class HrPayslip(models.Model):
    """Inherit hr.payslip to add late check-in deduction functionality"""
    _inherit = 'hr.payslip'

    late_check_in_ids = fields.Many2many(
        'late.check.in',
        string='Late Check-in',
        help='Late check-in records of the employee',
        compute='_compute_late_check_in_ids',
        readonly=True,
    )

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        """Write late check-in records into the payslip inputs."""
        res = super().get_inputs(contracts, date_from, date_to)

        try:
            late_check_in_type = self.env.ref(
                'dotbd_hr_zk_attendance_suite.late_check_in_salary_rule')
        except (ValueError, Exception):
            return res

        for contract in contracts:
            if not contract.employee_id:
                continue
            late_check_in_id = self.env['late.check.in'].sudo().search([
                ('employee_id', '=', contract.employee_id.id),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('state', '=', 'approved'),
            ])

            if late_check_in_id:
                res.append({
                    'name': late_check_in_type.name,
                    'code': late_check_in_type.code,
                    'amount': sum(late_check_in_id.mapped('penalty_amount')),
                    'contract_id': contract.id,
                })
        return res

    def _compute_late_check_in_ids(self):
        """Link approved late check-ins for the current payslip period."""
        LateCheckIn = self.env['late.check.in'].sudo()
        for slip in self:
            if slip.employee_id and slip.date_from and slip.date_to:
                slip.late_check_in_ids = LateCheckIn.search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date', '>=', slip.date_from),
                    ('date', '<=', slip.date_to),
                    ('state', '=', 'approved'),
                ])
            else:
                slip.late_check_in_ids = False

    def action_payslip_done(self):
        """Mark deducted late check-in records."""
        for rec in self.late_check_in_ids:
            rec.write({'state': 'deducted'})
        return super().action_payslip_done()
