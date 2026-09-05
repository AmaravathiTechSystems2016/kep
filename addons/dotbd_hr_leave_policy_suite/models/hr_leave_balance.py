# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AttendanceLeaveBalance(models.Model):
    _name = 'attendance.leave.balance'
    _description = 'Attendance Leave Balance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'balance_year desc, company_id, employee_id, leave_type_id'

    name = fields.Char(compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, ondelete='cascade')
    company_id = fields.Many2one(related='employee_id.company_id', store=True, readonly=True)
    attendance_category = fields.Selection([
        ('worker', 'Manufacturing Worker'),
        ('office', 'Computer / Office Staff'),
        ('other', 'Other'),
    ], compute='_compute_attendance_category', store=True, readonly=True)
    policy_id = fields.Many2one('attendance.leave.policy', required=True, tracking=True, ondelete='cascade')
    policy_line_id = fields.Many2one('attendance.leave.policy.line', required=True, tracking=True, ondelete='cascade')
    leave_type_id = fields.Many2one('hr.leave.type', required=True, tracking=True, ondelete='cascade')
    balance_year = fields.Integer(required=True, default=lambda self: fields.Date.today().year, tracking=True)
    opening_balance = fields.Float(tracking=True)
    accrued_leave = fields.Float(tracking=True)
    utilized_leave = fields.Float(tracking=True)
    closing_balance = fields.Float(tracking=True)

    _sql_constraints = [
        (
            'employee_policy_year_line_unique',
            'unique(employee_id, policy_id, policy_line_id, leave_type_id, balance_year)',
            'A leave balance record already exists for this employee, policy line, leave type, and year.',
        ),
    ]

    @api.depends('employee_id', 'leave_type_id', 'balance_year')
    def _compute_name(self):
        for record in self:
            if record.employee_id and record.leave_type_id and record.balance_year:
                record.name = f"{record.employee_id.name} - {record.leave_type_id.sudo().name} - {record.balance_year}"
            else:
                record.name = 'Leave Balance'

    @api.depends('employee_id')
    def _compute_attendance_category(self):
        for record in self:
            record.attendance_category = getattr(record.employee_id, 'attendance_category', False) or False

    @api.model
    def cron_refresh_leave_balances(self):
        policies = self.env['attendance.leave.policy'].sudo().search([('active', '=', True)])
        if policies:
            policies.action_refresh_leave_balances(year=fields.Date.today().year)
        return True
