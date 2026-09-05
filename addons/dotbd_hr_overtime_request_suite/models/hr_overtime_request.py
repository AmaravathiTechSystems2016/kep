# -*- coding: utf-8 -*-

import pytz
from datetime import datetime, timedelta, time

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HrOvertimeRequest(models.Model):
    _name = 'hr.overtime.request'
    _description = 'Manual Overtime Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default='New',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
    )
    attendance_category = fields.Selection(
        [
            ('worker', 'Manufacturing Worker'),
            ('office', 'Computer / Office Staff'),
            ('other', 'Other'),
        ],
        string='Employee Category',
        compute='_compute_attendance_category',
        store=True,
        readonly=True,
    )
    shift_template_id = fields.Many2one(
        'hr.shift.template',
        string='Default Shift Template',
        related='employee_id.default_shift_template_id',
        store=True,
        readonly=True,
    )
    request_date = fields.Date(
        string='Request Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    overtime_date = fields.Date(
        string='Overtime Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    start_time = fields.Float(
        string='Start Time',
        tracking=True,
        help='Optional overtime start time in hours, for example 18.00 for 6:00 PM.',
    )
    end_time = fields.Float(
        string='End Time',
        tracking=True,
        help='Optional overtime end time in hours, for example 21.00 for 9:00 PM.',
    )
    requested_hours = fields.Float(
        string='Requested Hours',
        required=True,
        tracking=True,
        help='Manual overtime hours requested by the employee or manager.',
    )
    approved_hours = fields.Float(
        string='Approved Hours',
        tracking=True,
        help='Hours approved by the manager.',
    )
    reason = fields.Text(string='Reason', required=True, tracking=True)
    manager_note = fields.Text(string='Manager Note', tracking=True)
    requested_by_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        readonly=True,
    )
    duration_text = fields.Char(
        string='Duration',
        compute='_compute_duration_text',
    )
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Attendance',
        readonly=True,
        tracking=True,
        help='Attendance record updated when the overtime request is approved.',
    )

    @api.depends('start_time', 'end_time', 'requested_hours')
    def _compute_duration_text(self):
        for rec in self:
            if rec.start_time and rec.end_time:
                rec.duration_text = f'{rec.start_time:.2f} - {rec.end_time:.2f}'
            elif rec.requested_hours:
                rec.duration_text = f'{rec.requested_hours:.2f} hours'
            else:
                rec.duration_text = False

    @api.depends('employee_id')
    def _compute_attendance_category(self):
        for rec in self:
            rec.attendance_category = getattr(rec.employee_id, 'attendance_category', False) or False

    @api.onchange('start_time', 'end_time')
    def _onchange_start_end_time(self):
        for rec in self:
            if rec.start_time and rec.end_time:
                if rec.end_time <= rec.start_time:
                    continue
                rec.requested_hours = round(rec.end_time - rec.start_time, 2)

    @api.constrains('start_time', 'end_time', 'requested_hours')
    def _check_duration(self):
        for rec in self:
            if rec.requested_hours is not None and rec.requested_hours <= 0:
                raise ValidationError(_('Requested hours must be greater than zero.'))
            if rec.start_time and rec.end_time and rec.end_time <= rec.start_time:
                raise ValidationError(_('End time must be greater than start time.'))

    @api.constrains('employee_id', 'overtime_date', 'state')
    def _check_duplicate_active_request(self):
        for rec in self.filtered(lambda r: r.employee_id and r.overtime_date and r.state not in ('cancelled', 'rejected')):
            domain = [
                ('id', '!=', rec.id),
                ('employee_id', '=', rec.employee_id.id),
                ('overtime_date', '=', rec.overtime_date),
                ('state', 'not in', ('cancelled', 'rejected')),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    'A manual overtime request already exists for %s on %s.'
                ) % (rec.employee_id.display_name, rec.overtime_date))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('hr.overtime.request') or 'New'
        return super().create(vals_list)

    def _check_hr_approver(self):
        if not (self.env.user.has_group('hr.group_hr_user') or self.env.user.has_group('hr.group_hr_manager')):
            raise UserError(_('Only HR users or managers can approve overtime requests.'))

    def _get_attendance_for_request(self):
        self.ensure_one()
        if not self.employee_id or not self.overtime_date:
            return self.env['hr.attendance']

        company_calendar = self.employee_id.company_id.resource_calendar_id
        tz_name = (
            self.employee_id.tz
            or (company_calendar.tz if company_calendar else False)
            or 'UTC'
        )
        tz_obj = pytz.timezone(tz_name) if tz_name in pytz.all_timezones else pytz.utc
        local_start = tz_obj.localize(datetime.combine(self.overtime_date, time.min))
        local_end = tz_obj.localize(datetime.combine(self.overtime_date + timedelta(days=1), time.min))
        utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
        utc_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)
        return self.env['hr.attendance'].search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', utc_start),
            ('check_in', '<', utc_end),
        ], order='check_in desc', limit=1)

    def _sync_attendance(self):
        for rec in self:
            attendance = rec._get_attendance_for_request()
            if not attendance:
                raise UserError(_(
                    'No attendance record was found for %s on %s. Please create or complete the attendance first.'
                ) % (rec.employee_id.display_name, rec.overtime_date))
            attendance.write({
                'manual_overtime_request_id': rec.id,
                'manual_overtime_hours': rec.approved_hours or rec.requested_hours,
            })
            rec.attendance_id = attendance.id

    def _unsync_attendance(self):
        for rec in self.filtered('attendance_id'):
            rec.attendance_id.write({
                'manual_overtime_request_id': False,
                'manual_overtime_hours': 0.0,
            })
            rec.attendance_id = False

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.write({'state': 'submitted'})

    def action_approve(self):
        self._check_hr_approver()
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted overtime requests can be approved.'))
            approved_hours = rec.approved_hours or rec.requested_hours
            rec.write({
                'state': 'approved',
                'approved_hours': approved_hours,
                'approved_by_id': self.env.user.id,
            })
            rec._sync_attendance()

    def action_reject(self):
        self._check_hr_approver()
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted overtime requests can be rejected.'))
            rec.write({
                'state': 'rejected',
                'approved_by_id': self.env.user.id,
            })

    def action_revoke_approval(self):
        self._check_hr_approver()
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('Only approved overtime requests can be revoked.'))
            rec._unsync_attendance()
            rec.write({
                'state': 'submitted',
                'approved_hours': 0.0,
                'approved_by_id': False,
                'manager_note': False,
            })

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            rec.write({'state': 'draft'})

    def action_cancel(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_('Please revoke approval before cancelling this overtime request.'))
            rec.write({'state': 'cancelled'})
