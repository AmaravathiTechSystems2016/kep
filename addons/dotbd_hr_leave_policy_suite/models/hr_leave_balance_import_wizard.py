# -*- coding: utf-8 -*-

import base64
import csv
import io
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AttendanceLeaveBalanceImportWizard(models.TransientModel):
    _name = 'attendance.leave.balance.import.wizard'
    _description = 'Import Old Leave Balances'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    balance_year = fields.Integer(
        string='Balance Year',
        default=lambda self: fields.Date.today().year,
        required=True,
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        help='Employees included in this import batch.',
    )
    csv_file = fields.Binary(
        string='CSV File',
        help='Upload a CSV file with columns like employee_name, employee_id, leave_type_name, leave_type_code, balance_year, opening_balance, notes.',
    )
    csv_filename = fields.Char(string='CSV Filename')
    line_ids = fields.One2many(
        'attendance.leave.balance.import.wizard.line',
        'wizard_id',
        string='Balance Lines',
    )

    def action_load_csv(self):
        self.ensure_one()
        if not self.csv_file:
            raise ValidationError(_('Please upload a CSV file first.'))

        raw = base64.b64decode(self.csv_file)
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValidationError(_('The uploaded CSV file is empty or invalid.'))

        required_any = {'opening_balance'}
        if not required_any.intersection({(name or '').strip().lower() for name in reader.fieldnames}):
            raise ValidationError(_(
                'The CSV file must contain at least an opening_balance column.'
            ))

        line_commands = [(5, 0, 0)]
        for index, row in enumerate(reader, start=2):
            normalized = {str(key or '').strip().lower(): (value or '').strip() for key, value in row.items()}
            employee = self._resolve_csv_employee(normalized)
            policy = self._resolve_csv_policy(normalized, employee)
            leave_type = self._resolve_csv_leave_type(normalized)
            balance_year = self._resolve_csv_year(normalized)
            opening_balance = self._resolve_csv_float(normalized, 'opening_balance')
            if not employee:
                raise ValidationError(_('Row %s: employee could not be resolved.') % index)
            if not leave_type:
                raise ValidationError(_('Row %s: leave type could not be resolved.') % index)
            line_commands.append((0, 0, {
                'employee_id': employee.id,
                'policy_id': policy.id if policy else False,
                'leave_type_id': leave_type.id,
                'balance_year': balance_year,
                'opening_balance': opening_balance,
                'notes': normalized.get('notes') or False,
            }))

        self.write({'line_ids': line_commands})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_('Please add at least one balance line to import.'))

        Balance = self.env['attendance.leave.balance'].sudo()
        Allocation = self.env['hr.leave.allocation'].sudo()
        created_or_updated = Balance.browse()
        created_allocations = Allocation.browse()

        for line in self.line_ids:
            employee = line.employee_id
            if not employee:
                raise ValidationError(_('Each line must have an employee.'))

            policy = line.policy_id or employee.leave_policy_id
            if not policy:
                raise ValidationError(_(
                    'No leave policy found for %(employee)s. Please select a policy on the line or assign one on the employee.'
                ) % {'employee': employee.name})

            policy_line = self._resolve_policy_line(policy, line.leave_type_id)
            if not policy_line:
                raise ValidationError(_(
                    'Leave type %(leave_type)s is not configured on policy %(policy)s for %(employee)s.'
                ) % {
                    'leave_type': line.leave_type_id.sudo().name,
                    'policy': policy.name,
                    'employee': employee.name,
                })

            balance_values = {
                'employee_id': employee.id,
                'policy_id': policy.id,
                'policy_line_id': policy_line.id,
                'leave_type_id': line.leave_type_id.id,
                'balance_year': line.balance_year or self.balance_year,
                'opening_balance': line.opening_balance,
                'accrued_leave': 0.0,
                'utilized_leave': 0.0,
                'closing_balance': line.opening_balance,
            }

            existing_balance = Balance.search([
                ('employee_id', '=', employee.id),
                ('policy_id', '=', policy.id),
                ('policy_line_id', '=', policy_line.id),
                ('leave_type_id', '=', line.leave_type_id.id),
                ('balance_year', '=', balance_values['balance_year']),
            ], limit=1)
            if existing_balance:
                existing_balance.write(balance_values)
                balance_record = existing_balance
            else:
                balance_record = Balance.create(balance_values)
            created_or_updated |= balance_record

            if line.opening_balance > 0:
                year = balance_values['balance_year']
                date_from = date(year, 1, 1)
                date_to = date(year, 12, 31)
                allocation_values = {
                    'employee_id': employee.id,
                    'holiday_status_id': line.leave_type_id.id,
                    'date_from': date_from,
                    'date_to': date_to,
                    'number_of_days': line.opening_balance,
                    'allocation_type': 'regular',
                    'state': 'confirm',
                    'allocation_origin': 'opening_balance',
                    'notes': line.notes or _(
                        'Imported opening balance for %(year)s.',
                        year=year,
                    ),
                    'leave_policy_id': policy.id,
                    'leave_policy_line_id': policy_line.id,
                }
                existing_allocation = Allocation.search([
                    ('employee_id', '=', employee.id),
                    ('leave_policy_id', '=', policy.id),
                    ('leave_policy_line_id', '=', policy_line.id),
                    ('holiday_status_id', '=', line.leave_type_id.id),
                    ('allocation_origin', '=', 'opening_balance'),
                    ('date_from', '=', date_from),
                ], limit=1)
                if existing_allocation:
                    existing_allocation.write(allocation_values)
                    allocation = existing_allocation
                else:
                    allocation = Allocation.with_context(mail_create_nosubscribe=True).create(allocation_values)
                if allocation.state != 'validate':
                    allocation.action_approve()
                created_allocations |= allocation

        message_parts = []
        if created_or_updated:
            message_parts.append(_('%s balance record(s) imported or updated.') % len(created_or_updated))
        if created_allocations:
            message_parts.append(_('%s opening allocation(s) created or updated.') % len(created_allocations))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Old Balances Imported'),
                'message': ' '.join(message_parts) if message_parts else _('No records were imported.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_reset_imported_balances(self):
        """Remove only the balances and allocations created by this import flow."""
        self.ensure_one()
        Balance = self.env['attendance.leave.balance'].sudo()
        Allocation = self.env['hr.leave.allocation'].sudo()
        removed_balances = 0
        removed_allocations = 0

        for line in self.line_ids:
            employee = line.employee_id
            if not employee:
                continue
            policy = line.policy_id or employee.leave_policy_id
            if not policy:
                continue
            policy_line = self._resolve_policy_line(policy, line.leave_type_id)
            if not policy_line:
                continue
            year = line.balance_year or self.balance_year
            balance_domain = [
                ('employee_id', '=', employee.id),
                ('policy_id', '=', policy.id),
                ('policy_line_id', '=', policy_line.id),
                ('leave_type_id', '=', line.leave_type_id.id),
                ('balance_year', '=', year),
            ]
            allocation_domain = [
                ('employee_id', '=', employee.id),
                ('leave_policy_id', '=', policy.id),
                ('leave_policy_line_id', '=', policy_line.id),
                ('holiday_status_id', '=', line.leave_type_id.id),
                ('allocation_origin', '=', 'opening_balance'),
                ('date_from', '=', date(year, 1, 1)),
            ]

            balances = Balance.search(balance_domain)
            allocations = Allocation.search(allocation_domain)
            removed_balances += len(balances)
            removed_allocations += len(allocations)
            allocations.filtered(lambda a: a.state in ('confirm', 'validate', 'validate1')).action_refuse()
            allocations.filtered(lambda a: a.state == 'refuse').unlink()
            balances.unlink()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Imported Balances Reset'),
                'message': _('%s balance record(s) and %s opening allocation(s) were removed.') % (removed_balances, removed_allocations),
                'type': 'warning',
                'sticky': False,
            },
        }

    def _resolve_csv_employee(self, normalized_row):
        Employee = self.env['hr.employee'].sudo()
        employee_id_raw = normalized_row.get('employee_id')
        employee_name = normalized_row.get('employee_name')
        if employee_id_raw and str(employee_id_raw).isdigit():
            employee = Employee.search([('id', '=', int(employee_id_raw))], limit=1)
            if employee:
                return employee
        if employee_name:
            return Employee.search([
                '|',
                ('name', '=ilike', employee_name),
                ('work_email', '=ilike', employee_name),
            ], limit=1)
        return False

    def _resolve_csv_policy(self, normalized_row, employee):
        Policy = self.env['attendance.leave.policy'].sudo()
        policy_id_raw = normalized_row.get('policy_id')
        policy_name = normalized_row.get('policy_name')
        if policy_id_raw and str(policy_id_raw).isdigit():
            policy = Policy.search([('id', '=', int(policy_id_raw))], limit=1)
            if policy:
                return policy
        if policy_name:
            company_id = employee.company_id.id if employee else self.company_id.id
            return Policy.search([
                ('company_id', '=', company_id),
                '|',
                ('name', '=ilike', policy_name),
                ('attendance_category', '=', employee.attendance_category if employee else False),
            ], limit=1)
        return employee.leave_policy_id if employee else False

    def _resolve_csv_leave_type(self, normalized_row):
        LeaveType = self.env['hr.leave.type'].sudo()
        company_domain = ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]
        leave_type_id_raw = normalized_row.get('leave_type_id')
        leave_type_code = normalized_row.get('leave_type_code')
        leave_type_name = normalized_row.get('leave_type_name')
        if leave_type_id_raw and str(leave_type_id_raw).isdigit():
            leave_type = LeaveType.search(company_domain + [('id', '=', int(leave_type_id_raw))], limit=1)
            if leave_type:
                return leave_type
        if leave_type_code:
            leave_type = LeaveType.search(company_domain + [('code', '=ilike', leave_type_code)], limit=1) if 'code' in LeaveType._fields else False
            if leave_type:
                return leave_type
        if leave_type_name:
            return LeaveType.search(company_domain + [('name', '=ilike', leave_type_name)], limit=1)
        return False

    def _resolve_csv_year(self, normalized_row):
        year_raw = normalized_row.get('balance_year') or normalized_row.get('year')
        if year_raw and str(year_raw).strip().isdigit():
            return int(year_raw)
        return self.balance_year

    def _resolve_csv_float(self, normalized_row, key):
        value = normalized_row.get(key)
        try:
            return float(value) if value not in (None, '') else 0.0
        except (TypeError, ValueError):
            raise ValidationError(_('Invalid numeric value for %s in CSV.') % key)

    def _resolve_policy_line(self, policy, leave_type):
        """Match an imported leave type to the best policy line.

        We first try an exact leave type match. If that fails, we fall back to
        the policy line that represents the same logical leave bucket, such as
        earned leave / paid leave aliases.
        """
        self.ensure_one()
        exact_line = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id.id == leave_type.id)[:1]
        if exact_line:
            return exact_line

        leave_name = (leave_type.sudo().name or '').strip().lower()
        leave_code = (getattr(leave_type, 'code', '') or '').strip().lower()

        earned_aliases = {
            'earned leave', 'earned leaves', 'paid leave', 'paid time off', 'pto',
            'el', 'el1', 'pl', 'paid leave balance',
        }
        casual_aliases = {'casual leave', 'casual', 'cl', 'cl1'}
        sick_aliases = {'sick leave', 'sick time off', 'sick', 'sl', 'sl1'}
        unpaid_aliases = {'unpaid leave', 'unpaid', 'unp', 'unp1', 'pl1'}
        maternity_aliases = {'maternity leave', 'maternity / paternity leave', 'mat', 'ml1'}
        comp_off_aliases = {'compensatory off', 'compensatory days', 'co', 'co1'}

        aliases_by_mode = {
            'earned': earned_aliases,
            'allocation': casual_aliases | sick_aliases | unpaid_aliases | maternity_aliases,
            'comp_off': comp_off_aliases,
        }

        for mode, aliases in aliases_by_mode.items():
            if leave_name in aliases or leave_code in aliases:
                return policy.line_ids.filtered(lambda l: l.active and l.allocation_mode == mode)[:1]

        return policy.line_ids.filtered(lambda l: l.active and l.leave_type_id and (
            (l.leave_type_id.sudo().name or '').strip().lower() == leave_name
            or (getattr(l.leave_type_id, 'code', '') or '').strip().lower() == leave_code
        ))[:1]


class AttendanceLeaveBalanceImportWizardLine(models.TransientModel):
    _name = 'attendance.leave.balance.import.wizard.line'
    _description = 'Import Old Leave Balance Line'
    _order = 'wizard_id, employee_id, leave_type_id'

    wizard_id = fields.Many2one(
        'attendance.leave.balance.import.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(related='wizard_id.company_id', store=False, readonly=True)
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        domain="[('company_id', '=', company_id)]",
    )
    policy_id = fields.Many2one(
        'attendance.leave.policy',
        string='Leave Policy',
        domain="[('company_id', '=', company_id)]",
    )
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        required=True,
        domain="[('company_id', 'in', [False, company_id])]",
    )
    balance_year = fields.Integer(
        string='Balance Year',
        default=lambda self: fields.Date.today().year,
        required=True,
    )
    opening_balance = fields.Float(
        string='Balance',
        required=True,
        help='Imported leave count. It will be stored as opening balance and opening allocation.',
    )
    notes = fields.Char(string='Notes')

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        for line in self:
            if line.employee_id and not line.policy_id:
                line.policy_id = line.employee_id.leave_policy_id
