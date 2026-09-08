# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, time

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class AttendanceRegularizationRequest(models.Model):
    _name = 'attendance.regularization.request'
    _description = 'Attendance Regularization Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(default='/', readonly=True, copy=False, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee',
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        help='Employee who is requesting the attendance correction.',
    )
    company_id = fields.Many2one(
        'res.company',
        related='employee_id.company_id',
        store=True,
        readonly=True,
    )
    manager_id = fields.Many2one(
        'hr.employee',
        related='employee_id.parent_id',
        store=True,
        readonly=True,
    )
    manager_user_id = fields.Many2one(
        'res.users',
        related='manager_id.user_id',
        store=True,
        readonly=True,
    )
    request_date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    existing_attendance_info = fields.Text(
        string='Attendance on Selected Date',
        compute='_compute_existing_attendance_info',
    )
    request_type = fields.Selection(
        [
            ('missed_check_in', 'Missed Check-in'),
            ('missed_check_out', 'Missed Check-out'),
            ('both', 'Both Punches Missing'),
            ('correction', 'Time Correction'),
        ],
        required=True,
        default='both',
        tracking=True,
    )
    check_in = fields.Datetime(tracking=True)
    check_out = fields.Datetime(tracking=True)
    reason = fields.Text(required=True, tracking=True)
    approval_note = fields.Text(tracking=True)
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Attendance Record',
        readonly=True,
        copy=False,
    )
    original_check_in = fields.Datetime(readonly=True, copy=False)
    original_check_out = fields.Datetime(readonly=True, copy=False)
    applied_check_in = fields.Datetime(readonly=True, copy=False)
    applied_check_out = fields.Datetime(readonly=True, copy=False)
    attendance_created_by_request = fields.Boolean(readonly=True, copy=False)
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'attendance_regularization_attachment_rel',
        'request_id',
        'attachment_id',
        string='Attachments',
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        tracking=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        employee = self.env.user.employee_id
        if not res.get('employee_id') and employee:
            res['employee_id'] = employee.id
        if not res.get('request_date'):
            res['request_date'] = fields.Date.context_today(self)
        return res

    @api.depends('employee_id', 'request_date')
    def _compute_existing_attendance_info(self):
        Attendance = self.env['hr.attendance'].sudo()
        for request in self:
            if not request.employee_id or not request.request_date:
                request.existing_attendance_info = _('Select an employee and date.')
                continue
            attendances = Attendance.search([
                ('employee_id', '=', request.employee_id.id),
                ('date', '=', request.request_date),
            ], order='check_in')
            if not attendances:
                request.existing_attendance_info = _(
                    'No attendance record found for this date.')
                continue
            details = []
            for attendance in attendances:
                check_in = self._format_local_datetime(attendance.check_in) \
                    if attendance.check_in else _('Missing')
                check_out = self._format_local_datetime(attendance.check_out) \
                    if attendance.check_out else _('Missing')
                details.append(_(
                    'Check-in: %(check_in)s | Check-out: %(check_out)s | '
                    'Worked: %(worked_hours).2f hours'
                ) % {
                    'check_in': check_in,
                    'check_out': check_out,
                    'worked_hours': attendance.worked_hours or 0.0,
                })
            request.existing_attendance_info = '\n'.join(details)

    def _format_local_datetime(self, value):
        """Display stored UTC datetimes in the current user's timezone."""
        local_value = fields.Datetime.context_timestamp(self, value)
        return local_value.strftime('%Y-%m-%d %I:%M %p')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'attendance.regularization.request') or '/'
        return super().create(vals_list)

    @api.constrains('check_in', 'check_out', 'request_type')
    def _check_requested_times(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out <= rec.check_in:
                raise ValidationError(_('Check-out must be later than check-in.'))

            if rec.request_type == 'missed_check_in' and not rec.check_in:
                raise ValidationError(_('Missed check-in requests require a check-in time.'))
            if rec.request_type == 'missed_check_out' and not rec.check_out:
                raise ValidationError(_('Missed check-out requests require a check-out time.'))
            if rec.request_type == 'both' and (not rec.check_in or not rec.check_out):
                raise ValidationError(_('Both punch requests require both check-in and check-out times.'))
            if rec.request_type == 'correction' and not (rec.check_in or rec.check_out):
                raise ValidationError(_('Provide at least one corrected punch time.'))

    @api.constrains('employee_id', 'request_date', 'state')
    def _check_duplicate_active_requests(self):
        """Allow history, but avoid multiple active requests for the same employee/day."""
        for rec in self.filtered(lambda r: r.state in ('draft', 'submitted')):
            duplicate = self.search_count([
                ('id', '!=', rec.id),
                ('employee_id', '=', rec.employee_id.id),
                ('request_date', '=', rec.request_date),
                ('state', 'in', ('draft', 'submitted')),
            ])
            if duplicate:
                raise ValidationError(_(
                    'There is already a draft/submitted regularization request for this employee on the same date.'
                ))

    def _check_approved_leave(self):
        Leave = self.env['hr.leave'].sudo()
        for request in self:
            if not request.employee_id or not request.request_date:
                continue
            leave = Leave.search([
                ('employee_id', '=', request.employee_id.id),
                ('state', '=', 'validate'),
                ('request_date_from', '<=', request.request_date),
                ('request_date_to', '>=', request.request_date),
            ], limit=1)
            if leave:
                raise ValidationError(_(
                    'Attendance regularization is not allowed for %(employee)s on %(date)s because %(leave)s is approved.'
                ) % {
                    'employee': request.employee_id.name,
                    'date': request.request_date,
                    'leave': leave.holiday_status_id.sudo().name,
                })

    @api.constrains('employee_id', 'request_date')
    def _check_regularization_leave_conflict(self):
        self._check_approved_leave()

    def _get_day_bounds(self):
        self.ensure_one()
        day_start = datetime.combine(self.request_date, time.min)
        day_end = day_start + timedelta(days=1)
        return day_start, day_end

    def _find_attendance(self):
        self.ensure_one()
        Attendance = self.env['hr.attendance'].sudo()
        start_dt, end_dt = self._get_day_bounds()

        existing_request_attendance = self.search([
            ('id', '!=', self.id),
            ('employee_id', '=', self.employee_id.id),
            ('request_date', '=', self.request_date),
            ('state', '=', 'approved'),
            ('attendance_id', '!=', False),
        ], limit=1)
        if existing_request_attendance and existing_request_attendance.attendance_id:
            return existing_request_attendance.attendance_id

        open_attendance = Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            ('check_out', '=', False),
            ('check_in', '>=', start_dt),
            ('check_in', '<', end_dt),
        ], order='check_in desc, id desc', limit=1)
        # Reuse the same-day open attendance for any request that supplies
        # the missing/corrected punch. Otherwise the global open-attendance
        # check below incorrectly blocks valid regularization requests.
        if open_attendance and (
                self.request_type in ('missed_check_out', 'both', 'correction')
                and (self.check_in or self.check_out)):
            return open_attendance

        return Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            '|',
            '&', ('check_in', '>=', start_dt), ('check_in', '<', end_dt),
            '&', ('check_out', '>=', start_dt), ('check_out', '<', end_dt),
        ], order='check_in desc, id desc', limit=1)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.write({'state': 'submitted'})
            if rec.manager_user_id:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=rec.manager_user_id.id,
                    note=_('Attendance regularization request needs your review.'),
                )

    def _check_approval_access(self):
        if self.env.is_superuser():
            return
        approver_groups = (
            'dotbd_hr_access_control_suite.group_hr_department_manager',
            'dotbd_hr_access_control_suite.group_hr_officer',
            'dotbd_hr_access_control_suite.group_hr_manager',
            'dotbd_hr_access_control_suite.group_hr_executive',
        )
        if not any(self.env.user.has_group(group) for group in approver_groups):
            raise AccessError(_('Only a department manager or HR approver can approve or reject attendance regularization requests.'))

    def action_approve(self):
        self._check_approval_access()
        Attendance = self.env['hr.attendance'].sudo()
        for rec in self:
            if rec.state not in ('submitted', 'draft'):
                continue

            rec._check_approved_leave()

            attendance = rec._find_attendance()
            values = {}

            if rec.request_type in ('missed_check_in', 'both', 'correction') and rec.check_in:
                values['check_in'] = rec.check_in
            if rec.request_type in ('missed_check_out', 'both', 'correction') and rec.check_out:
                values['check_out'] = rec.check_out

            if attendance:
                original_check_in = attendance.check_in
                original_check_out = attendance.check_out
                attendance.write(values)
            else:
                open_attendance = Attendance.search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('check_out', '=', False),
                ], order='check_in desc, id desc', limit=1)
                if open_attendance:
                    raise UserError(_(
                        'Cannot approve this request because an earlier attendance is still open '
                        'since %(check_in)s. Please close that attendance first and try again.'
                    ) % {
                        'check_in': fields.Datetime.to_string(open_attendance.check_in),
                    })
                if not values.get('check_in'):
                    raise UserError(_(
                        'A new attendance record cannot be created without a check-in time.'
                    ))
                values['employee_id'] = rec.employee_id.id
                attendance = Attendance.create(values)
                original_check_in = False
                original_check_out = False

            rec.write({
                'attendance_id': attendance.id,
                'original_check_in': original_check_in,
                'original_check_out': original_check_out,
                'applied_check_in': values.get('check_in') or False,
                'applied_check_out': values.get('check_out') or False,
                'attendance_created_by_request': not bool(original_check_in or original_check_out),
                'state': 'approved',
                'approval_note': rec.approval_note or _('Approved'),
            })

    def action_reject(self):
        self._check_approval_access()
        for rec in self:
            if rec.state in ('approved', 'cancelled'):
                continue
            rec.write({'state': 'rejected'})
            if rec.activity_ids:
                rec.activity_ids.unlink()

    def action_revoke_approval(self):
        """Undo an approval and restore or remove the attendance change."""
        self._check_approval_access()
        Attendance = self.env['hr.attendance'].sudo()
        for rec in self:
            if rec.state != 'approved' or not rec.attendance_id:
                continue

            attendance = rec.attendance_id.sudo()

            if rec.attendance_created_by_request:
                other_requests = self.search([
                    ('id', '!=', rec.id),
                    ('attendance_id', '=', attendance.id),
                    ('state', '=', 'approved'),
                ], limit=1)
                if other_requests:
                    raise UserError(_(
                        'This attendance is already used by another approved regularization request. '
                        'Please revoke the later request first.'
                    ))
                attendance.unlink()
            else:
                restore_vals = {}
                if rec.original_check_in:
                    restore_vals['check_in'] = rec.original_check_in
                restore_vals['check_out'] = rec.original_check_out or False

                if not restore_vals:
                    raise UserError(_(
                        'Cannot restore the original attendance because the original punch values are missing.'
                    ))

                attendance.write(restore_vals)

            rec.write({
                'attendance_id': False,
                'state': 'rejected',
                'approval_note': rec.approval_note or _('Approval revoked by manager'),
            })

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_('Approved requests cannot be reset. Create a new request instead.'))
            rec.write({'state': 'draft'})

    def action_cancel(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_('Approved requests cannot be cancelled.'))
            rec.write({'state': 'cancelled'})
