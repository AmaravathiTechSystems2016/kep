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

from odoo import api, models


class ReportHrPayrollCommunityReportPayslipDetails(models.AbstractModel):
    """Create new model for getting Payslip Details Report"""
    _name = 'report.hr_payroll_community.report_payslipdetails'
    _description = 'Payslip Details Report'

    # The payslip builder consolidates unpaid leave and absence into one line.
    _LOP_CODES = frozenset(('LOP',))
    # Same unpaid codes the salary rules exclude from paid days.
    _UNPAID_CODES = frozenset(('LOP', 'UNPAID', 'UNP', 'UNP1', 'UL', 'PL1'))

    @staticmethod
    def _line_amounts(payslip):
        amounts = {}
        for line in payslip.line_ids.filtered('appears_on_payslip'):
            amounts[line.code] = amounts.get(line.code, 0.0) + line.total
        return amounts

    @staticmethod
    def _amount(amounts, *codes):
        return sum(amounts.get(code, 0.0) for code in codes)

    def get_summary(self, payslip):
        amounts = self._line_amounts(payslip)
        contract = payslip.contract_id
        calendar_days = (payslip.date_to - payslip.date_from).days + 1
        # Paid leave of any type counts as worked; only unpaid leave and
        # loss of pay count as absence.
        worked_days = sum(
            line.number_of_days for line in payslip.worked_days_line_ids
            if (line.code or '').strip().upper() not in self._UNPAID_CODES
        )
        lop_days = sum(
            line.number_of_days for line in payslip.worked_days_line_ids
            if (line.code or '').strip().upper() in self._LOP_CODES
        )
        basic_master = contract.get_basic_amount() if contract else 0.0
        hra_master = contract.get_hra_amount() if contract else 0.0
        conveyance_master = contract.get_conveyance_amount() if contract else 0.0
        basic = self._amount(amounts, 'BASIC')
        conveyance = self._amount(amounts, 'Travel')
        net = self._amount(amounts, 'NET')
        deduction_codes = ('PF', 'ESI', 'PT', 'SALARY_ADVANCE', 'TDS',
                           *self._LOP_CODES)
        total_deductions = abs(sum(
            amount for code, amount in amounts.items()
            if code in deduction_codes and amount < 0
        ))
        other_deductions = abs(sum(
            amount for code, amount in amounts.items()
            if code not in (
                'PF', 'ESI', 'PT', 'SALARY_ADVANCE', 'TDS', 'NET',
                'BASIC', 'HRA', 'Travel', 'GROSS', 'DA', 'Meal',
                'Medical', 'Other', *self._LOP_CODES,
            ) and amount < 0
        ))
        total_deductions += other_deductions
        master_total = basic_master + hra_master + conveyance_master
        return {
            'calendar_days': calendar_days,
            'worked_days': round(worked_days, 2),
            'absent_days': round(max(calendar_days - worked_days, 0.0), 2),
            'lop_days': round(lop_days, 2),
            'basic': basic,
            'da': 0.0,
            'hra': self._amount(amounts, 'HRA'),
            'basic_da': basic,
            'medical_other': 0.0,
            'conveyance': conveyance,
            'gross': self._amount(amounts, 'GROSS'),
            'arrears': self._amount(amounts, 'ARREARS'),
            'master_basic_da': basic_master,
            'master_hra': hra_master,
            'master_medical_other': 0.0,
            'master_conveyance': conveyance_master,
            'master_total': master_total,
            'pf': abs(self._amount(amounts, 'PF')),
            'esi': abs(self._amount(amounts, 'ESI')),
            'pt': abs(self._amount(amounts, 'PT')),
            'salary_advance': abs(self._amount(amounts, 'SALARY_ADVANCE')),
            'tds': abs(self._amount(amounts, 'TDS')),
            'other_deductions': other_deductions,
            'lop': abs(self._amount(amounts, *self._LOP_CODES)),
            'total_deductions': total_deductions,
            'net': net,
            'salary_in_words': payslip.company_id.currency_id.amount_to_text(net),
        }

    @staticmethod
    def _format_payslip_period(date_from, date_to):
        """1-Sept-2026 to 30-Sept-2026 Payslip."""
        months = (
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec',
        )

        def _format(value):
            return f'{value.day}-{months[value.month - 1]}-{value.year}'

        return f'{_format(date_from)} to {_format(date_to)} Payslip'

    @staticmethod
    def get_report_data(payslip):
        """Return employee and bank values used by the formatted payslip."""
        employee = payslip.employee_id
        bank = employee.primary_bank_account_id
        bank_id = bank.bank_id if bank else False
        return {
            'employee_number': employee.employee_id or employee.identification_id or 'Not Applicable',
            'department': employee.department_id.name if employee.department_id else 'Not Applicable',
            'location': employee.work_location_id.name if employee.work_location_id else 'Not Applicable',
            'bank_name': bank_id.name if bank_id else 'Not Applicable',
            'bank_account': bank.acc_number if bank else 'Not Applicable',
            'ifsc': ((bank_id.ifsc_code or bank_id.bic) if bank_id else False) or 'Not Applicable',
            'esi_number': getattr(employee, 'esi_number', False) or 'Not Applicable',
            'contract_type': employee.sudo().contract_type_id.name or 'Not Applicable',
            'month_label': ReportHrPayrollCommunityReportPayslipDetails._format_payslip_period(
                payslip.date_from, payslip.date_to),
        }

    def get_details_by_rule_category(self, payslip_lines):
        """Function for get Salary Rule Categories"""
        PayslipLine = self.env['hr.payslip.line']
        RuleCateg = self.env['hr.salary.rule.category']

        def get_recursive_parent(current_rule_category, rule_categories=None):
            """Function for return Rule Categories with respect to Parent
            Category"""
            if rule_categories:
                rule_categories = current_rule_category | rule_categories
            else:
                rule_categories = current_rule_category
            if current_rule_category.parent_id:
                return get_recursive_parent(current_rule_category.parent_id,
                                            rule_categories)
            else:
                return rule_categories
        res = {}
        result = {}
        if payslip_lines:
            self.env.cr.execute("""
                SELECT pl.id, pl.category_id, pl.slip_id FROM 
                hr_payslip_line as pl
                LEFT JOIN hr_salary_rule_category AS rc on 
                (pl.category_id = rc.id)
                WHERE pl.id in %s
                GROUP BY rc.parent_id, pl.sequence, pl.id, pl.category_id
                ORDER BY pl.sequence, rc.parent_id""",
                                (tuple(payslip_lines.ids),))
            for x in self.env.cr.fetchall():
                result.setdefault(x[2], {})
                result[x[2]].setdefault(x[1], [])
                result[x[2]][x[1]].append(x[0])
            for payslip_id, lines_dict in result.items():
                res.setdefault(payslip_id, [])
                for rule_categ_id, line_ids in lines_dict.items():
                    rule_categories = RuleCateg.browse(rule_categ_id)
                    lines = PayslipLine.browse(line_ids)
                    level = 0
                    for parent in get_recursive_parent(rule_categories):
                        res[payslip_id].append({
                            'rule_category': parent.name,
                            'name': parent.name,
                            'code': parent.code,
                            'level': level,
                            'total': sum(lines.mapped('total')),
                        })
                        level += 1
                    for line in lines:
                        res[payslip_id].append({
                            'rule_category': line.name,
                            'name': line.name,
                            'code': line.code,
                            'total': line.total,
                            'level': level
                        })
        return res

    def get_lines_by_contribution_register(self, payslip_lines):
        """Function for getting Contribution Register Lines"""
        result = {}
        res = {}
        for line in payslip_lines.filtered('register_id'):
            result.setdefault(line.slip_id.id, {})
            result[line.slip_id.id].setdefault(line.register_id, line)
            result[line.slip_id.id][line.register_id] |= line
        for payslip_id, lines_dict in result.items():
            res.setdefault(payslip_id, [])
            for register, lines in lines_dict.items():
                res[payslip_id].append({
                    'register_name': register.name,
                    'total': sum(lines.mapped('total')),
                })
                for line in lines:
                    res[payslip_id].append({
                        'name': line.name,
                        'code': line.code,
                        'quantity': line.quantity,
                        'amount': line.amount,
                        'total': line.total,
                    })
        return res

    @api.model
    def _get_report_values(self, docids, data=None):
        """Function for getting Payslip Details Report values"""
        payslips = self.env['hr.payslip'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip',
            'docs': payslips,
            'data': data,
            'get_summary': self.get_summary,
            'get_report_data': self.get_report_data,
            'get_details_by_rule_category': self.get_details_by_rule_category(
                payslips.mapped('details_by_salary_rule_category_ids').filtered(
                    lambda r: r.appears_on_payslip)),
            'get_lines_by_contribution_register':
                self.get_lines_by_contribution_register(
                payslips.mapped('line_ids').filtered(
                    lambda r: r.appears_on_payslip)),
        }
