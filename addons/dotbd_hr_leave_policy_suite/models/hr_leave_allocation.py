# -*- coding: utf-8 -*-

from odoo import fields, models


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    leave_policy_id = fields.Many2one(
        'attendance.leave.policy',
        string='Leave Policy',
        readonly=True,
        index=True,
        tracking=True,
    )
    leave_policy_line_id = fields.Many2one(
        'attendance.leave.policy.line',
        string='Policy Line',
        readonly=True,
        index=True,
        tracking=True,
    )
    allocation_origin = fields.Selection(
        [
            ('fixed', 'Fixed Annual Allocation'),
            ('earned', 'Earned Leave'),
            ('comp_off', 'Comp Off'),
            ('carry_forward', 'Carry Forward'),
            ('opening_balance', 'Opening Balance'),
            ('probation', 'Probation Allocation'),
            ('manual', 'Manual'),
        ],
        string='Allocation Origin',
        readonly=True,
        index=True,
        tracking=True,
    )
