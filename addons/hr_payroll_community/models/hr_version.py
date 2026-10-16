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
    basic_mode = fields.Selection([
        ('fixed', 'Fixed'),
        ('percentage', 'Percentage of Gross'),
    ], string='Basic Mode', default='percentage', required=True,
        help="Fixed uses the entered basic, such as 14000 or 16500. "
             "Percentage calculates basic as that percent of gross wage.")
    basic_salary = fields.Monetary(
        string='Fixed Basic',
        tracking=True,
        help="Monthly basic used when Basic Mode is Fixed.")
    basic_percentage = fields.Float(
        string='Basic Percentage (%)',
        help="Percent of gross wage used as basic when Basic Mode is Percentage.")
    hra_percentage = fields.Float(
        string='HRA Percentage (%)',
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
        help="Employee ESI contribution percentage.")
    esi_employer_rate = fields.Float(
        string="ESI Employer Rate (%)",
        digits='Payroll Rate',
        help="Employer ESI contribution percentage.")
    esi_wage_ceiling = fields.Float(
        string="ESI Wage Ceiling",
        help="Maximum monthly wage eligible for ESI.")
    professional_tax = fields.Monetary(
        string="Professional Tax",
        help="Monthly professional tax deduction for this employee.")
    pf_rate = fields.Float(
        string="PF Rate (%)",
        digits='Payroll Rate',
        help="Employee provident fund contribution percentage.")
    pf_wage_ceiling = fields.Monetary(
        string="PF Wage Ceiling",
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
        string="Overtime Multiplier",
        help="Multiplier applied for overtime calculations.")

    def get_basic_amount(self):
        """Monthly basic. Fixed amount, or a percentage of gross wage."""
        self.ensure_one()
        if self.basic_mode == 'fixed':
            return self.basic_salary or 0.0
        return (self.wage or 0.0) * (self.basic_percentage or 0.0) / 100.0

    def get_hra_amount(self):
        """HRA is 30 percent of basic for every slab."""
        self.ensure_one()
        return self.get_basic_amount() * 0.30

    def get_conveyance_amount(self):
        """Conveyance balances gross. It can be negative.

        Gross = Basic + HRA + Conveyance. Medical is not part of any slab.
        """
        self.ensure_one()
        return (self.wage or 0.0) - self.get_basic_amount() - self.get_hra_amount()

    @api.model
    def _init_basic_mode(self):
        """Keep a filled fixed basic on Fixed mode. Everyone else stays on percentage."""
        self.search([('basic_salary', '>', 0)]).write({'basic_mode': 'fixed'})

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
            structures = self.env['hr.payroll.structure']
            for contract in self:
                structures |= contract._structure_for_profile()

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
        """Return values from the editable profile configuration record."""
        profile = self.env['hr.payroll.profile'].sudo().search([
            ('code', '=', self.payroll_profile),
        ], limit=1)
        if not profile:
            return {}
        fields_to_copy = [
            'basic_percentage', 'hra_percentage', 'allowance_amount',
            'washing_allowance', 'conveyance_allowance', 'medical_allowance',
            'da', 'travel_allowance', 'meal_allowance', 'other_allowance',
            'overtime_multiplier', 'esi_applicable', 'esi_employee_rate',
            'esi_employer_rate', 'esi_wage_ceiling', 'pf_rate',
            'pf_wage_ceiling',
            'professional_tax',
        ]
        values = {field_name: profile[field_name] for field_name in fields_to_copy}
        structure = self._structure_for_profile()
        if structure and not self.struct_id:
            values['struct_id'] = structure.id
        return values

    def _structure_for_profile(self):
        """Salary structure that matches this contract's payroll profile."""
        self.ensure_one()
        if self.struct_id:
            return self.struct_id
        xmlid = {
            'manufacturing_worker': 'hr_payroll_community.structure_worker',
            'computer_esi': 'hr_payroll_community.structure_office',
            'computer_no_esi': 'hr_payroll_community.structure_office',
        }.get(self.payroll_profile)
        if not xmlid:
            return self.env['hr.payroll.structure']
        return self.env.ref(xmlid, raise_if_not_found=False) or self.env['hr.payroll.structure']

    @api.model
    def _assign_missing_payroll_structures(self):
        """Fill salary structures that were left empty on existing contracts."""
        for contract in self.search([('struct_id', '=', False)]):
            structure = contract._structure_for_profile()
            if structure:
                contract.struct_id = structure.id
        slips = self.env['hr.payslip'].search([
            ('struct_id', '=', False),
            ('state', '=', 'draft'),
            ('contract_id', '!=', False),
        ])
        for slip in slips:
            if slip.contract_id.struct_id:
                slip.struct_id = slip.contract_id.struct_id

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
