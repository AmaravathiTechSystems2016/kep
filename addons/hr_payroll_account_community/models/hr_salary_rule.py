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
from odoo import Command, api, fields, models


class HrSalaryRule(models.Model):
    """Extends the standard 'hr.salary.rule' model to include additional
    fields for defining salary rules."""
    _inherit = 'hr.salary.rule'

    analytic_account_id = fields.Many2one('account.analytic.account',
                                          string='Analytic Account',
                                          help="Analytic account associated "
                                               "with the record")
    account_tax_id = fields.Many2one('account.tax', string='Tax',
                                     help="Tax account associated with the "
                                          "record")
    account_debit_id = fields.Many2one('account.account',
                                       string='Debit Account',
                                       help="Debit account associated with the"
                                            " record")
    account_credit_id = fields.Many2one('account.account',
                                        string='Credit Account',
                                        help="Credit account associated with"
                                             " the record")

    # Positive amounts debit the first account and credit the second.
    # Deductions are stored as negative amounts, so those sides swap:
    # the liability or expense reversal belongs in the debit field.
    _EARNING_DEBIT_XMLIDS = {
        'BASIC': ('p2101', 'expense_salary'),
        'DA': ('p2101', 'expense_salary'),
        'HRA': ('p300001', 'expense_salary'),
        'Travel': ('p300002', 'expense_salary'),
        'Meal': ('p300002', 'expense_salary'),
        'Medical': ('p300002', 'expense_salary'),
        'Other': ('p300002', 'expense_salary'),
        'OT': ('p2101', 'expense_salary'),
    }
    _DEDUCTION_DEBIT_XMLIDS = {
        'PF': ('p300007', 'employee_payroll_taxes'),
        'ESI': ('esi_payable', 'employee_payroll_taxes'),
        'PT': ('p300012', 'employee_payroll_taxes'),
        'UNPAID': ('p2101', 'expense_salary'),
        'LC': ('p2101', 'expense_salary'),
        'SAR': ('p300009', 'prepayments'),
        'LO': ('p300009', 'prepayments'),
    }
    _PAYABLE_XMLIDS = ('p300010', 'salary_payable', 'p11241')

    @api.model
    def _chart_account(self, company, xmlids):
        for xmlid in xmlids:
            if xmlid == 'esi_payable':
                account = self.env.ref(
                    f'hr_payroll_account_community.{company.id}_esi_payable',
                    raise_if_not_found=False,
                )
            else:
                account = self.env.ref(
                    f'account.{company.id}_{xmlid}',
                    raise_if_not_found=False,
                )
            if account and company in account.company_ids:
                return account
        return self.env['account.account']

    @api.model
    def _ensure_esi_payable_account(self, company):
        """Indian chart has PF and professional tax, but no ESI payable."""
        if company.chart_template != 'in':
            return self.env['account.account']
        account = self._chart_account(company, ('esi_payable',))
        if account:
            return account
        account = self.env['account.account'].with_company(company).search([
            ('company_ids', 'in', company.id),
            ('code', '=', '300013'),
        ], limit=1)
        if not account:
            account = self.env['account.account'].with_company(company).create({
                'name': 'Employee State Insurance Payable',
                'code': '300013',
                'account_type': 'liability_current',
                'company_ids': [Command.link(company.id)],
            })
        self.env['ir.model.data'].sudo().create({
            'name': f'{company.id}_esi_payable',
            'module': 'hr_payroll_account_community',
            'model': 'account.account',
            'res_id': account.id,
            'noupdate': True,
        })
        return account

    @api.model
    def _assign_payroll_accounts(self, companies=None):
        """Set salary-rule accounts from the company chart.

        Gross and Net stay without accounts. They are totals of the other
        rules, and posting them would book the same salary twice.
        """
        if companies is None:
            companies = self.env['res.company'].sudo().search([])
        for company in companies:
            self._ensure_esi_payable_account(company)
            payable = self._chart_account(company, self._PAYABLE_XMLIDS)
            if not payable:
                continue
            rules = self.sudo().with_context(active_test=False).search([
                ('code', 'in', list(self._EARNING_DEBIT_XMLIDS) + list(
                    self._DEDUCTION_DEBIT_XMLIDS)),
            ])
            for rule in rules:
                if rule.code in self._EARNING_DEBIT_XMLIDS:
                    debit = self._chart_account(
                        company, self._EARNING_DEBIT_XMLIDS[rule.code])
                    credit = payable
                else:
                    debit = self._chart_account(
                        company, self._DEDUCTION_DEBIT_XMLIDS[rule.code])
                    credit = payable
                if debit and credit:
                    rule.write({
                        'account_debit_id': debit.id,
                        'account_credit_id': credit.id,
                    })
