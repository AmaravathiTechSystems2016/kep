# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AttendanceLeaveEncashment(models.Model):
    _name = 'attendance.leave.encashment'
    _description = 'Attendance Leave Encashment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'departure_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', tracking=True)
    company_id = fields.Many2one('res.company', required=True, tracking=True)
    policy_id = fields.Many2one('attendance.leave.policy', required=True, ondelete='cascade', tracking=True)
    policy_line_id = fields.Many2one('attendance.leave.policy.line', required=True, ondelete='cascade', tracking=True)
    leave_type_id = fields.Many2one('hr.leave.type', required=True, tracking=True)
    departure_date = fields.Date(required=True, tracking=True)
    encashment_days = fields.Float(required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True)
    notes = fields.Text()

    @api.depends('employee_id', 'departure_date', 'leave_type_id')
    def _compute_name(self):
        for record in self:
            if record.employee_id and record.leave_type_id and record.departure_date:
                record.name = f"{record.employee_id.name} - {record.leave_type_id.sudo().name} ({record.departure_date})"
            else:
                record.name = "Leave Encashment"

    def action_done(self):
        self.write({'state': 'done'})
        return True
