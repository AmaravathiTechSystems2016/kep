# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    attendance_category = fields.Selection(
        [
            ('worker', 'Manufacturing Worker'),
            ('office', 'Computer / Office Staff'),
            ('other', 'Other'),
        ],
        string='Attendance Category',
        default='other',
        tracking=True,
        help='Use this field to separate workers and office staff for leave policy rules.',
    )
    leave_policy_id = fields.Many2one(
        'attendance.leave.policy',
        string='Leave Policy',
        tracking=True,
        help='Policy used to auto-create yearly leave allocations for this employee.',
    )
    leave_allocation_count = fields.Integer(
        string='Leave Allocations',
        compute='_compute_leave_allocation_count',
    )
    leave_balance_count = fields.Integer(
        string='Leave Balances',
        compute='_compute_leave_balance_count',
    )
    def _compute_leave_allocation_count(self):
        Allocation = self.env['hr.leave.allocation'].sudo()
        for employee in self:
            employee.leave_allocation_count = Allocation.search_count([
                ('employee_id', '=', employee.id),
                ('leave_policy_id', '=', employee.leave_policy_id.id),
            ]) if employee.leave_policy_id else 0

    def _compute_leave_balance_count(self):
        Balance = self.env['attendance.leave.balance'].sudo()
        for employee in self:
            employee.leave_balance_count = Balance.search_count([
                ('employee_id', '=', employee.id),
            ])

    def _get_default_probation_end_date(self):
        """Return the probation end date derived from the joining date."""
        self.ensure_one()
        joining_date = self.joining_date or self.contract_date_start
        if not joining_date and 'joining_date' in self._fields:
            joining_date = self.joining_date
        if not joining_date:
            return False
        return joining_date + relativedelta(months=6)

    def _sync_probation_end_date(self):
        """Populate trial_date_end from joining date when it is missing."""
        for employee in self:
            if employee.trial_date_end:
                continue
            probation_end_date = employee._get_default_probation_end_date()
            if probation_end_date:
                employee.trial_date_end = probation_end_date

    @api.onchange('joining_date', 'contract_date_start')
    def _onchange_probation_end_date(self):
        for employee in self:
            if employee.trial_date_end:
                continue
            probation_end_date = employee._get_default_probation_end_date()
            if probation_end_date:
                employee.probation_end_date = probation_end_date

    def _suggest_leave_policy(self, company_id=None, attendance_category=None):
        company_id = company_id or self.company_id.id
        attendance_category = attendance_category or self.attendance_category
        if not company_id or not attendance_category:
            return False
        return self.env['attendance.leave.policy'].sudo().search([
            ('company_id', '=', company_id),
            ('attendance_category', '=', attendance_category),
            ('active', '=', True),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('leave_policy_id'):
                policy = self.env['attendance.leave.policy'].sudo().search([
                    ('company_id', '=', vals.get('company_id', self.env.company.id)),
                    ('attendance_category', '=', vals.get('attendance_category', 'other')),
                    ('active', '=', True),
                ], limit=1)
                if policy:
                    vals['leave_policy_id'] = policy.id
        records = super().create(vals_list)
        records._sync_probation_end_date()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._sync_probation_end_date()
        if 'leave_policy_id' not in vals and ('company_id' in vals or 'attendance_category' in vals):
            for employee in self:
                policy = employee._suggest_leave_policy()
                if employee.leave_policy_id != policy:
                    employee.leave_policy_id = policy.id if policy else False
        return res

    def _register_hook(self):
        res = super()._register_hook()
        employees = self.sudo().search([
            ('trial_date_end', '=', False),
            '|',
            ('joining_date', '!=', False),
            ('contract_date_start', '!=', False),
        ])
        employees._sync_probation_end_date()
        return res

    def action_open_leave_policy(self):
        self.ensure_one()
        if not self.leave_policy_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leave Policy',
            'res_model': 'attendance.leave.policy',
            'view_mode': 'form',
            'res_id': self.leave_policy_id.id,
            'target': 'current',
        }

    def action_open_leave_allocations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leave Allocations',
            'res_model': 'hr.leave.allocation',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_leave_policy_id': self.leave_policy_id.id if self.leave_policy_id else False,
            },
            'target': 'current',
        }

    def action_open_leave_balances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leave Balances',
            'res_model': 'attendance.leave.balance',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_policy_id': self.leave_policy_id.id if self.leave_policy_id else False,
            },
            'target': 'current',
        }

    def action_generate_employee_leave_allocations(self):
        self.ensure_one()
        if not self.leave_policy_id:
            return False
        return self.leave_policy_id.sudo().action_generate_yearly_allocations_for_employee(self.sudo())

    def action_reset_employee_leave_allocations(self):
        self.ensure_one()
        if not self.leave_policy_id:
            return False
        return self.leave_policy_id.sudo().action_reset_generated_allocations_for_employee(self.sudo())

    def action_open_leave_balance_import(self):
        employees = self or self.env['hr.employee'].browse(self.env.context.get('active_ids', []))
        employees = employees.exists()
        if not employees and self.env.context.get('active_id'):
            employees = self.env['hr.employee'].browse(self.env.context['active_id']).exists()
        if not employees:
            employees = self
        active_year = fields.Date.today().year
        company_id = employees[:1].company_id.id if employees else self.env.company.id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Old Balances',
            'res_model': 'attendance.leave.balance.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': company_id,
                'default_balance_year': active_year,
                'default_employee_ids': [(6, 0, employees.ids)],
            },
        }
