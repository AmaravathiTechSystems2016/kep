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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('subcontractor_id'):
                subcontractor = self.env['hr.subcontractor'].browse(
                    vals['subcontractor_id'])
                vals['contractor_code'] = self._next_subcontractor_code(subcontractor)
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if (not self.env.context.get('allow_subcontractor_code')
                and 'contractor_code' in vals
                and any(employee.subcontractor_id for employee in self)):
            vals.pop('contractor_code')
        result = super().write(vals)
        for employee in self:
            if employee.subcontractor_id:
                expected_prefix = '%s-EMP/' % employee.subcontractor_id.code
                if ('subcontractor_id' in vals
                        or not employee.contractor_code
                        or not employee.contractor_code.startswith(expected_prefix)):
                    employee.with_context(
                        allow_subcontractor_code=True).write({
                            'contractor_code': self._next_subcontractor_code(
                                employee.subcontractor_id),
                        })
        return result

    def _next_subcontractor_code(self, subcontractor):
        sequence_code = self.env['ir.sequence'].next_by_code(
            'hr.subcontractor.employee') or _('New')
        return '%s-%s' % (subcontractor.code, sequence_code)

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
