# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrShiftTemplate(models.Model):
    _name = 'hr.shift.template'
    _description = 'Shift Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    applicable_category = fields.Selection([
        ('all', 'All'),
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], string='Applicable Category', default='all', tracking=True)
    start_time = fields.Float(string='Start Time', required=True, tracking=True,
                              help='Expected shift start time in hours.')
    end_time = fields.Float(string='End Time', required=True, tracking=True,
                            help='Expected shift end time in hours.')
    break_duration = fields.Float(string='Break Duration (Hours)', default=1.0)
    grace_in_minutes = fields.Integer(string='Check-in Grace (Minutes)', default=0)
    grace_out_minutes = fields.Integer(string='Check-out Grace (Minutes)', default=0)
    overtime_allowed = fields.Boolean(string='Overtime Allowed', default=False)
    weekly_off_day_ids = fields.Many2many(
        'hr.shift.weekday',
        'hr_shift_template_weekday_rel',
        'template_id',
        'weekday_id',
        string='Weekly Off Days',
        help='Days that are treated as off days for this shift template.')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')

    @api.constrains('start_time', 'end_time')
    def _check_time_range(self):
        for rec in self:
            if rec.start_time == rec.end_time:
                raise ValidationError('Shift start and end time cannot be the same.')
