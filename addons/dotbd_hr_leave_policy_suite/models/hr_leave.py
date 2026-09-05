# -*- coding: utf-8 -*-

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.addons.resource.models.utils import HOURS_PER_DAY
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    request_apply_in = fields.Selection(
        [('day', 'Days'), ('hour', 'Hours')],
        string='Apply In',
        default='day',
        tracking=True,
        help='Choose Days for a normal leave request or Hours for a short leave in the same day.',
    )

    def _get_leave_contact_partner(self):
        self.ensure_one()
        employee = self.employee_id
        partner = employee.work_contact_id or employee.user_id.partner_id
        return partner

    def _get_leave_approver_partners(self):
        self.ensure_one()
        partners = self.env['res.partner']
        if self.validation_type in ('manager', 'both') and self.employee_id.leave_manager_id:
            partners |= self.employee_id.leave_manager_id.partner_id
        if self.validation_type in ('hr', 'both'):
            partners |= self.holiday_status_id.responsible_ids.partner_id
        return partners.filtered(lambda partner: partner.email)

    def _notify_leave_request(self):
        for leave in self:
            partners = leave._get_leave_approver_partners()
            if not partners:
                continue
            leave.message_notify(
                partner_ids=partners.ids,
                subject=_('New Leave Request'),
                body=_(
                    '%(employee)s has applied for %(leave_type)s from %(date_from)s to %(date_to)s.',
                    employee=leave.employee_id.name,
                    leave_type=leave.holiday_status_id.sudo().name,
                    date_from=fields.Date.to_string(leave.request_date_from or leave.date_from.date()),
                    date_to=fields.Date.to_string(leave.request_date_to or leave.date_to.date()),
                ),
                email_layout_xmlid='mail.mail_notification_layout',
                model_description=_('Time Off'),
                subtitles=[leave.display_name],
            )

    def _notify_leave_decision(self, decision):
        for leave in self:
            partner = leave._get_leave_contact_partner()
            if not partner or not partner.email:
                continue
            if decision == 'approved':
                subject = _('Leave Approved')
                body = _(
                    'Your %(leave_type)s request from %(date_from)s to %(date_to)s has been approved.',
                    leave_type=leave.holiday_status_id.sudo().name,
                    date_from=fields.Date.to_string(leave.request_date_from or leave.date_from.date()),
                    date_to=fields.Date.to_string(leave.request_date_to or leave.date_to.date()),
                )
            else:
                subject = _('Leave Rejected')
                body = _(
                    'Your %(leave_type)s request from %(date_from)s to %(date_to)s has been rejected.',
                    leave_type=leave.holiday_status_id.sudo().name,
                    date_from=fields.Date.to_string(leave.request_date_from or leave.date_from.date()),
                    date_to=fields.Date.to_string(leave.request_date_to or leave.date_to.date()),
                )
            leave.message_notify(
                partner_ids=partner.ids,
                subject=subject,
                body=body,
                email_layout_xmlid='mail.mail_notification_layout',
                model_description=_('Time Off'),
                subtitles=[leave.display_name],
            )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'request_apply_in' in fields_list and not defaults.get('request_apply_in'):
            leave_type_id = defaults.get('holiday_status_id') or self.env.context.get('default_holiday_status_id')
            leave_type = self.env['hr.leave.type'].browse(leave_type_id) if leave_type_id else self.env['hr.leave.type']
            defaults['request_apply_in'] = 'hour' if leave_type and leave_type.request_unit == 'hour' else 'day'
        return defaults

    @api.onchange('holiday_status_id')
    def _onchange_request_apply_in(self):
        for leave in self:
            if leave.holiday_status_id and leave.holiday_status_id.request_unit == 'hour':
                leave.request_apply_in = 'hour'
            elif not leave.request_apply_in:
                leave.request_apply_in = 'day'

    def _get_employee_service_months(self, employee, target_date=None):
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

    def _get_employee_probation_end_date(self, employee):
        """Return probation end date from employee record or policy settings."""
        probation_end = employee.probation_end_date
        if probation_end:
            return probation_end
        joining_date = employee.contract_date_start
        if not joining_date and 'joining_date' in employee._fields:
            joining_date = employee.joining_date
        if not joining_date:
            return False
        months = employee.leave_policy_id.new_joiner_service_months_limit or 6
        return joining_date + relativedelta(months=months)

    def _check_new_joiner_monthly_leave_limit(self):
        for leave in self:
            employee = leave.employee_id
            policy = employee.leave_policy_id
            if not employee or not policy:
                continue
            if not policy.new_joiner_service_months_limit or not policy.new_joiner_monthly_leave_limit:
                continue
            target_date = leave.request_date_from or leave.date_from.date()
            probation_end_date = leave._get_employee_probation_end_date(employee)
            if probation_end_date and target_date > probation_end_date:
                continue
            month_start = target_date.replace(day=1)
            if month_start.month == 12:
                month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)
            probation_leave_types = self.env['hr.leave.type'].sudo().search([]).filtered(
                lambda leave_type: (
                    (leave_type.name or '').strip().lower() in {
                        'casual leave', 'sick time off', 'sick leave'
                    }
                    or (leave_type.code or '').strip().lower() in {'cl', 'sl'}
                )
            )
            leave_count = self.search_count([
                ('employee_id', '=', employee.id),
                ('request_date_from', '>=', month_start),
                ('request_date_from', '<=', month_end),
                ('holiday_status_id', 'in', probation_leave_types.ids),
                ('state', 'not in', ('cancel', 'refuse')),
                ('id', '!=', leave.id),
            ])
            if leave_count >= policy.new_joiner_monthly_leave_limit:
                raise ValidationError(_(
                    'During probation, employees can avail only %(limit)s leave(s) per month during the first %(months)s month(s) of service.'
                ) % {
                    'limit': policy.new_joiner_monthly_leave_limit,
                    'months': policy.new_joiner_service_months_limit,
                })

    def _check_probation_leave_rule(self):
        for leave in self:
            employee = leave.employee_id
            policy = employee.leave_policy_id
            if not employee or not policy:
                continue
            probation_end_date = leave._get_employee_probation_end_date(employee)
            if not probation_end_date:
                continue
            target_date = leave.request_date_from or leave.date_from.date()
            if target_date > probation_end_date:
                continue
            leave_type_name = (leave.holiday_status_id.sudo().name or '').strip().lower()
            leave_type_code = (leave.holiday_status_id.sudo().code or '').strip().lower()
            allowed_probation_types = {'casual leave', 'cl', 'sick time off', 'sick leave', 'sl'}
            if leave_type_name not in allowed_probation_types and leave_type_code not in allowed_probation_types:
                raise ValidationError(_(
                    'During probation, only Casual Leave or Sick Leave can be applied.'
                ))
            leave._check_new_joiner_monthly_leave_limit()

    @api.depends('holiday_status_id.request_unit', 'request_apply_in')
    def _compute_request_unit_half(self):
        for leave in self:
            leave.request_unit_half = leave.request_apply_in == 'day' and leave.leave_type_request_unit == 'half_day'

    @api.depends('holiday_status_id.request_unit', 'request_apply_in')
    def _compute_request_unit_hours(self):
        for leave in self:
            leave.request_unit_hours = leave.request_apply_in == 'hour' or leave.leave_type_request_unit == 'hour'

    def _get_durations(self, check_leave_type=True, resource_calendar=None):
        durations = super()._get_durations(check_leave_type=check_leave_type, resource_calendar=resource_calendar)
        hour_leaves = self.filtered(lambda leave: leave.request_apply_in == 'hour' and leave.date_from and leave.date_to)
        for leave in hour_leaves:
            calendar = resource_calendar or leave.resource_calendar_id or leave.employee_id.resource_calendar_id or self.env.company.resource_calendar_id
            hours = max(0.0, (leave.date_to - leave.date_from).total_seconds() / 3600.0)
            hours = float_round(hours, precision_digits=2)
            day_hours = float_round(calendar.hours_per_day or HOURS_PER_DAY, precision_digits=2) if calendar else HOURS_PER_DAY
            days = float_round(hours / (day_hours or HOURS_PER_DAY), precision_digits=2)
            durations[leave.id] = (days, hours)
        return durations

    @api.depends('number_of_hours', 'number_of_days', 'request_apply_in', 'holiday_status_id.request_unit')
    def _compute_duration_display(self):
        for leave in self:
            if leave.request_apply_in == 'hour' or leave.leave_type_request_unit == 'hour':
                hours, minutes = divmod(abs(leave.number_of_hours) * 60, 60)
                minutes = round(minutes)
                if minutes == 60:
                    minutes = 0
                    hours += 1
                leave.duration_display = f'{int(hours):d}:{minutes:02d} {_("hours")}'
            else:
                leave.duration_display = "%g %s" % (float_round(leave.number_of_days, precision_digits=2), _('days'))

    @api.constrains('holiday_status_id', 'number_of_days', 'attachment_ids')
    def _check_support_document_after_days(self):
        for leave in self:
            threshold = leave.holiday_status_id.support_document_after_days
            if not threshold:
                continue
            if leave.number_of_days <= threshold:
                continue
            if leave.attachment_ids:
                continue
            raise ValidationError(_(
                'This leave type requires a supporting document when the request exceeds %s day(s).'
            ) % threshold)

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        leaves.filtered(lambda leave: leave.state == 'confirm')._check_probation_leave_rule()
        leaves.filtered(lambda leave: leave.state == 'confirm' and not leave.env.context.get('leave_fast_create'))._notify_leave_request()
        return leaves

    def write(self, vals):
        previous_states = {leave.id: leave.state for leave in self}
        res = super().write(vals)
        submitted = self.filtered(lambda leave: leave.state == 'confirm' and previous_states.get(leave.id) != 'confirm')
        submitted._check_probation_leave_rule()
        return res

    def action_approve(self, check_state=True):
        self._check_probation_leave_rule()
        result = super().action_approve(check_state=check_state)
        self.filtered(lambda leave: leave.state == 'validate')._notify_leave_decision('approved')
        return result
