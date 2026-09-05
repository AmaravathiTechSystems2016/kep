# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    payroll_profile_id = fields.Many2one(
        'dotbd.hr.payroll.profile',
        string='Payroll Profile',
        tracking=True,
        domain="[('company_id', '=', company_id), ('attendance_category', '=', attendance_category)]",
        help='Payroll profile used to configure salary structure and allowances.',
    )
    esi_applicable = fields.Boolean(string='ESI Applicable', tracking=True)
    pf_applicable = fields.Boolean(string='PF Applicable', tracking=True)
    payroll_hra = fields.Monetary(string='HRA', tracking=True, currency_field='payroll_currency_id')
    payroll_basic = fields.Monetary(string='Basic Salary', tracking=True, currency_field='payroll_currency_id')
    payroll_special_allowance = fields.Monetary(string='Special Allowance', tracking=True, currency_field='payroll_currency_id')
    payroll_conveyance_allowance = fields.Monetary(string='Conveyance Allowance', tracking=True, currency_field='payroll_currency_id')
    payroll_washing_allowance = fields.Monetary(string='Washing Allowance', tracking=True, currency_field='payroll_currency_id')
    payroll_medical_allowance = fields.Monetary(string='Medical Allowance', tracking=True, currency_field='payroll_currency_id')
    payroll_overtime_multiplier = fields.Float(string='Overtime Multiplier', tracking=True)
    payroll_notes = fields.Text(string='Payroll Notes')
    payroll_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
    )
    payroll_gross_preview = fields.Monetary(
        string='Gross Preview',
        compute='_compute_payroll_gross_preview',
        store=False,
        currency_field='payroll_currency_id',
    )

    @api.depends(
        'payroll_basic',
        'payroll_hra',
        'payroll_special_allowance',
        'payroll_conveyance_allowance',
        'payroll_washing_allowance',
        'payroll_medical_allowance',
    )
    def _compute_payroll_gross_preview(self):
        for rec in self:
            rec.payroll_gross_preview = (
                rec.payroll_basic
                + rec.payroll_hra
                + rec.payroll_special_allowance
                + rec.payroll_conveyance_allowance
                + rec.payroll_washing_allowance
                + rec.payroll_medical_allowance
            )

    def _suggest_payroll_profile(self, company_id=None, attendance_category=None):
        company_id = company_id or self.company_id.id
        attendance_category = attendance_category or getattr(self, 'attendance_category', False)
        if not company_id or not attendance_category:
            return False
        return self.env['dotbd.hr.payroll.profile'].sudo().search([
            ('company_id', '=', company_id),
            ('attendance_category', '=', attendance_category),
            ('active', '=', True),
        ], limit=1)

    @api.onchange('company_id', 'attendance_category')
    def _onchange_payroll_profile_id(self):
        for employee in self:
            if employee.payroll_profile_id:
                continue
            profile = employee._suggest_payroll_profile()
            if profile:
                employee.payroll_profile_id = profile
                employee.esi_applicable = profile.use_esi
                employee.pf_applicable = profile.use_pf
                employee.payroll_overtime_multiplier = profile.overtime_multiplier
                employee.payroll_special_allowance = employee.payroll_special_allowance or profile.special_allowance
                employee.payroll_conveyance_allowance = employee.payroll_conveyance_allowance or profile.conveyance_allowance
                employee.payroll_washing_allowance = employee.payroll_washing_allowance or profile.washing_allowance
                employee.payroll_medical_allowance = employee.payroll_medical_allowance or profile.medical_allowance

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company_id = vals.get('company_id', self.env.company.id)
            attendance_category = vals.get('attendance_category')
            if not vals.get('payroll_profile_id') and company_id and attendance_category:
                profile = self.env['dotbd.hr.payroll.profile'].sudo().search([
                    ('company_id', '=', company_id),
                    ('attendance_category', '=', attendance_category),
                    ('active', '=', True),
                ], limit=1)
                if profile:
                    vals['payroll_profile_id'] = profile.id
                    vals.setdefault('esi_applicable', profile.use_esi)
                    vals.setdefault('pf_applicable', profile.use_pf)
                    vals.setdefault('payroll_overtime_multiplier', profile.overtime_multiplier)
        return super().create(vals_list)
