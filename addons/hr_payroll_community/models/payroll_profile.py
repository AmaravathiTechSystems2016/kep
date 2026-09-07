# -*- coding: utf-8 -*-

from odoo import fields, models


class HrPayrollProfile(models.Model):
    _name = 'hr.payroll.profile'
    _description = 'Payroll Profile'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Selection([
        ('manufacturing_worker', 'Manufacturing Worker'),
        ('computer_esi', 'Computer Worker With ESI'),
        ('computer_no_esi', 'Computer Worker Without ESI'),
    ], required=True, index=True)
    basic_percentage = fields.Float(string='Basic Percentage (%)')
    hra_percentage = fields.Float(string='HRA Percentage (%)')
    allowance_amount = fields.Monetary(string='Allowance')
    washing_allowance = fields.Monetary(string='Washing Allowance')
    conveyance_allowance = fields.Monetary(string='Conveyance Allowance')
    medical_allowance = fields.Monetary(string='Medical Allowance')
    da = fields.Monetary(string='DA')
    travel_allowance = fields.Monetary(string='Travel Allowance')
    meal_allowance = fields.Monetary(string='Meal Allowance')
    other_allowance = fields.Monetary(string='Other Allowance')
    overtime_multiplier = fields.Float(string='Overtime Multiplier')
    esi_applicable = fields.Boolean(string='ESI Applicable')
    esi_employee_rate = fields.Float(string='ESI Rate (%)')
    esi_employer_rate = fields.Float(string='ESI Employer Rate (%)')
    esi_wage_ceiling = fields.Float(string='ESI Wage Ceiling')
    pf_rate = fields.Float(string='PF Rate (%)')
    pf_wage_ceiling = fields.Monetary(string='PF Wage Ceiling')
    professional_tax = fields.Monetary(string='Professional Tax')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
        required=True,
    )

    _code_unique = models.Constraint(
        'UNIQUE(code)', 'Each payroll profile code must be unique.')
