# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    onboarding_ids = fields.One2many('hr.employee.onboarding', 'employee_id', string='Onboarding Records')
    onboarding_count = fields.Integer(compute='_compute_onboarding_count', string='Onboarding Count')

    @api.depends('onboarding_ids')
    def _compute_onboarding_count(self):
        counts = self.env['hr.employee.onboarding']._read_group(
            [('employee_id', 'in', self.ids)],
            ['employee_id'],
            ['__count']
        )
        mapped = {employee.id: count for employee, count in counts}
        for employee in self:
            employee.onboarding_count = mapped.get(employee.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        if self.env.context.get('skip_auto_onboarding'):
            return employees

        onboarding_model = self.env['hr.employee.onboarding'].sudo()
        template_model = self.env['hr.onboarding.template'].sudo()

        for employee, vals in zip(employees, vals_list):
            category = vals.get('attendance_category') or getattr(employee, 'attendance_category', False)
            if category not in ('worker', 'office', 'other'):
                continue

            existing = onboarding_model.search([('employee_id', '=', employee.id)], limit=1)
            if existing:
                continue

            template = template_model.get_template_for_category(category, company_id=employee.company_id.id)
            onboarding = onboarding_model.create({
                'employee_id': employee.id,
                'employee_category': category,
                'template_id': template.id if template else False,
            })
            if template:
                onboarding.action_load_template()

        return employees
