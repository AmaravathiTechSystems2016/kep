# -*- coding: utf-8 -*-

from odoo import models


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _post_load_data(self, template_code, company, template_data):
        super()._post_load_data(template_code, company, template_data)
        self.env['account.journal']._ensure_salary_journals(company)
        self.env['hr.salary.rule']._assign_payroll_accounts(company)
