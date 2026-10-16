# -*- coding: utf-8 -*-

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AttendanceLeavePolicy(models.Model):
    _name = 'attendance.leave.policy'
    _description = 'Attendance Leave Policy'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'company_id, attendance_category, name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        tracking=True,
    )
    attendance_category = fields.Selection([
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], string='Attendance Category', required=True, tracking=True)
    earned_leave_min_service_months = fields.Integer(
        string='Earned Leave Eligibility After Service (Months)',
        default=12,
        help='Earned leave becomes eligible after joining date plus this many months.',
    )
    maternity_min_worked_days_last_12_months = fields.Integer(
        string='Maternity Eligibility After Worked Days',
        default=80,
        help='Maternity leave is generated only after the employee has worked this many days in the last 12 months.',
    )
    new_joiner_service_months_limit = fields.Integer(
        string='New Joiner Limit (Months)',
        default=6,
        help='For the first N months from joining, apply the new-joiner leave cap.',
    )
    new_joiner_monthly_leave_limit = fields.Float(
        string='New Joiner Leave Limit / Month',
        default=1.0,
        help='Maximum number of leaves allowed in one month for new joiners.',
    )
    rule_note = fields.Text(
        string='Leave Structure',
        help='Company leave structure applied by this policy.',
    )
    employee_count = fields.Integer(compute='_compute_employee_count', string='Employees')
    line_ids = fields.One2many(
        'attendance.leave.policy.line',
        'policy_id',
        string='Leave Rules',
        copy=True,
    )

    _sql_constraints = [
        (
            'policy_company_category_unique',
            'unique(company_id, attendance_category, name)',
            'A leave policy with the same company, category, and name already exists.',
        ),
    ]

    @api.depends('company_id', 'attendance_category')
    def _compute_employee_count(self):
        Employee = self.env['hr.employee'].sudo()
        for policy in self:
            policy.employee_count = Employee.search_count([
                ('company_id', '=', policy.company_id.id),
                ('attendance_category', '=', policy.attendance_category),
                ('active', '=', True),
            ])

    def _get_target_employees(self, company=None, category=None):
        self.ensure_one()
        company = company or self.company_id
        category = category or self.attendance_category
        return self.env['hr.employee'].sudo().search([
            ('company_id', '=', company.id),
            ('attendance_category', '=', category),
            ('active', '=', True),
        ])

    def _get_employee_service_months(self, employee, target_date=None):
        """Return completed months of service based on contract start date."""
        self.ensure_one()
        target_date = target_date or fields.Date.context_today(self)
        start_date = employee.contract_date_start
        if not start_date and 'joining_date' in employee._fields:
            start_date = employee.joining_date
        if not start_date:
            return 0
        months = (target_date.year - start_date.year) * 12 + (target_date.month - start_date.month)
        if target_date.day < start_date.day:
            months -= 1
        return max(months, 0)

    def _get_employee_joining_date(self, employee):
        """Return the best available joining/start date for the employee."""
        self.ensure_one()
        for field_name in ('contract_date_start', 'joining_date'):
            if field_name in employee._fields:
                value = employee[field_name]
                if value:
                    return value
        return False

    def _get_employee_policy_activation_date(self, employee):
        """Return the date from which normal company policy should apply."""
        self.ensure_one()
        probation_end_date = getattr(employee, 'probation_end_date', False)
        if probation_end_date:
            return probation_end_date
        joining_date = self._get_employee_joining_date(employee)
        if not joining_date:
            return False
        return self._add_months_to_date(
            joining_date,
            self.new_joiner_service_months_limit or 6,
        )

    def _get_probation_allocation_amount(self, line):
        """Return the provisional allocation amount used during probation."""
        self.ensure_one()
        monthly_limit = self.new_joiner_monthly_leave_limit or 0.0
        probation_months = self.new_joiner_service_months_limit or 0
        if monthly_limit <= 0 or probation_months <= 0:
            return 0.0
        provisional_days = monthly_limit * probation_months
        if line.annual_days:
            provisional_days = min(provisional_days, line.annual_days)
        return round(provisional_days, 2)

    def _get_probation_allocation_lines(self, employee):
        """Return leave policy lines eligible for provisional probation allocations."""
        self.ensure_one()
        lines = self.sudo().line_ids.filtered(lambda l: (
            l.active
            and l.leave_type_id
            and l.allocation_mode == 'allocation'
            and l.annual_days > 0
            and l._is_applicable_to_employee(employee)
        ))
        # Recompute the stored leave-type flag before filtering existing data.
        # This covers leave types whose name/code was changed before an upgrade.
        for leave_type in lines.mapped('leave_type_id').sudo():
            if 'probation_allowed_type' in leave_type._fields:
                leave_type._compute_probation_allowed_type()
        return lines.filtered(lambda l: (
            getattr(l.leave_type_id, 'probation_allowed_type', False)
        ))

    def _cleanup_probation_allocations_for_employee(self, employee):
        """Remove provisional probation allocations for an employee."""
        self.ensure_one()
        Allocation = self.env['hr.leave.allocation'].sudo()
        probation_allocations = Allocation.search([
            ('leave_policy_id', '=', self.id),
            ('employee_id', '=', employee.id),
            ('allocation_origin', '=', 'probation'),
        ])
        if probation_allocations:
            probation_allocations.filtered(lambda a: a.state in ('confirm', 'validate', 'validate1')).action_refuse()
            probation_allocations.filtered(lambda a: a.state == 'refuse').unlink()
        return probation_allocations

    def _create_probation_allocations_for_employee(self, employee, year=None):
        """Create provisional allocations valid only through probation."""
        self.ensure_one()
        Allocation = self.env['hr.leave.allocation'].sudo()
        year = year or fields.Date.today().year
        date_from = date(year, 1, 1)
        date_to = date(year, 12, 31)
        probation_end_date = self._get_employee_policy_activation_date(employee)
        if probation_end_date:
            date_to = min(date_to, probation_end_date)
        created_allocations = Allocation.browse()

        for line in self._get_probation_allocation_lines(employee):
            existing_allocations = Allocation.search([
                ('leave_policy_id', '=', self.id),
                ('leave_policy_line_id', '=', line.id),
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', line.leave_type_id.id),
                ('allocation_origin', '=', 'probation'),
                ('date_from', '=', date_from),
            ])
            if existing_allocations:
                existing_allocations.filtered(
                    lambda allocation: allocation.date_to != date_to
                ).write({'date_to': date_to})
                continue
            allocation_days = self._get_probation_allocation_amount(line)
            if allocation_days <= 0:
                continue
            allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                'employee_id': employee.id,
                'holiday_status_id': line.leave_type_id.id,
                'date_from': date_from,
                'date_to': date_to,
                'number_of_days': allocation_days,
                'allocation_type': 'regular',
                'state': 'confirm',
                'allocation_origin': 'probation',
                'notes': _(
                    'Probation allocation generated for %(employee)s (%(policy)s).',
                    employee=employee.name,
                    policy=self.name,
                ),
                'leave_policy_id': self.id,
                'leave_policy_line_id': line.id,
            })
            allocation.action_approve()
            created_allocations |= allocation
        return created_allocations

    def _get_carry_forward_cap_days(self, line):
        """Return the maximum balance allowed after carry forward and current-year earned allocation."""
        self.ensure_one()
        total_limit = line.carry_forward_total_limit_days or 0.0
        if total_limit <= 0:
            total_limit = 60.0
        annual_days = line.annual_days or 0.0
        return max(0.0, round(total_limit - annual_days, 2))

    def _add_months_to_date(self, base_date, months):
        """Return base_date shifted forward by a number of months."""
        if not base_date or not months:
            return base_date
        month_index = base_date.month - 1 + months
        year = base_date.year + month_index // 12
        month = month_index % 12 + 1
        day = min(base_date.day, [31,
                                  29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                                  31, 30, 31, 30,
                                  31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)

    def _get_employee_earned_leave_eligibility_date(self, employee):
        """Earned leave becomes eligible after service completion threshold."""
        self.ensure_one()
        joining_date = self._get_employee_joining_date(employee)
        if not joining_date:
            return False
        return self._add_months_to_date(joining_date, self.earned_leave_min_service_months)

    def _get_employee_worked_days_last_12_months(self, employee, target_date=None):
        """Count present working days in the last 12 months using attendance summary data."""
        self.ensure_one()
        target_date = target_date or fields.Date.context_today(self)
        start_date = target_date - relativedelta(months=12)
        summary_model = self.env['attendance.summary.analysis'].sudo()
        try:
            summary = summary_model.get_attendance_summary([employee.id], start_date, target_date)
        except Exception:
            return 0
        return sum(
            1 for rec in summary
            if rec.get('employee_id') == employee.id and rec.get('status') == 'present'
        )

    def _is_maternity_eligible(self, employee, target_date=None):
        """Maternity is full entitlement, but only after the employee worked enough days."""
        self.ensure_one()
        maternity_lines = self.line_ids.filtered(
            lambda line: line.active and line.leave_type_id and 'maternity' in (line.leave_type_id.sudo().name or '').lower()
        )
        if not maternity_lines:
            return True
        worked_days = self._get_employee_worked_days_last_12_months(employee, target_date=target_date)
        return worked_days >= self.maternity_min_worked_days_last_12_months

    def _compute_prorated_annual_days(self, annual_days, year, start_date=None, end_date=None):
        """Prorate annual leave within a calendar year based on eligible service days."""
        if not annual_days:
            return 0.0
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        period_start = max(start_date or year_start, year_start)
        period_end = min(end_date or year_end, year_end)
        if period_start > period_end:
            return 0.0
        total_days = (year_end - year_start).days + 1
        eligible_days = (period_end - period_start).days + 1
        return round(annual_days * eligible_days / total_days, 2)

    def action_generate_yearly_allocations(self, year=None):
        """Generate draft allocations for matching employees.

        The allocations are created as normal Odoo time-off allocations.
        If a leave type is configured for auto-validation in Odoo, the
        native create flow will validate it automatically.
        """
        Allocation = self.env['hr.leave.allocation'].sudo()
        year = year or fields.Date.today().year
        date_from = date(year, 1, 1)
        date_to = date(year, 12, 31)
        today = fields.Date.context_today(self)
        created_allocations = Allocation.browse()

        for policy in self:
            policy = policy.sudo()
            employees = policy._get_target_employees()
            fixed_lines = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'allocation' and l.annual_days > 0)
            earned_lines = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'earned' and l.annual_days > 0)
            comp_off_lines = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'comp_off' and l.comp_off_days_per_worked_day > 0)

            for employee in employees:
                activation_date = policy._get_employee_policy_activation_date(employee)
                policy_active = not activation_date or today >= activation_date
                employee_fixed_lines = fixed_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
                employee_earned_lines = earned_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
                employee_comp_off_lines = comp_off_lines.filtered(lambda l: l._is_applicable_to_employee(employee))

                if not policy_active:
                    created_allocations |= policy._create_probation_allocations_for_employee(employee, year=year)
                    continue

                policy._cleanup_probation_allocations_for_employee(employee)

                for line in employee_fixed_lines:
                    leave_name = (line.leave_type_id.sudo().name or '').lower()
                    if 'maternity' in leave_name:
                        continue
                    joining_date = activation_date or policy._get_employee_joining_date(employee)
                    prorate = line.allocation_mode == 'allocation' and line.gender_applicability == 'all'
                    allocation_days = line.annual_days
                    if prorate and joining_date:
                        allocation_days = policy._compute_prorated_annual_days(line.annual_days, year, joining_date, date_to)
                    existing = Allocation.search_count([
                        ('leave_policy_id', '=', policy.id),
                        ('leave_policy_line_id', '=', line.id),
                        ('employee_id', '=', employee.id),
                        ('holiday_status_id', '=', line.leave_type_id.id),
                        ('date_from', '=', date_from),
                    ])
                    if existing:
                        continue

                    allocation_vals = {
                        'employee_id': employee.id,
                        'holiday_status_id': line.leave_type_id.id,
                        'date_from': date_from,
                        'date_to': date_to,
                        'number_of_days': allocation_days,
                        'allocation_type': 'regular',
                        'state': 'confirm',
                        'allocation_origin': 'fixed',
                        'notes': _('Auto-generated from policy %(policy)s (%(category)s)',
                                   policy=policy.name,
                                   category=policy.attendance_category),
                        'leave_policy_id': policy.id,
                        'leave_policy_line_id': line.id,
                    }
                    allocation = Allocation.with_context(mail_create_nosubscribe=True).create(allocation_vals)
                    allocation.action_approve()
                    created_allocations |= allocation

            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            for employee in employees:
                activation_date = policy._get_employee_policy_activation_date(employee)
                policy_active = not activation_date or today >= activation_date
                service_months = policy._get_employee_service_months(employee, today)
                earned_eligibility_date = policy._get_employee_earned_leave_eligibility_date(employee)
                employee_earned_lines = earned_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
                employee_comp_off_lines = comp_off_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
                earned_leave_eligible = bool(employee_earned_lines) and (
                    earned_eligibility_date
                    and today >= earned_eligibility_date
                    or (not earned_eligibility_date and service_months >= policy.earned_leave_min_service_months)
                )
                if earned_leave_eligible:
                    for line in employee_earned_lines:
                        earned_start_date = earned_eligibility_date or policy._get_employee_joining_date(employee)
                        allocation_days = line.annual_days
                        if earned_start_date:
                            allocation_days = policy._compute_prorated_annual_days(line.annual_days, year, earned_start_date, year_end)
                        existing = Allocation.search_count([
                            ('leave_policy_id', '=', policy.id),
                            ('leave_policy_line_id', '=', line.id),
                            ('employee_id', '=', employee.id),
                            ('holiday_status_id', '=', line.leave_type_id.id),
                            ('date_from', '=', year_start),
                        ])
                        if existing:
                            continue
                        allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                            'employee_id': employee.id,
                            'holiday_status_id': line.leave_type_id.id,
                            'date_from': year_start,
                            'date_to': year_end,
                            'number_of_days': allocation_days,
                            'allocation_type': 'regular',
                            'state': 'confirm',
                            'allocation_origin': 'earned',
                            'notes': _(
                                'Earned leave generated for %(year)s after service completion.',
                                year=year,
                            ),
                            'leave_policy_id': policy.id,
                            'leave_policy_line_id': line.id,
                        })
                        allocation.action_approve()
                        created_allocations |= allocation

                employee_maternity_lines = fixed_lines.filtered(
                    lambda l: l._is_applicable_to_employee(employee)
                    and 'maternity' in (l.leave_type_id.sudo().name or '').lower()
                )
                if policy_active and employee_maternity_lines and policy._is_maternity_eligible(employee, today):
                    for line in employee_maternity_lines:
                        allocation_days = line.annual_days
                        existing = Allocation.search_count([
                            ('leave_policy_id', '=', policy.id),
                            ('leave_policy_line_id', '=', line.id),
                            ('employee_id', '=', employee.id),
                            ('holiday_status_id', '=', line.leave_type_id.id),
                            ('date_from', '=', date_from),
                        ])
                        if existing:
                            continue
                        allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                            'employee_id': employee.id,
                            'holiday_status_id': line.leave_type_id.id,
                            'date_from': date_from,
                            'date_to': date_to,
                            'number_of_days': allocation_days,
                            'allocation_type': 'regular',
                            'state': 'confirm',
                            'allocation_origin': 'fixed',
                            'notes': _(
                                'Maternity leave generated after 80 worked days in the last 12 months.'
                            ),
                            'leave_policy_id': policy.id,
                            'leave_policy_line_id': line.id,
                        })
                        allocation.action_approve()
                        created_allocations |= allocation

                if policy_active and employee_comp_off_lines:
                    prev_month_end = today.replace(day=1) - timedelta(days=1)
                    prev_month_start = prev_month_end.replace(day=1)
                    comp_days = policy._count_comp_off_days(employee, prev_month_start, prev_month_end)
                    grant_date = today.replace(day=1)
                    for line in employee_comp_off_lines:
                        comp_off_days = comp_days * line.comp_off_days_per_worked_day
                        if comp_off_days <= 0:
                            continue
                        comp_from, comp_to = policy._comp_off_allocation_period(line, grant_date)
                        if Allocation.search_count([
                            ('leave_policy_id', '=', policy.id),
                            ('leave_policy_line_id', '=', line.id),
                            ('employee_id', '=', employee.id),
                            ('holiday_status_id', '=', line.leave_type_id.id),
                            ('date_from', '=', comp_from),
                        ]):
                            continue
                        allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                            'employee_id': employee.id,
                            'holiday_status_id': line.leave_type_id.id,
                            'date_from': comp_from,
                            'date_to': comp_to,
                            'number_of_days': comp_off_days,
                            'allocation_type': 'regular',
                            'state': 'confirm',
                            'allocation_origin': 'comp_off',
                            'notes': _(
                                'Comp-off generated from %(days)s qualifying work day(s) during %(period)s',
                                days=comp_days,
                                period=prev_month_start.strftime('%B %Y'),
                            ),
                            'leave_policy_id': policy.id,
                            'leave_policy_line_id': line.id,
                        })
                        allocation.action_approve()
                        created_allocations |= allocation

        self.action_refresh_leave_balances(year=year)
        return created_allocations

    def action_generate_yearly_allocations_for_employee(self, employee, year=None):
        """Generate allocations only for one employee."""
        self.ensure_one()
        self = self.sudo()
        employee = employee.sudo()
        Allocation = self.env['hr.leave.allocation'].sudo()
        year = year or fields.Date.today().year
        date_from = date(year, 1, 1)
        date_to = date(year, 12, 31)
        today = fields.Date.context_today(self)
        created_allocations = Allocation.browse()

        fixed_lines = self.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'allocation' and l.annual_days > 0)
        earned_lines = self.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'earned' and l.annual_days > 0)
        comp_off_lines = self.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'comp_off' and l.comp_off_days_per_worked_day > 0)

        employee_fixed_lines = fixed_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
        employee_earned_lines = earned_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
        employee_comp_off_lines = comp_off_lines.filtered(lambda l: l._is_applicable_to_employee(employee))
        activation_date = self._get_employee_policy_activation_date(employee)
        policy_active = not activation_date or today >= activation_date

        if not policy_active:
            created_allocations |= self._create_probation_allocations_for_employee(employee, year=year)
            self.action_refresh_leave_balances(year=year)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Probation Allocations Created'),
                    'message': _(
                        'Small probation leave allocations were created for %(employee)s. Normal policy allocations will start after %(date)s.'
                    ) % {
                        'employee': employee.name,
                        'date': fields.Date.to_string(activation_date) if activation_date else _('probation ends'),
                    },
                    'type': 'success',
                    'sticky': False,
                },
            }

        self._cleanup_probation_allocations_for_employee(employee)

        for line in employee_fixed_lines:
            leave_name = (line.leave_type_id.sudo().name or '').lower()
            if 'maternity' in leave_name:
                continue
            joining_date = activation_date or self._get_employee_joining_date(employee)
            prorate = line.allocation_mode == 'allocation' and line.gender_applicability == 'all'
            allocation_days = line.annual_days
            if prorate and joining_date:
                allocation_days = self._compute_prorated_annual_days(line.annual_days, year, joining_date, date_to)
            existing = Allocation.search_count([
                ('leave_policy_id', '=', self.id),
                ('leave_policy_line_id', '=', line.id),
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', line.leave_type_id.id),
                ('date_from', '=', date_from),
            ])
            if existing:
                continue
            allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                'employee_id': employee.id,
                'holiday_status_id': line.leave_type_id.id,
                'date_from': date_from,
                'date_to': date_to,
                'number_of_days': allocation_days,
                'allocation_type': 'regular',
                'state': 'confirm',
                'allocation_origin': 'fixed',
                'notes': _('Auto-generated from policy %(policy)s (%(category)s)',
                           policy=self.name,
                           category=self.attendance_category),
                'leave_policy_id': self.id,
                'leave_policy_line_id': line.id,
            })
            allocation.action_approve()
            created_allocations |= allocation

        today = fields.Date.context_today(self)
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        service_months = self._get_employee_service_months(employee, today)
        earned_eligibility_date = self._get_employee_earned_leave_eligibility_date(employee)
        earned_leave_eligible = bool(employee_earned_lines) and (
            earned_eligibility_date
            and today >= earned_eligibility_date
            or (not earned_eligibility_date and service_months >= self.earned_leave_min_service_months)
        )
        if earned_leave_eligible:
            for line in employee_earned_lines:
                earned_start_date = earned_eligibility_date or self._get_employee_joining_date(employee)
                allocation_days = line.annual_days
                if earned_start_date:
                    allocation_days = self._compute_prorated_annual_days(line.annual_days, year, earned_start_date, year_end)
                existing = Allocation.search_count([
                    ('leave_policy_id', '=', self.id),
                    ('leave_policy_line_id', '=', line.id),
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', line.leave_type_id.id),
                    ('date_from', '=', year_start),
                ])
                if existing:
                    continue
                allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                    'employee_id': employee.id,
                    'holiday_status_id': line.leave_type_id.id,
                    'date_from': year_start,
                    'date_to': year_end,
                    'number_of_days': allocation_days,
                    'allocation_type': 'regular',
                    'state': 'confirm',
                    'allocation_origin': 'earned',
                    'notes': _(
                        'Earned leave generated for %(year)s after service completion.',
                        year=year,
                    ),
                    'leave_policy_id': self.id,
                    'leave_policy_line_id': line.id,
                })
                allocation.action_approve()
                created_allocations |= allocation

        employee_maternity_lines = fixed_lines.filtered(
            lambda l: l._is_applicable_to_employee(employee)
            and 'maternity' in (l.leave_type_id.sudo().name or '').lower()
        )
        if policy_active and employee_maternity_lines and self._is_maternity_eligible(employee, today):
            for line in employee_maternity_lines:
                allocation_days = line.annual_days
                existing = Allocation.search_count([
                    ('leave_policy_id', '=', self.id),
                    ('leave_policy_line_id', '=', line.id),
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', line.leave_type_id.id),
                    ('date_from', '=', date_from),
                ])
                if existing:
                    continue
                allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                    'employee_id': employee.id,
                    'holiday_status_id': line.leave_type_id.id,
                    'date_from': date_from,
                    'date_to': date_to,
                    'number_of_days': allocation_days,
                    'allocation_type': 'regular',
                    'state': 'confirm',
                    'allocation_origin': 'fixed',
                    'notes': _(
                        'Maternity leave generated after 80 worked days in the last 12 months.'
                    ),
                    'leave_policy_id': self.id,
                    'leave_policy_line_id': line.id,
                })
                allocation.action_approve()
                created_allocations |= allocation

        if policy_active and employee_comp_off_lines:
            prev_month_end = today.replace(day=1) - timedelta(days=1)
            prev_month_start = prev_month_end.replace(day=1)
            comp_days = self._count_comp_off_days(employee, prev_month_start, prev_month_end)
            grant_date = today.replace(day=1)
            for line in employee_comp_off_lines:
                comp_off_days = comp_days * line.comp_off_days_per_worked_day
                if comp_off_days <= 0:
                    continue
                comp_from, comp_to = self._comp_off_allocation_period(line, grant_date)
                if Allocation.search_count([
                    ('leave_policy_id', '=', self.id),
                    ('leave_policy_line_id', '=', line.id),
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', line.leave_type_id.id),
                    ('date_from', '=', comp_from),
                ]):
                    continue
                allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                    'employee_id': employee.id,
                    'holiday_status_id': line.leave_type_id.id,
                    'date_from': comp_from,
                    'date_to': comp_to,
                    'number_of_days': comp_off_days,
                    'allocation_type': 'regular',
                    'state': 'confirm',
                    'allocation_origin': 'comp_off',
                    'notes': _(
                        'Comp-off generated from %(days)s qualifying work day(s) during %(period)s',
                        days=comp_days,
                        period=prev_month_start.strftime('%B %Y'),
                    ),
                    'leave_policy_id': self.id,
                    'leave_policy_line_id': line.id,
                })
                allocation.action_approve()
                created_allocations |= allocation

        self.action_refresh_leave_balances(year=year)
        return created_allocations

    def action_reset_generated_allocations_for_employee(self, employee):
        """Remove generated allocations for one employee under this policy."""
        self.ensure_one()
        self = self.sudo()
        employee = employee.sudo()
        Allocation = self.env['hr.leave.allocation'].sudo()
        allocations = Allocation.search([
            ('leave_policy_id', '=', self.id),
            ('employee_id', '=', employee.id),
            ('allocation_origin', 'in', ['fixed', 'earned', 'comp_off', 'carry_forward', 'probation']),
        ])
        removed_count = len(allocations)
        if allocations:
            # Approved allocations cannot be deleted directly, so first refuse
            # them, then remove the refused records in one step.
            allocations.filtered(lambda a: a.state in ('confirm', 'validate', 'validate1')).action_refuse()
            allocations.filtered(lambda a: a.state == 'refuse').unlink()
        self.action_refresh_leave_balances()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Allocations Reset'),
                'message': _('%s generated allocation(s) were removed for %s.') % (removed_count, employee.name),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_generate_carry_forward_allocations(self, year=None):
        """Carry forward unused earned leave into the new year."""
        Allocation = self.env['hr.leave.allocation'].sudo()
        year = year or fields.Date.today().year
        prev_year_end = date(year - 1, 12, 31)
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        created_allocations = Allocation.browse()

        for policy in self:
            employees = policy._get_target_employees()
            earned_lines = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'earned' and l.carry_forward_enabled)
            for employee in employees:
                for line in earned_lines.filtered(lambda l: l._is_applicable_to_employee(employee)):
                    remaining = policy._get_leave_balance(employee, line.leave_type_id, prev_year_end)
                    if remaining <= 0:
                        continue
                    carry_days = remaining
                    carry_cap = policy._get_carry_forward_cap_days(line)
                    if carry_cap > 0:
                        carry_days = min(carry_days, carry_cap)
                    if line.carry_forward_limit_days > 0:
                        carry_days = min(carry_days, line.carry_forward_limit_days)
                    if carry_days <= 0:
                        continue
                    existing = Allocation.search_count([
                        ('employee_id', '=', employee.id),
                        ('holiday_status_id', '=', line.leave_type_id.id),
                        ('leave_policy_id', '=', policy.id),
                        ('leave_policy_line_id', '=', line.id),
                        ('date_from', '=', year_start),
                    ])
                    if existing:
                        continue
                    allocation = Allocation.with_context(mail_create_nosubscribe=True).create({
                        'employee_id': employee.id,
                        'holiday_status_id': line.leave_type_id.id,
                        'date_from': year_start,
                        'date_to': year_end,
                        'number_of_days': carry_days,
                        'allocation_type': 'regular',
                        'state': 'confirm',
                        'allocation_origin': 'carry_forward',
                        'notes': _(
                            'Carry forward from %(year)s for %(policy)s',
                            year=year - 1,
                            policy=policy.name,
                        ),
                        'leave_policy_id': policy.id,
                        'leave_policy_line_id': line.id,
                    })
                    allocation.action_approve()
                    created_allocations |= allocation
        self.action_refresh_leave_balances(year=year)
        return created_allocations

    def action_refresh_leave_balances(self, year=None):
        """Recompute balance summary lines for employees covered by these policies."""
        Balance = self.env['attendance.leave.balance'].sudo()
        year = year or fields.Date.today().year
        created_or_updated = Balance.browse()

        for policy in self:
            policy = policy.sudo()
            employees = policy._get_target_employees()
            lines = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id)
            for employee in employees:
                for line in lines.filtered(lambda l: l._is_applicable_to_employee(employee)):
                    values = policy._compute_leave_balance_values(employee, line, year)
                    existing = Balance.search([
                        ('employee_id', '=', employee.id),
                        ('policy_line_id', '=', line.id),
                        ('balance_year', '=', year),
                    ], limit=1)
                    if existing:
                        existing.write(values)
                        created_or_updated |= existing
                    else:
                        created_or_updated |= Balance.create(values)
        return created_or_updated

    def _compute_leave_balance_values(self, employee, line, year):
        """Return opening/accrued/utilized/closing values for one employee and leave type."""
        self = self.sudo()
        Allocation = self.env['hr.leave.allocation'].sudo()
        Leave = self.env['hr.leave'].sudo()
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        prior_year_end = date(year - 1, 12, 31)

        opening_domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', line.leave_type_id.id),
            ('leave_policy_id', '=', self.id),
            ('leave_policy_line_id', '=', line.id),
            ('allocation_origin', 'in', ['carry_forward', 'opening_balance']),
            ('state', '=', 'validate'),
            ('date_from', '>=', year_start),
            ('date_from', '<=', year_end),
        ]
        accrued_domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', line.leave_type_id.id),
            ('leave_policy_id', '=', self.id),
            ('leave_policy_line_id', '=', line.id),
            ('allocation_origin', 'in', ['fixed', 'earned', 'comp_off', 'probation']),
            ('state', '=', 'validate'),
            ('date_from', '>=', year_start),
            ('date_from', '<=', year_end),
        ]
        utilized_domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', line.leave_type_id.id),
            ('state', '=', 'validate'),
            ('request_date_from', '>=', year_start),
            ('request_date_from', '<=', year_end),
        ]
        opening = sum(Allocation.search(opening_domain).mapped('number_of_days'))
        if not opening:
            opening = max(0.0, self._get_leave_balance(employee, line.leave_type_id, prior_year_end))
        accrued = sum(Allocation.search(accrued_domain).mapped('number_of_days'))
        utilized = sum(Leave.search(utilized_domain).mapped('number_of_days'))
        closing = opening + accrued - utilized
        return {
            'name': f'{employee.name} - {line.leave_type_id.sudo().name} - {year}',
            'employee_id': employee.id,
            'policy_id': self.id,
            'policy_line_id': line.id,
            'leave_type_id': line.leave_type_id.id,
            'balance_year': year,
            'opening_balance': opening,
            'accrued_leave': accrued,
            'utilized_leave': utilized,
            'closing_balance': closing,
        }

    def action_reset_generated_allocations(self):
        """Remove allocations generated by this policy so they can be rebuilt."""
        Allocation = self.env['hr.leave.allocation'].sudo()
        removed_count = 0
        for policy in self:
            policy = policy.sudo()
            allocations = Allocation.search([
                ('leave_policy_id', '=', policy.id),
                ('allocation_origin', 'in', ['fixed', 'earned', 'comp_off', 'carry_forward', 'probation']),
            ])
            removed_count += len(allocations)
            allocations.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Allocations Reset'),
                'message': _('%s generated allocation(s) were removed. You can generate them again now.') % removed_count,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_rebuild_policy_lines(self):
        """Rebuild policy lines from existing leave types in the database."""
        self.ensure_one()
        self._sync_policy_lines_from_standard_specs(self)
        self.with_context(
            tracking_disable=True,
            mail_notrack=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
        ).write({'line_ids': []})
        self._refresh_demo_leave_type_rules()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Policy Rebuilt'),
                'message': _('Policy lines were rebuilt from existing leave types.'),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def _repair_inaccessible_policy_leave_types(self):
        """Re-link policy lines that point to leave types outside the policy company.

        These records can be left behind by demo data or older module versions and
        will trigger access errors when the policy form is opened.
        """
        lines = self.env['attendance.leave.policy.line'].sudo().search([
            ('leave_type_id', '!=', False),
            ('policy_id.company_id', '!=', False),
        ])
        if not lines:
            return

        for line in lines:
            try:
                leave_type = line.leave_type_id.sudo()
                policy_company = line.company_id
                if not leave_type or not policy_company:
                    continue
                if not leave_type.company_id or leave_type.company_id == policy_company:
                    continue

                replacement = self._find_demo_leave_type(
                    codes=[leave_type.code] if 'code' in leave_type._fields and leave_type.code else [],
                    names=[leave_type.name] if leave_type.name else [],
                    company=policy_company,
                )
                if replacement and replacement != leave_type:
                    line.with_context(
                        tracking_disable=True,
                        mail_notrack=True,
                        mail_create_nolog=True,
                        mail_create_nosubscribe=True,
                    ).write({'leave_type_id': replacement.id})
                if 'maternity' in (leave_type.name or '').lower() and line.gender_applicability != 'female':
                    line.with_context(
                        tracking_disable=True,
                        mail_notrack=True,
                        mail_create_nolog=True,
                        mail_create_nosubscribe=True,
                    ).write({'gender_applicability': 'female'})
            except Exception:
                # Never block registry load because of a bad legacy record.
                continue

    @api.model
    def _standard_leave_structure_note(self):
        return _(
            "Leave year: 1 January to 31 December.\n"
            "Sick Leave (SL): 12 days per year. Not carried forward.\n"
            "Casual Leave (CL): 6 days per year. Not carried forward.\n"
            "Earned Leave (EL): 15 days after 1 year of service. Carry forward up to 60 days.\n"
            "New joiner, first 6 months: maximum 1 leave per month.\n"
            "New joiner, after 6 months: normal leave entitlement.\n"
            "Maternity Leave: 26 weeks (182 days) after 80 days worked in the last 12 months. Paid. Not auto-credited.\n"
            "Paternity Leave: not applicable.\n"
            "Compensatory Off: for work on weekly offs or holidays. Valid for 1 year from the date it is allocated. Paid.\n"
            "Festival Leave: company holiday list. Not a leave balance.\n"
            "WFH / Remote: not applicable.\n"
            "Unpaid Leave cuts salary. Sick, Casual, Earned, Maternity and Compensatory Off do not."
        )

    @api.model
    def _leave_type_vals(self, vals):
        leave_type_model = self.env['hr.leave.type']
        return {key: value for key, value in vals.items() if key in leave_type_model._fields}

    def _comp_off_allocation_period(self, line, grant_date):
        """Comp-off is valid for one year from the date it is allocated."""
        self.ensure_one()
        months = int(line.comp_off_validity_months or 12)
        date_from = grant_date
        date_to = date_from + relativedelta(months=months) - timedelta(days=1)
        return date_from, date_to

    @api.model
    def _apply_comp_off_validity(self):
        """Set existing comp-off allocations to expire one year after they were allocated."""
        Allocation = self.env['hr.leave.allocation'].sudo()
        allocations = Allocation.search([
            ('allocation_origin', '=', 'comp_off'),
            ('date_from', '!=', False),
        ])
        for allocation in allocations:
            line = allocation.leave_policy_line_id
            months = int(line.comp_off_validity_months or 12) if line else 12
            date_to = allocation.date_from + relativedelta(months=months) - timedelta(days=1)
            if allocation.date_to != date_to:
                allocation.with_context(
                    tracking_disable=True,
                    mail_notrack=True,
                    mail_create_nolog=True,
                    leave_skip_state_check=True,
                ).write({'date_to': date_to})

    @api.model
    def _replace_leave_type(self, old_type, new_type):
        """Move balances off a wrong leave type and archive it."""
        if not old_type or not new_type or old_type == new_type:
            return
        old_type = old_type.sudo()
        new_type = new_type.sudo()
        quiet = {
            'tracking_disable': True,
            'mail_notrack': True,
            'mail_create_nolog': True,
            'mail_create_nosubscribe': True,
        }
        Allocation = self.env['hr.leave.allocation'].sudo()
        Leave = self.env['hr.leave'].sudo()
        movable_ids = []
        for allocation in Allocation.search([('holiday_status_id', '=', old_type.id)]):
            conflict = Allocation.search_count([
                ('id', '!=', allocation.id),
                ('employee_id', '=', allocation.employee_id.id),
                ('holiday_status_id', '=', new_type.id),
                ('date_from', '=', allocation.date_from),
                ('state', '!=', 'refuse'),
            ])
            if not conflict:
                movable_ids.append(allocation.id)
        if movable_ids:
            # Keep the stored duration. An ORM write recomputes it from an
            # empty display value and turns a real balance into 0 days.
            self.env.cr.execute(
                """
                UPDATE hr_leave_allocation
                   SET holiday_status_id = %s,
                       name = %s || ' (' || trim(to_char(number_of_days, 'FM999990.00')) || ' day(s))'
                 WHERE id IN %s
                """,
                (new_type.id, new_type.name, tuple(movable_ids)),
            )
            Allocation.browse(movable_ids).invalidate_recordset(
                ['holiday_status_id', 'name'], flush=False,
            )
        leave_ids = Leave.search([('holiday_status_id', '=', old_type.id)]).ids
        if leave_ids:
            self.env.cr.execute(
                """
                UPDATE hr_leave
                   SET holiday_status_id = %s
                 WHERE id IN %s
                """,
                (new_type.id, tuple(leave_ids)),
            )
            Leave.browse(leave_ids).invalidate_recordset(['holiday_status_id'], flush=False)
        Line = self.env['attendance.leave.policy.line'].sudo()
        for line in Line.search([('leave_type_id', '=', old_type.id)]):
            sibling = line.policy_id.line_ids.filtered(
                lambda item: item.leave_type_id == new_type and item.id != line.id
            )
            if sibling:
                line.with_context(**quiet).write({'active': False})
            else:
                line.with_context(**quiet).write({'leave_type_id': new_type.id})
        Balance = self.env['attendance.leave.balance'].sudo()
        for balance in Balance.search([('leave_type_id', '=', old_type.id)]):
            conflict = Balance.search_count([
                ('id', '!=', balance.id),
                ('employee_id', '=', balance.employee_id.id),
                ('policy_id', '=', balance.policy_id.id),
                ('policy_line_id', '=', balance.policy_line_id.id),
                ('leave_type_id', '=', new_type.id),
                ('balance_year', '=', balance.balance_year),
            ])
            if conflict:
                continue
            balance.with_context(**quiet).write({'leave_type_id': new_type.id})
        if not Allocation.search_count([
            ('holiday_status_id', '=', old_type.id),
            ('state', '!=', 'refuse'),
        ]):
            old_type.with_context(**quiet).write({'active': False})

    @api.model
    def _ensure_standard_leave_types(self):
        """Create or correct the leave types used by the company structure.

        Runs on every module upgrade so the server database changes without a dump.
        """
        LeaveType = self.env['hr.leave.type'].sudo()
        company = self.env['res.company'].sudo().search([], limit=1) or self.env.company
        quiet = {
            'tracking_disable': True,
            'mail_notrack': True,
            'mail_create_nolog': True,
            'mail_create_nosubscribe': True,
        }
        if company.country_id and 'leave_short_code' in LeaveType._fields:
            foreign_codes = LeaveType.with_context(active_test=False).search([
                ('leave_short_code', 'in', ['SL', 'CL', 'EL', 'CO', 'ML', 'UL']),
                ('country_id', '!=', False),
                ('country_id', '!=', company.country_id.id),
            ])
            if foreign_codes:
                foreign_codes.with_context(**quiet).write({'leave_short_code': False})

        def upsert(codes, names, vals, create_vals=None):
            leave_type = self._find_demo_leave_type(codes, names, company=company)
            payload = self._leave_type_vals(vals)
            if leave_type:
                leave_type.with_context(**quiet).write(payload)
                return leave_type
            create_payload = self._leave_type_vals(dict(create_vals or {}, **vals))
            if company.country_id and 'country_id' not in create_payload:
                create_payload['country_id'] = company.country_id.id
            create_payload.setdefault('company_id', False)
            return LeaveType.with_context(**quiet).create(create_payload)

        common = {
            'active': True,
            'company_id': False,
            'request_unit': 'day',
            'time_type': 'leave',
        }
        sick = upsert(
            ['SL', 'SL1'],
            ['Sick Leave', 'Sick Time Off'],
            dict(common, name='Sick Leave', code='SL', leave_short_code='SL', unpaid=False,
                 requires_allocation=True, employee_requests=False, support_document=True,
                 sequence=10),
        )
        if sick and 'support_document_after_days' in sick._fields:
            sick.with_context(**quiet).write({'support_document_after_days': 3})
        casual = upsert(
            ['CL', 'CL1'],
            ['Casual Leave'],
            dict(common, name='Casual Leave', code='CL', leave_short_code='CL', unpaid=False,
                 requires_allocation=True, employee_requests=False, sequence=20),
        )
        earned = upsert(
            ['EL', 'EL1'],
            ['Earned Leave'],
            dict(common, name='Earned Leave', code='EL', leave_short_code='EL', unpaid=False,
                 requires_allocation=True, employee_requests=False, sequence=30),
        )
        comp = upsert(
            ['CO', 'CO1'],
            ['Compensatory Off', 'Compensatory Days'],
            dict(common, name='Compensatory Off', code='CO', leave_short_code='CO', unpaid=False,
                 requires_allocation=True, employee_requests=False, sequence=40),
        )
        maternity = upsert(
            ['ML', 'MAT', 'ML1'],
            ['Maternity Leave'],
            dict(common, name='Maternity Leave', code='ML', leave_short_code='ML', unpaid=False,
                 requires_allocation=False, employee_requests=False, sequence=50),
            create_vals={'leave_validation_type': 'both', 'allocation_validation_type': 'hr'},
        )
        unpaid = upsert(
            ['UL', 'UNP', 'UNP1'],
            ['Unpaid Leave', 'Unpaid'],
            dict(common, name='Unpaid Leave', code='UL', leave_short_code='UL', unpaid=True,
                 requires_allocation=False, employee_requests=False, sequence=60),
        )
        paid_time_off = self._find_demo_leave_type(['PTO'], ['Paid Time Off'], company=company)
        if paid_time_off and earned and paid_time_off != earned:
            self._replace_leave_type(paid_time_off, earned)
        kept = {record.id for record in (sick, casual, earned, comp, maternity, unpaid) if record}
        for leave_type in LeaveType.search([('active', '=', True)]):
            if leave_type.id in kept:
                continue
            if not self._find_demo_leave_type(
                [leave_type.code] if leave_type.code else [],
                [leave_type.name] if leave_type.name else [],
                company=company,
            ):
                continue
            name = (leave_type.name or '').strip().lower()
            if 'paternity' in name or 'work from home' in name or name.startswith('wfh'):
                leave_type.with_context(**quiet).write({'active': False})
        return {
            'sick': sick,
            'casual': casual,
            'earned': earned,
            'comp': comp,
            'maternity': maternity,
            'unpaid': unpaid,
        }

    @api.model
    def create_demo_policies(self):
        """Create or refresh worker and office policies from the company leave structure."""
        self._ensure_standard_leave_types()
        policies = [
            {'name': 'Worker Leave Policy', 'attendance_category': 'worker'},
            {'name': 'Office Leave Policy', 'attendance_category': 'office'},
        ]
        companies = self.env['res.company'].sudo().search([])
        if not companies:
            companies = self.env.company
        results = self.env['attendance.leave.policy']
        structure_note = self._standard_leave_structure_note()
        quiet = {
            'tracking_disable': True,
            'mail_notrack': True,
            'mail_create_nolog': True,
            'mail_create_nosubscribe': True,
        }
        for company in companies:
            for policy_vals in policies:
                policy = self.search([
                    ('name', '=', policy_vals['name']),
                    ('attendance_category', '=', policy_vals['attendance_category']),
                    ('company_id', '=', company.id),
                ], limit=1)
                vals = dict(
                    policy_vals,
                    company_id=company.id,
                    earned_leave_min_service_months=12,
                    maternity_min_worked_days_last_12_months=80,
                    new_joiner_service_months_limit=6,
                    new_joiner_monthly_leave_limit=1.0,
                    rule_note=structure_note,
                )
                if policy:
                    policy.with_context(**quiet).write(vals)
                else:
                    policy = self.with_context(**quiet).create(vals)
                self._sync_policy_lines_from_standard_specs(policy)
                results |= policy
        self._refresh_demo_leave_type_rules()
        self._apply_comp_off_validity()
        if results:
            results.with_context(**quiet).action_refresh_leave_balances()
        return results

    def _sync_policy_lines_from_standard_specs(self, policy):
        """Match standard specs to existing lines without breaking existing allocations."""
        policy = policy.sudo()
        line_specs = policy._get_standard_policy_line_specs(policy.attendance_category)
        existing_lines = policy.line_ids.filtered(lambda l: l.active)
        kept_lines = self.env['attendance.leave.policy.line']

        for line_spec in line_specs:
            leave_type = policy._find_demo_leave_type(
                line_spec.get('leave_type_codes', []),
                line_spec.get('leave_type_names', []),
                company=policy.company_id,
            )
            if not leave_type:
                continue
            values = dict(line_spec)
            values.pop('leave_type_names', None)
            values.pop('leave_type_codes', None)
            values['leave_type_id'] = leave_type.id
            values['active'] = True

            line = existing_lines.filtered(lambda l: l.leave_type_id.id == leave_type.id)[:1]
            if line:
                line.with_context(
                    tracking_disable=True,
                    mail_notrack=True,
                    mail_create_nolog=True,
                    mail_create_nosubscribe=True,
                ).write(values)
                kept_lines |= line
            else:
                kept_lines |= policy.line_ids.create(dict(values, policy_id=policy.id))

        extra_lines = existing_lines - kept_lines
        if extra_lines:
            extra_lines.with_context(
                tracking_disable=True,
                mail_notrack=True,
                mail_create_nolog=True,
                mail_create_nosubscribe=True,
            ).write({'active': False})

    @api.model
    def _get_standard_policy_line_specs(self, attendance_category):
        comp_note = (
            'For work on weekly offs or holidays. Valid for 1 year from the date it is allocated. Paid.'
        )
        return [
            {
                'sequence': 10,
                'leave_type_codes': ['EL', 'EL1'],
                'leave_type_names': ['Earned Leave'],
                'allocation_mode': 'earned',
                'gender_applicability': 'all',
                'working_days_per_leave': 15,
                'earned_days_per_unit': 1,
                'carry_forward_enabled': True,
                'carry_forward_limit_days': 0,
                'carry_forward_total_limit_days': 60,
                'encash_on_exit': True,
                'annual_days': 15,
                'notes': '15 days per calendar year after 1 year of service. Carry forward is capped at 60 days. Paid.',
            },
            {
                'sequence': 20,
                'leave_type_codes': ['CL', 'CL1'],
                'leave_type_names': ['Casual Leave'],
                'allocation_mode': 'allocation',
                'gender_applicability': 'all',
                'annual_days': 6,
                'carry_forward_enabled': False,
                'carry_forward_limit_days': 0,
                'notes': '6 days per calendar year. Not carried forward. Paid.',
            },
            {
                'sequence': 30,
                'leave_type_codes': ['SL', 'SL1'],
                'leave_type_names': ['Sick Leave', 'Sick Time Off'],
                'allocation_mode': 'allocation',
                'gender_applicability': 'all',
                'annual_days': 12,
                'carry_forward_enabled': False,
                'carry_forward_limit_days': 0,
                'notes': '12 days per calendar year. Not carried forward. Paid. Certificate after 3 days.',
            },
            {
                'sequence': 40,
                'leave_type_codes': ['ML', 'MAT', 'ML1'],
                'leave_type_names': ['Maternity Leave'],
                'allocation_mode': 'manual',
                'gender_applicability': 'female',
                'annual_days': 182,
                'carry_forward_enabled': False,
                'notes': '26 weeks (182 days) after 80 days worked in the last 12 months. Paid. Not auto-credited.',
            },
            {
                'sequence': 50,
                'leave_type_codes': ['CO', 'CO1'],
                'leave_type_names': ['Compensatory Off', 'Compensatory Days'],
                'allocation_mode': 'comp_off',
                'gender_applicability': 'all',
                'comp_off_days_per_worked_day': 1,
                'comp_off_validity_months': 12,
                'annual_days': 0,
                'carry_forward_enabled': False,
                'notes': comp_note,
            },
            {
                'sequence': 60,
                'leave_type_codes': ['UL', 'UNP', 'UNP1'],
                'leave_type_names': ['Unpaid Leave', 'Unpaid'],
                'allocation_mode': 'manual',
                'gender_applicability': 'all',
                'annual_days': 0,
                'carry_forward_enabled': False,
                'notes': 'Unpaid leave cuts salary. No allocation balance.',
            },
        ]

    @api.model
    def _find_demo_leave_type(self, codes=None, names=None, company=None):
        LeaveType = self.env['hr.leave.type'].sudo()
        codes = codes or []
        names = names or []
        company = company or self.env.company
        domain = ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        country = company.country_id
        if country:
            domain = [
                '&',
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
                '|', ('country_id', '=', False), ('country_id', '=', country.id),
            ]
        if 'code' in LeaveType._fields:
            for code in codes:
                if not code:
                    continue
                leave_type = LeaveType.search(domain + [('code', '=', code)], limit=1)
                if leave_type:
                    return leave_type
        for name in names:
            if not name:
                continue
            leave_type = LeaveType.search(domain + [('name', '=', name)], limit=1)
            if leave_type:
                return leave_type
        return False

    @api.model
    def _refresh_demo_leave_type_rules(self):
        sick_leave = self._find_demo_leave_type(['SL', 'SL1'], ['Sick Time Off', 'Sick Leave'], company=self.env.company)
        if sick_leave:
            sick_leave.with_context(
                tracking_disable=True,
                mail_notrack=True,
                mail_create_nolog=True,
                mail_create_nosubscribe=True,
            ).write({'support_document_after_days': 3, 'support_document': True})

    def action_generate_exit_encashments(self, employees, departure_date):
        """Create encashment records for unused earned leave on exit."""
        Encashment = self.env['attendance.leave.encashment'].sudo()
        created = Encashment.browse()
        for policy in self:
            encash_lines = policy.line_ids.filtered(lambda l: l.active and l.leave_type_id and l.allocation_mode == 'earned' and l.encash_on_exit)
            for employee in employees:
                for line in encash_lines.filtered(lambda l: l._is_applicable_to_employee(employee)):
                    balance = policy._get_leave_balance(employee, line.leave_type_id, departure_date)
                    if balance <= 0:
                        continue
                    existing = Encashment.search_count([
                        ('employee_id', '=', employee.id),
                        ('policy_id', '=', policy.id),
                        ('policy_line_id', '=', line.id),
                        ('departure_date', '=', departure_date),
                    ])
                    if existing:
                        continue
                    record = Encashment.create({
                        'employee_id': employee.id,
                        'company_id': employee.company_id.id,
                        'policy_id': policy.id,
                        'policy_line_id': line.id,
                        'leave_type_id': line.leave_type_id.id,
                        'departure_date': departure_date,
                        'encashment_days': balance,
                        'notes': _('Generated from unused earned leave balance.'),
                    })
                    created |= record
        return created

    def _get_leave_balance(self, employee, leave_type, target_date):
        employee_data = employee._get_consumed_leaves(leave_type, target_date, ignore_future=True)[0]
        balance = 0.0
        for allocation_data in employee_data.get(employee, {}).get(leave_type, {}).values():
            balance += allocation_data.get('virtual_remaining_leaves', 0.0)
        return balance

    def _count_present_working_days(self, employee, start_date, end_date):
        summary_model = self.env['attendance.summary.analysis'].sudo()
        summary = summary_model.get_attendance_summary([employee.id], start_date, end_date)
        return sum(1 for rec in summary if rec.get('employee_id') == employee.id and rec.get('status') == 'present')

    def _count_comp_off_days(self, employee, start_date, end_date):
        summary_model = self.env['attendance.summary.analysis'].sudo()
        Attendance = self.env['hr.attendance'].sudo()
        summary = summary_model.get_attendance_summary([employee.id], start_date, end_date)
        comp_dates = []
        for rec in summary:
            if rec.get('employee_id') != employee.id or rec.get('status') not in ('weekend', 'public_holiday'):
                continue
            day = rec['date']
            utc_start, utc_end = summary_model._get_utc_datetime_range(day)
            if Attendance.search_count([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', utc_start),
                ('check_in', '<=', utc_end),
            ]):
                comp_dates.append(day)
        return len(set(comp_dates))

    @api.model
    def cron_generate_missing_allocations(self):
        """Monthly cron to create missing policy allocations."""
        current_year = fields.Date.today().year
        policies = self.search([('active', '=', True)])
        if policies:
            policies.action_generate_yearly_allocations(year=current_year)
            if fields.Date.today().month == 1:
                policies.action_generate_carry_forward_allocations(year=current_year)
        return True


