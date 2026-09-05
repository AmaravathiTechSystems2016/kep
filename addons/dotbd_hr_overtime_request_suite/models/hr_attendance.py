# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    manual_overtime_request_id = fields.Many2one(
        'hr.overtime.request',
        string='Manual Overtime Request',
        readonly=True,
        ondelete='set null',
    )
    manual_overtime_hours = fields.Float(
        string='Manual Overtime (Hours)',
        readonly=True,
        help='Approved manual overtime hours linked from the overtime request.',
    )
