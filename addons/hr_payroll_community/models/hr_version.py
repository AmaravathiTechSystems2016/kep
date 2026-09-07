# -*- coding: utf-8 -*-
#############################################################################
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import api, fields, models


class HrContract(models.Model):
    """
    Employee contract based on the visa, work permits
    allows to configure different Salary structure
    """
    _inherit = 'hr.version'

    struct_id = fields.Many2one('hr.payroll.structure',
                                string='Salary Structure',
                                help="Choose Payroll Structure")
    payroll_profile = fields.Selection([
        ('manufacturing_worker', 'Manufacturing Worker'),
        ('computer_esi', 'Computer Worker With ESI'),
        ('computer_no_esi', 'Computer Worker Without ESI'),
    ], string='Payroll Profile', default='manufacturing_worker',
        help="Select the payroll policy profile for this employee.")
    basic_percentage = fields.Float(
        string='Basic Percentage (%)', default=50.0,
        help="Percentage of monthly wage used as basic salary.")
    hra_percentage = fields.Float(
        string='HRA Percentage (%)', default=30.0,
        help="Percentage applied on basic salary for HRA.")
    schedule_pay = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi-annually', 'Semi-annually'),
        ('annually', 'Annually'),
        ('weekly', 'Weekly'),
        ('bi-weekly', 'Bi-weekly'),
        ('bi-monthly', 'Bi-monthly'),
    ], string='Scheduled Pay', index=True, default='monthly',
        help="Defines the frequency of the wage payment.")
    hra = fields.Monetary(string='HRA', tracking=True,
                          help="House rent allowance.")
    conveyance_allowance = fields.Monetary(
        string="Conveyance Allowance",
        help="Conveyance allowance. If left zero, it can be calculated as the "
             "remaining allowance component based on the wage.")
    washing_allowance = fields.Monetary(
        string="Washing Allowance",
        help="Washing allowance for manufacturing workers.")
    allowance_amount = fields.Monetary(
        string="Allowance",
        help="Generic allowance amount for office/computer worker profiles.")
    esi_applicable = fields.Boolean(
        string="ESI Applicable",
        help="Enable ESI deduction for this contract.")
    esi_employee_rate = fields.Float(
        string="ESI Rate (%)",
        digits='Payroll Rate',
        default=0.75,
        help="Employee ESI contribution percentage.")
    esi_employer_rate = fields.Float(
        string="ESI Employer Rate (%)",
        digits='Payroll Rate',
        default=3.25,
        help="Employer ESI contribution percentage.")
    esi_wage_ceiling = fields.Float(
        string="ESI Wage Ceiling",
        default=21000.0,
        help="Maximum monthly wage eligible for ESI.")
    professional_tax = fields.Monetary(
        string="Professional Tax",
        help="Monthly professional tax deduction for this employee.")
    pf_rate = fields.Float(
        string="PF Rate (%)",
        digits='Payroll Rate',
        default=12.0,
        help="Employee provident fund contribution percentage.")
    pf_wage_ceiling = fields.Monetary(
        string="PF Wage Ceiling",
        default=15000.0,
        help="Maximum monthly Basic plus DA amount subject to PF.")
    uan_number = fields.Char(
        string="UAN Number",
        help="Universal Account Number used for provident fund records.")
    travel_allowance = fields.Monetary(string="Travel Allowance",
                                       help="Travel allowance")
    da = fields.Monetary(string="DA", help="Dearness allowance")
    meal_allowance = fields.Monetary(string="Meal Allowance",
                                     help="Meal allowance")
    medical_allowance = fields.Monetary(string="Medical Allowance",
                                        help="Medical allowance")
    other_allowance = fields.Monetary(string="Other Allowance",
                                      help="Other allowances")
    overtime_multiplier = fields.Float(
        string="Overtime Multiplier", default=2.0,
        help="Multiplier applied for overtime calculations.")

    def get_all_structures(self):
        """
        @return: the structures linked to the given contracts, ordered by
        hierarchy (parent=False first,then first level children and so on)
        and without duplicate
        """
        structures = self.mapped('struct_id')
        if not structures:
            structures = self.mapped('contract_template_id.struct_id')

        if not structures:
            return []
        # YTI TODO return browse records
        return list(set(structures._get_parent_structure().ids))

    @api.onchange('payroll_profile')
    def _onchange_payroll_profile(self):
        """Apply a sensible default setup for the chosen payroll profile."""
        for contract in self:
            contract.update(contract._payroll_profile_defaults())

    def _payroll_profile_defaults(self):
        """Return the standard contract values for the selected profile."""
        profile = self.payroll_profile
        defaults = {
            'basic_percentage': 50.0,
            'hra_percentage': 30.0,
            'allowance_amount': 0.0,
            'washing_allowance': 0.0,
            'conveyance_allowance': 0.0,
            'medical_allowance': 0.0,
            'esi_applicable': False,
            'esi_employee_rate': 0.0,
            'esi_wage_ceiling': 0.0,
        }
        if profile == 'manufacturing_worker':
            defaults.update({
                'washing_allowance': 1250.0,
                'esi_applicable': True,
                'esi_employee_rate': 0.75,
                'esi_wage_ceiling': 21000.0,
            })
        elif profile == 'computer_esi':
            defaults.update({
                'allowance_amount': 1250.0,
                'esi_applicable': True,
                'esi_employee_rate': 0.75,
                'esi_wage_ceiling': 21000.0,
            })
        elif profile == 'computer_no_esi':
            defaults.update({
                'hra_percentage': 40.0,
                'medical_allowance': 1250.0,
            })
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        contracts = super().create(vals_list)
        for contract, vals in zip(contracts, vals_list):
            if 'payroll_profile' in vals:
                contract.update(contract._payroll_profile_defaults())
        return contracts

    def write(self, vals):
        result = super().write(vals)
        if 'payroll_profile' in vals:
            for contract in self:
                contract.update(contract._payroll_profile_defaults())
        return result

    def get_attribute(self, code, attribute):
        """Function for return code for Contract"""
        return self.env['hr.contract.advantage.template'].search(
                [('code', '=', code)],
                limit=1)[attribute]

    def set_attribute_value(self, code, active):
        """Function for set code for Contract"""
        for contract in self:
            if active:
                value = self.env['hr.contract.advantage.template'].search(
                    [('code', '=', code)], limit=1).default_value
                contract[code] = value
            else:
                contract[code] = 0.0
