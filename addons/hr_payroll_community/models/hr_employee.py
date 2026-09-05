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
from odoo import fields, models


class HrEmployee(models.Model):
    """Inherit hr_employee for getting Payslip Counts"""
    _inherit = 'hr.employee'

    slip_ids = fields.One2many('hr.payslip',
                               'employee_id', string='Payslips',
                               readonly=True,
                               help="Choose Payslip for Employee")
    payslip_count = fields.Integer(compute='_compute_payslip_count',
                                   string='Payslip Count',
                                   help="Set Payslip Count")
    payroll_profile = fields.Selection(
        related='version_id.payroll_profile',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    basic_percentage = fields.Float(
        related='version_id.basic_percentage',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hra_percentage = fields.Float(
        related='version_id.hra_percentage',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    allowance_amount = fields.Monetary(
        related='version_id.allowance_amount',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    washing_allowance = fields.Monetary(
        related='version_id.washing_allowance',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    conveyance_allowance = fields.Monetary(
        related='version_id.conveyance_allowance',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    overtime_multiplier = fields.Float(
        related='version_id.overtime_multiplier',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    esi_applicable = fields.Boolean(
        related='version_id.esi_applicable',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    esi_employee_rate = fields.Float(
        related='version_id.esi_employee_rate',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    esi_employer_rate = fields.Float(
        related='version_id.esi_employer_rate',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    esi_wage_ceiling = fields.Float(
        related='version_id.esi_wage_ceiling',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    uan_number = fields.Char(
        related='version_id.uan_number',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    professional_tax = fields.Monetary(
        related='version_id.professional_tax',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    pf_rate = fields.Float(
        related='version_id.pf_rate',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    pf_wage_ceiling = fields.Monetary(
        related='version_id.pf_wage_ceiling',
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )

    def _compute_payslip_count(self):
        """Function for count Payslips"""
        payslip_data = self.env['hr.payslip'].sudo().read_group(
            [('employee_id', 'in', self.ids)],
            ['employee_id'], ['employee_id'])
        result = dict(
            (data['employee_id'][0], data['employee_id_count']) for data in
            payslip_data)
        for employee in self:
            employee.payslip_count = result.get(employee.id, 0)
