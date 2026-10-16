# -*- coding: utf-8 -*-

from odoo import api, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _default_salary_journal(self):
        company = self.env.company
        journal = self.search([
            ('company_id', '=', company.id),
            ('type', '=', 'general'),
            ('code', '=', 'SAL'),
        ], limit=1)
        if journal:
            return journal
        return self.search([
            ('company_id', '=', company.id),
            ('type', '=', 'general'),
            ('code', 'not in', ('CABA', 'EXCH')),
        ], limit=1)

    @api.model
    def _get_salary_payable_account(self, company):
        """Net salary liability from the installed chart."""
        for xmlid in ('p300010', 'salary_payable', 'p11241'):
            account = self.env.ref(
                f'account.{company.id}_{xmlid}',
                raise_if_not_found=False,
            )
            if account and company in account.company_ids:
                return account
        return self.env['account.account'].with_company(company).search([
            ('company_ids', 'in', company.id),
            ('account_type', '=', 'liability_current'),
            ('name', 'in', ('Salary Exp Payable', 'Salary Payable', 'Wages Payable')),
        ], limit=1)

    @api.model
    def _ensure_salary_journals(self, companies=None):
        """Create one general Salaries journal per company.

        The default account is the chart's Salary Payable account. Payslip
        posting uses that account only to balance an entry. Salary rule debit
        and credit accounts stay on the rules themselves.
        """
        if companies is None:
            companies = self.env['res.company'].sudo().search([])
        for company in companies:
            journal = self.with_company(company).search([
                ('company_id', '=', company.id),
                ('code', '=', 'SAL'),
            ], limit=1)
            payable = self._get_salary_payable_account(company)
            if journal:
                if payable and journal.default_account_id != payable:
                    journal.default_account_id = payable
                continue
            self.with_company(company).create({
                'name': 'Salaries',
                'code': 'SAL',
                'type': 'general',
                'company_id': company.id,
                'default_account_id': payable.id if payable else False,
            })
