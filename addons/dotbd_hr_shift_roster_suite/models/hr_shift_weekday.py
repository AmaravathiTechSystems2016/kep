# -*- coding: utf-8 -*-

from odoo import fields, models


class HrShiftWeekday(models.Model):
    _name = 'hr.shift.weekday'
    _description = 'Shift Weekday'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Selection([
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
        ('sun', 'Sunday'),
    ], required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

