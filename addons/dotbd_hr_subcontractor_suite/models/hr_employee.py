# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    subcontractor_id = fields.Many2one(
        'hr.subcontractor', string='Subcontractor', tracking=True)
    subcontractor_status = fields.Selection([
        ('assigned', 'Assigned'),
        ('active', 'Active'),
        ('released', 'Released'),
    ], string='Subcontractor Status', default='assigned', tracking=True)
    subcontractor_join_date = fields.Date(string='Subcontractor Join Date', tracking=True)
    subcontractor_end_date = fields.Date(string='Subcontractor End Date', tracking=True)

    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_id(self):
        for employee in self:
            if employee.subcontractor_id:
                employee.employee_type = 'contractor'
                if not employee.subcontractor_join_date:
                    employee.subcontractor_join_date = employee.subcontractor_id.contract_start

    @api.constrains('subcontractor_join_date', 'subcontractor_end_date')
    def _check_subcontractor_dates(self):
        for employee in self:
            if (employee.subcontractor_join_date and employee.subcontractor_end_date
                    and employee.subcontractor_end_date < employee.subcontractor_join_date):
                raise ValidationError(_('Subcontractor End Date must be after Join Date.'))