class AttendanceLeavePolicyLine(models.Model):
    _name = 'attendance.leave.policy.line'
    _description = 'Attendance Leave Policy Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    policy_id = fields.Many2one(
        'attendance.leave.policy',
        string='Policy',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(related='policy_id.company_id', store=True, readonly=True)
    attendance_category = fields.Selection(related='policy_id.attendance_category', store=True, readonly=True)
    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        required=True,
        domain="[('company_id', 'in', [False, company_id])]",
    )
    gender_applicability = fields.Selection([
        ('all', 'All Employees'),
        ('male', 'Male Only'),
        ('female', 'Female Only'),
    ], string='Applicable Gender', default='all', required=True)
    display_leave_type_name = fields.Char(
        string='Leave Type Label',
        compute='_compute_display_leave_type_name',
        store=True,
    )
    allocation_mode = fields.Selection([
        ('allocation', 'Auto Allocation'),
        ('earned', 'Earned Leave'),
        ('comp_off', 'Comp Off'),
        ('manual', 'Manual / Informational'),
    ], string='Rule Type', default='allocation', required=True)
    working_days_per_leave = fields.Float(
        string='Working Days per Leave',
        default=20.0,
        help='For Earned Leave lines, grant one leave day after this many working days.'
    )
    carry_forward_enabled = fields.Boolean(
        string='Carry Forward',
        default=True,
        help='Carry unused earned leave into the next year.'
    )
    carry_forward_limit_days = fields.Float(
        string='Carry Forward Limit',
        default=0.0,
        help='Maximum number of days to carry forward. Use 0 for no cap.'
    )
    carry_forward_total_limit_days = fields.Float(
        string='Carry Forward Total Limit',
        default=60.0,
        help='Maximum total balance allowed after carry forward for this leave type.'
    )
    earned_days_per_unit = fields.Float(
        string='Days per Earned Unit',
        default=1.0,
        help='Usually 1 leave day is generated per earned unit.'
    )
    encash_on_exit = fields.Boolean(
        string='Encash on Exit',
        default=True,
        help='Create an encashment record when the employee leaves the company.'
    )
    comp_off_days_per_worked_day = fields.Float(
        string='Comp-off Days per Work Day',
        default=1.0,
        help='How many comp-off days to generate for one qualifying weekend or holiday work day.'
    )
    comp_off_validity_months = fields.Integer(
        string='Comp-off Validity (Months)',
        default=12,
        help='A comp-off allocation stays valid for this many months from the date it is allocated.',
    )
    annual_days = fields.Float(string='Annual Days', required=True, default=0.0)
    notes = fields.Char()

    _sql_constraints = [
        (
            'policy_leave_type_unique',
            'unique(policy_id, leave_type_id)',
            'The same leave type cannot appear twice on one policy.',
        ),
        (
            'annual_days_positive',
            'check(annual_days >= 0)',
            'Annual Days cannot be negative.',
        ),
    ]

    @api.depends('leave_type_id', 'allocation_mode')
    def _compute_display_leave_type_name(self):
        for line in self:
            if line.allocation_mode == 'earned':
                line.display_leave_type_name = 'Earned Leave'
            elif line.allocation_mode == 'comp_off':
                line.display_leave_type_name = 'Compensatory Off'
            elif line.leave_type_id:
                line.display_leave_type_name = line.leave_type_id.sudo().name
            else:
                line.display_leave_type_name = False

    def _is_applicable_to_employee(self, employee):
        self.ensure_one()
        if self.gender_applicability == 'all':
            return True
        employee_gender = self._get_employee_gender(employee)
        return employee_gender == self.gender_applicability

    @api.model
    def _get_employee_gender(self, employee):
        """Return the employee gender field in a safe way across HR variants."""
        employee_gender = False
        if employee:
            employee_gender = getattr(employee, 'sex', False) or getattr(employee, 'gender', False)
            if not employee_gender and getattr(employee, 'version_id', False):
                employee_gender = getattr(employee.version_id, 'sex', False) or getattr(employee.version_id, 'gender', False)
            if not employee_gender and getattr(employee, 'resource_id', False):
                employee_gender = getattr(employee.resource_id, 'sex', False) or getattr(employee.resource_id, 'gender', False)
        return employee_gender

    @api.onchange('leave_type_id')
    def _onchange_leave_type_id_set_gender_applicability(self):
        for line in self:
            leave_name = (line.leave_type_id.sudo().name or '').lower() if line.leave_type_id else ''
            if 'maternity' in leave_name:
                line.gender_applicability = 'female'

    @api.constrains('leave_type_id')
    def _check_leave_type_company(self):
        for line in self:
            if line.leave_type_id.company_id and line.leave_type_id.company_id != line.company_id:
                raise ValidationError(_(
                    'The selected leave type must belong to the same company as the policy.'
                ))
            if line.allocation_mode == 'allocation' and line.annual_days <= 0:
                raise ValidationError(_(
                    'Auto Allocation lines must have Annual Days greater than zero.'
                ))
            if line.allocation_mode == 'earned' and line.working_days_per_leave <= 0:
                raise ValidationError(_(
                    'Earned Leave lines must have Working Days per Leave greater than zero.'
                ))
            if line.allocation_mode == 'earned' and line.carry_forward_limit_days < 0:
                raise ValidationError(_(
                    'Carry Forward Limit cannot be negative.'
                ))
            if line.allocation_mode == 'earned' and line.carry_forward_total_limit_days < 0:
                raise ValidationError(_(
                    'Carry Forward Total Limit cannot be negative.'
                ))
            if line.allocation_mode == 'comp_off' and line.comp_off_days_per_worked_day <= 0:
                raise ValidationError(_(
                    'Comp Off lines must have Comp-off Days per Work Day greater than zero.'
                ))
            if line.allocation_mode == 'comp_off' and line.comp_off_validity_months <= 0:
                raise ValidationError(_(
                    'Comp Off validity must be at least 1 month.'
                ))
