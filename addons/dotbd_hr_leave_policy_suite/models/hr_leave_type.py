# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    support_document_after_days = fields.Float(
        string='Supporting Document After Days',
        default=0.0,
        help='If greater than 0, time off requests longer than this number of days require an attachment.',
    )
    probation_allowed_type = fields.Boolean(
        string='Probation Allowed',
        compute='_compute_probation_allowed_type',
        store=True,
        help='Allow this leave type to be selected during probation even without a normal allocation balance.',
    )

    @api.depends('name', 'code')
    def _compute_probation_allowed_type(self):
        allowed_names = {'casual leave', 'casual', 'sick time off', 'sick leave', 'sick', 'unpaid leave', 'unpaid'}
        allowed_codes = {'cl', 'sl', 'unp', 'unp1', 'unpaid'}
        for leave_type in self:
            name = (leave_type.name or '').strip().lower()
            code = (leave_type.code or '').strip().lower()
            leave_type.probation_allowed_type = name in allowed_names or code in allowed_codes
