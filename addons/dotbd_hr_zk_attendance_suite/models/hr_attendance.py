# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#
################################################################################
import logging
import pytz
from datetime import datetime, timedelta, time
from odoo import fields, models, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    """Inherit the module to add late check-in tracking with tolerance"""
    _inherit = 'hr.attendance'

    late_check_in = fields.Integer(
        string="Actual Late Time (Minutes)",
        compute="_compute_late_check_in",
        help="This shows the actual duration of the employee's tardiness (without tolerance).",
        store=True)

    tolerance_late_time = fields.Integer(
        string="Counted Late Time (Minutes)",
        compute="_compute_tolerance_late_time",
        help="Late time after applying tolerance settings. 0 means within tolerance limit.",
        store=True)

    is_within_tolerance = fields.Boolean(
        string="Within Tolerance",
        compute="_compute_tolerance_late_time",
        help="True if the employee is within the late tolerance limit.",
        store=True)

    late_check_in_id = fields.Many2one(
        'late.check.in',
        string="Late Check-in Record",
        help="Related late check-in record if created")

    shift_roster_line_id = fields.Integer(
        string='Shift Roster Line ID',
        help='Database ID of the roster line used to evaluate this attendance record.')
    planned_start_time = fields.Float(
        string='Planned Start Time',
        compute='_compute_shift_roster_context',
        help='Planned shift start time coming from the roster line, if any.')
    planned_end_time = fields.Float(
        string='Planned End Time',
        compute='_compute_shift_roster_context',
        help='Planned shift end time coming from the roster line, if any.')
    planned_break_duration = fields.Float(
        string='Planned Break Duration',
        compute='_compute_shift_roster_context',
        help='Planned break duration coming from the roster line, if any.')
    planned_is_weekly_off = fields.Boolean(
        string='Planned Weekly Off',
        compute='_compute_shift_roster_context',
        help='True when the roster line marks this day as a weekly off.')
    early_leave_minutes = fields.Integer(
        string='Early Leave (Minutes)',
        compute='_compute_roster_time_metrics',
        help='Minutes left early compared to the roster/shift end time.')
    overtime_minutes = fields.Integer(
        string='Overtime (Minutes)',
        compute='_compute_roster_time_metrics',
        help='Minutes worked beyond the roster/shift end time.')
    comp_off_eligible = fields.Boolean(
        string='Comp-Off Eligible',
        compute='_compute_roster_time_metrics',
        help='True when the employee works on a rostered weekly off.')
    comp_off_hours = fields.Float(
        string='Comp-Off Hours',
        compute='_compute_roster_time_metrics',
        help='Hours worked on a rostered weekly off.')

    def _approved_leave_for_datetime(self, employee, value):
        """Return approved leave covering the local date of a punch."""
        if not employee or not value:
            return self.env['hr.leave'].browse()
        local_date = fields.Datetime.context_timestamp(
            employee, fields.Datetime.to_datetime(value)
        ).date()
        return self.env['hr.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', local_date),
            ('request_date_to', '>=', local_date),
        ], limit=1)

    def _check_approved_leave(self, employee, value):
        leave = self._approved_leave_for_datetime(employee, value)
        if leave:
            raise ValidationError(
                'Attendance cannot be added for %s because %s is approved on that date.'
                % (employee.name, leave.holiday_status_id.sudo().name)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            employee = self.env['hr.employee'].browse(values.get('employee_id'))
            self._check_approved_leave(employee, values.get('check_in'))
        return super().create(vals_list)

    def write(self, vals):
        if 'check_in' in vals or 'employee_id' in vals:
            for attendance in self:
                employee = self.env['hr.employee'].browse(
                    vals.get('employee_id', attendance.employee_id.id)
                )
                check_in = vals.get('check_in', attendance.check_in)
                self._check_approved_leave(employee, check_in)
        return super().write(vals)

    # ZK Machine Integration
    zk_punch_ids = fields.One2many(
        'zk.machine.attendance', 'hr_attendance_id',
        string='Device Punches',
        help='Raw punch records from biometric device that contributed to this attendance')

    zk_punch_count = fields.Integer(
        string='Punch Count',
        compute='_compute_zk_punch_count',
        store=True,
        help='Number of device punches linked to this attendance')

    attendance_source = fields.Selection([
        ('biometric', 'Biometric Device'),
        ('manual', 'Manual Entry'),
        ('system', 'System Generated')
    ], string='Attendance Source', compute='_compute_attendance_source', store=True,
       help='Source of this attendance record')

    @api.depends('zk_punch_ids')
    def _compute_zk_punch_count(self):
        """Count the number of ZK punches linked to this attendance"""
        for rec in self:
            rec.zk_punch_count = len(rec.zk_punch_ids)

    @api.depends('zk_punch_ids')
    def _compute_attendance_source(self):
        """Determine the source of attendance record"""
        for rec in self:
            if rec.zk_punch_ids:
                rec.attendance_source = 'biometric'
            else:
                rec.attendance_source = 'manual'

    @api.model
    def _get_shift_roster_line(self, employee, work_date, company_id=None):
        """Return the roster line that applies to an employee on a given date."""
        if not employee or not work_date:
            return self.env['hr.shift.roster.line'].browse()

        if 'hr.shift.roster.line' not in self.env:
            return self.env['hr.shift.roster.line'].browse()

        return self.env['hr.shift.roster.line'].sudo().get_planned_line(
            employee, work_date, company_id=company_id or employee.company_id)

    @api.depends('check_in', 'employee_id')
    def _compute_shift_roster_context(self):
        """Cache the roster line and its planned values for the attendance day."""
        for rec in self:
            roster_line = self.env['hr.shift.roster.line'].browse()
            if rec.check_in and rec.employee_id and 'hr.shift.roster.line' in self.env:
                roster_line = rec._get_shift_roster_line(rec.employee_id, rec.check_in.date(), rec.employee_id.company_id)

            rec.shift_roster_line_id = roster_line.id if roster_line else False
            rec.planned_start_time = roster_line.start_time if roster_line else 0.0
            rec.planned_end_time = roster_line.end_time if roster_line else 0.0
            rec.planned_break_duration = roster_line.break_duration if roster_line else 0.0
            rec.planned_is_weekly_off = bool(roster_line and roster_line.is_weekly_off)

    @api.depends('check_in', 'employee_id', 'shift_roster_line_id', 'planned_start_time', 'planned_is_weekly_off')
    def _compute_late_check_in(self):
        """Calculate actual late check-in minutes without applying tolerance."""
        for rec in self:
            rec.late_check_in = 0
            if not rec.check_in or not rec.employee_id:
                continue

            roster_line = self.env['hr.shift.roster.line'].browse(rec.shift_roster_line_id) if rec.shift_roster_line_id and 'hr.shift.roster.line' in self.env else self.env['hr.shift.roster.line'].browse()
            if not roster_line and 'hr.shift.roster.line' in self.env:
                roster_line = rec._get_shift_roster_line(rec.employee_id, rec.check_in.date(), rec.employee_id.company_id)

            if roster_line:
                rec.shift_roster_line_id = roster_line.id
                rec.planned_start_time = roster_line.start_time
                rec.planned_end_time = roster_line.end_time
                rec.planned_break_duration = roster_line.break_duration
                rec.planned_is_weekly_off = bool(roster_line.is_weekly_off or getattr(roster_line, 'is_public_holiday', False))
                if roster_line.is_weekly_off or getattr(roster_line, 'is_public_holiday', False):
                    continue
                start_float = roster_line.start_time
            else:
                start_float = None

            # Get resource calendar from employee or contract as fallback only.
            calendar = None
            if start_float is None:
                try:
                    if hasattr(rec.employee_id, '_get_contracts'):
                        contracts = rec.employee_id._get_contracts(rec.check_in.date())
                        if contracts and rec.employee_id.id in contracts:
                            contract_versions = contracts[rec.employee_id.id]
                            if contract_versions and hasattr(contract_versions, 'resource_calendar_id'):
                                calendar = contract_versions.resource_calendar_id
                except Exception as e:
                    _logger.debug("Could not get contract calendar for %s: %s", rec.employee_id.name, e)

                if not calendar:
                    calendar = rec.employee_id.resource_calendar_id
                if not calendar:
                    calendar = rec.employee_id.company_id.resource_calendar_id

                if not calendar:
                    continue

                # Convert check_in using the calendar's timezone (same tz as hour_from).
                # In Odoo 19 _get_tz() was updated to put calendar.tz first for this
                # exact reason. We replicate that priority here so the weekday and the
                # start-time comparison are both in the schedule's reference frame.
                cal_tz_name = (calendar.tz
                               or rec.employee_id.tz
                               or rec.employee_id.company_id.resource_calendar_id.tz
                               or 'UTC')
                tz_obj = pytz.timezone(cal_tz_name) if cal_tz_name in pytz.all_timezones else pytz.utc
                dt_local = pytz.utc.localize(rec.check_in).astimezone(tz_obj)
                local_weekday = str(dt_local.weekday())

                # Find the earliest start time among all schedule lines for this weekday.
                # Using the earliest start handles both morning-only and full-day schedule types.
                day_schedules = [s for s in calendar.attendance_ids
                                 if s.dayofweek == local_weekday]
                if not day_schedules:
                    continue
                schedule = min(day_schedules, key=lambda s: s.hour_from)

                str_time = dt_local.strftime("%H:%M")
                check_in_date = datetime.strptime(str_time, "%H:%M").time()
                start_date = datetime.strptime(
                    '{0:02.0f}:{1:02.0f}'.format(*divmod(
                        schedule.hour_from * 60, 60)), "%H:%M").time()

                check_in_td = timedelta(hours=check_in_date.hour, minutes=check_in_date.minute)
                start_date_td = timedelta(hours=start_date.hour, minutes=start_date.minute)

                if check_in_td > start_date_td:
                    final = check_in_td - start_date_td
                    rec.late_check_in = int(final.total_seconds() / 60)
                continue

            # Convert check-in into a local time using the employee/company timezone.
            cal_tz_name = (
                rec.employee_id.tz
                or rec.employee_id.company_id.resource_calendar_id.tz
                or 'UTC'
            )
            tz_obj = pytz.timezone(cal_tz_name) if cal_tz_name in pytz.all_timezones else pytz.utc
            dt_local = pytz.utc.localize(rec.check_in).astimezone(tz_obj)
            check_in_date = dt_local.time()
            start_date = datetime.strptime(
                '{0:02.0f}:{1:02.0f}'.format(*divmod(start_float * 60, 60)), "%H:%M").time()

            check_in_td = timedelta(hours=check_in_date.hour, minutes=check_in_date.minute)
            start_date_td = timedelta(hours=start_date.hour, minutes=start_date.minute)

            if check_in_td > start_date_td:
                final = check_in_td - start_date_td
                rec.late_check_in = int(final.total_seconds() / 60)

    @api.depends(
        'check_in', 'check_out', 'employee_id',
        'shift_roster_line_id', 'planned_start_time', 'planned_end_time',
        'planned_break_duration', 'planned_is_weekly_off',
    )
    def _compute_roster_time_metrics(self):
        """Compute early leave and overtime using roster times when available."""
        for rec in self:
            rec.early_leave_minutes = 0
            rec.overtime_minutes = 0
            rec.comp_off_eligible = False
            rec.comp_off_hours = 0.0

            if not rec.check_in or not rec.check_out or not rec.employee_id:
                continue

            roster_line = self.env['hr.shift.roster.line'].browse(rec.shift_roster_line_id) if rec.shift_roster_line_id and 'hr.shift.roster.line' in self.env else self.env['hr.shift.roster.line'].browse()
            if not roster_line and 'hr.shift.roster.line' in self.env:
                roster_line = rec._get_shift_roster_line(
                    rec.employee_id, rec.check_in.date(), rec.employee_id.company_id)

            if roster_line:
                overtime_allowed = bool(getattr(roster_line.shift_template_id, 'overtime_allowed', False))
                if roster_line.is_weekly_off or getattr(roster_line, 'is_public_holiday', False):
                    worked_hours = (rec.check_out - rec.check_in).total_seconds() / 3600.0
                    rec.comp_off_eligible = worked_hours > 0
                    rec.comp_off_hours = round(max(0.0, worked_hours), 2)
                    continue
                start_float = roster_line.start_time
                end_float = roster_line.end_time
                break_duration = roster_line.break_duration or 0.0
            else:
                start_float = rec.planned_start_time or 0.0
                end_float = rec.planned_end_time or 0.0
                break_duration = rec.planned_break_duration or 0.0

            if not start_float and not end_float:
                continue

            cal_tz_name = (
                rec.employee_id.tz
                or rec.employee_id.company_id.resource_calendar_id.tz
                or 'UTC'
            )
            tz_obj = pytz.timezone(cal_tz_name) if cal_tz_name in pytz.all_timezones else pytz.utc
            check_in_local = pytz.utc.localize(rec.check_in).astimezone(tz_obj)
            check_out_local = pytz.utc.localize(rec.check_out).astimezone(tz_obj)

            planned_start_dt = datetime.combine(check_in_local.date(), time(
                int(start_float), int((start_float - int(start_float)) * 60)))
            planned_end_dt = datetime.combine(check_in_local.date(), time(
                int(end_float), int((end_float - int(end_float)) * 60)))

            if planned_end_dt <= planned_start_dt:
                planned_end_dt += timedelta(days=1)

            if overtime_allowed and check_out_local.replace(tzinfo=None) > planned_end_dt:
                rec.overtime_minutes = int(
                    (check_out_local.replace(tzinfo=None) - planned_end_dt).total_seconds() / 60)
            elif check_out_local.replace(tzinfo=None) < planned_end_dt:
                rec.early_leave_minutes = int(
                    (planned_end_dt - check_out_local.replace(tzinfo=None)).total_seconds() / 60)

    @api.depends('late_check_in')
    def _compute_tolerance_late_time(self):
        """Calculate late time after applying tolerance settings."""
        for rec in self:
            # Get tolerance parameter from system configuration
            minutes_after = int(self.env['ir.config_parameter'].sudo().get_param(
                'dotbd_hr_zk_attendance_suite.late_check_in_after', default=0))

            if rec.late_check_in > minutes_after:
                rec.tolerance_late_time = rec.late_check_in - minutes_after
                rec.is_within_tolerance = False
            else:
                rec.tolerance_late_time = 0
                rec.is_within_tolerance = True

    @api.model
    def create_late_check_in_records(self):
        """Function creates records in late.check.in model for employees who were late
        This is called by cron job or manually"""
        max_limit = int(self.env['ir.config_parameter'].sudo().get_param(
            'dotbd_hr_zk_attendance_suite.maximum_minutes', default=240))

        enable_penalties = self.env['ir.config_parameter'].sudo().get_param(
            'dotbd_hr_zk_attendance_suite.enable_late_penalties', default='True') in ('True', 'true', '1', True)

        if not enable_penalties:
            return

        # Get existing late check-in records
        existing_late_records = self.env['late.check.in'].sudo().search([])
        existing_attendance_ids = set(existing_late_records.mapped('attendance_id.id'))

        # Get all attendance records without late check-in record
        attendance_records = self.sudo().search([
            ('check_in', '!=', False),
            ('late_check_in', '>', 0),
        ])

        for rec in attendance_records:
            # Skip if within tolerance
            if rec.is_within_tolerance:
                continue

            # Skip if exceeds maximum limit (considered absent instead of late)
            if max_limit > 0 and rec.late_check_in > max_limit:
                continue

            record_data = {
                'employee_id': rec.employee_id.id,
                'late_minutes': rec.tolerance_late_time,
                'actual_late_minutes': rec.late_check_in,
                'date': rec.check_in.date(),
                'attendance_id': rec.id,
            }

            if rec.id not in existing_attendance_ids:
                # Create new late check-in record
                late_record = self.env['late.check.in'].sudo().create(record_data)
                rec.late_check_in_id = late_record.id
            else:
                # Update existing record
                existing_record = existing_late_records.filtered(
                    lambda x: x.attendance_id.id == rec.id
                )
                if existing_record:
                    existing_record.write(record_data)

    @api.model
    def late_check_in_records(self):
        """Alias method for backward compatibility with employee_late_check_in module
        Calls create_late_check_in_records() method"""
        return self.create_late_check_in_records()

    def unlink(self):
        """Override the unlink method to delete corresponding records in late.check.in model"""
        late_records_to_delete = self.env['late.check.in'].sudo().search([
            ('attendance_id', 'in', self.ids)
        ])
        late_records_to_delete.unlink()
        return super(HrAttendance, self).unlink()
