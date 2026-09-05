# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    default_shift_template_id = fields.Many2one(
        'hr.shift.template', string='Default Shift Template',
        help='Default shift used when a roster or assignment does not specify one.')

