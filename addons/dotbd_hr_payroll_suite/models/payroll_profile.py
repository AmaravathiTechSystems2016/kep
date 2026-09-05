# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DotbdHrPayrollProfile(models.Model):
    _name = 'dotbd.hr.payroll.profile'
    _description = 'Dot BD Payroll Profile'
    _order = 'company_id, attendance_category, name'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    attendance_category = fields.Selection([
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], required=True, tracking=True)
    payroll_structure_id = fields.Many2one(
        'hr.payroll.structure',
        string='Payroll Structure',
        tracking=True,
    )
    use_pf = fields.Boolean(string='Apply PF', tracking=True)
    use_esi = fields.Boolean(string='Apply ESI', tracking=True)
    pf_percentage = fields.Float(string='PF %', tracking=True)
    esi_percentage = fields.Float(string='ESI %', tracking=True)
    basic_mode = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('ctc', 'CTC Based'),
        ('minimum_wage', 'Minimum Wage Based'),
    ], string='Basic Mode', required=True, tracking=True)
    basic_percentage = fields.Float(string='Basic % of CTC', tracking=True)
    hra_percentage = fields.Float(string='HRA %', tracking=True)
    special_allowance = fields.Monetary(tracking=True)
    conveyance_allowance = fields.Monetary(tracking=True)
    washing_allowance = fields.Monetary(tracking=True)
    medical_allowance = fields.Monetary(tracking=True)
    overtime_multiplier = fields.Float(string='Overtime Multiplier', tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text()
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
    )

    _sql_constraints = [
        (
            'dotbd_payroll_profile_unique',
            'unique(company_id, attendance_category, name)',
            'Payroll profile name must be unique per company and category.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('company_id', self.env.company.id)
        return super().create(vals_list)
