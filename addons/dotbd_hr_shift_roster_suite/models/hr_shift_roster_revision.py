# -*- coding: utf-8 -*-

from odoo import fields, models


class HrShiftRosterRevision(models.Model):
    _name = 'hr.shift.roster.revision'
    _description = 'Shift Roster Revision'
    _order = 'create_date desc, id desc'

    roster_id = fields.Many2one('hr.shift.roster', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='roster_id.company_id', store=True, readonly=True)
    action_type = fields.Selection([
        ('generated', 'Generated'),
        ('rebuilt', 'Rebuilt'),
        ('bulk_update', 'Bulk Update'),
        ('manual', 'Manual Change'),
    ], required=True, default='manual')
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    note = fields.Char()
    line_count = fields.Integer(readonly=True)
    revision_line_ids = fields.One2many(
        'hr.shift.roster.revision.line', 'revision_id', string='Revision Lines')


class HrShiftRosterRevisionLine(models.Model):
    _name = 'hr.shift.roster.revision.line'
    _description = 'Shift Roster Revision Line'
    _order = 'date, employee_id'

    revision_id = fields.Many2one('hr.shift.roster.revision', required=True, ondelete='cascade')
    roster_id = fields.Many2one(related='revision_id.roster_id', store=True, readonly=True)
    company_id = fields.Many2one(related='revision_id.company_id', store=True, readonly=True)
    date = fields.Date(required=True)
    employee_id = fields.Many2one('hr.employee', required=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    attendance_category = fields.Selection([
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], readonly=True)
    shift_template_id = fields.Many2one('hr.shift.template', required=True, readonly=True)
    start_time = fields.Float(readonly=True)
    end_time = fields.Float(readonly=True)
    break_duration = fields.Float(readonly=True)
    is_weekly_off = fields.Boolean(readonly=True)
    is_public_holiday = fields.Boolean(readonly=True)
    holiday_name = fields.Char(readonly=True)
    notes = fields.Text(readonly=True)
