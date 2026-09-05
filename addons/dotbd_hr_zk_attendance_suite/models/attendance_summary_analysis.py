# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#
################################################################################
from odoo import api, fields, models, tools
from datetime import datetime, timedelta, time
from collections import defaultdict
import pytz


class AttendanceSummaryAnalysis(models.Model):
    """Model to analyze comprehensive attendance including absences, late, overtime"""
    _name = 'attendance.summary.analysis'
    _description = 'Attendance Summary Analysis'
    _auto = False
    _order = 'attendance_date desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    attendance_date = fields.Date(string='Date', readonly=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('leave', 'On Leave'),
        ('public_holiday', 'Public Holiday'),
        ('weekend', 'Weekend/Holiday'),
    ], string='Status', readonly=True)

    check_in_time = fields.Datetime(string='Check In', readonly=True)
    check_out_time = fields.Datetime(string='Check Out', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True)

    is_late = fields.Boolean(string='Is Late', readonly=True)
    late_minutes = fields.Float(string='Late (Minutes)', readonly=True)

    overtime_hours = fields.Float(string='Overtime (Hours)', readonly=True)
    undertime_hours = fields.Float(string='Undertime (Hours)', readonly=True)

    expected_hours = fields.Float(string='Expected Hours', readonly=True)

    def init(self):
        """Create SQL view for attendance summary"""
        tools.drop_view_if_exists(self.env.cr, 'attendance_summary_analysis')
        query = """
            CREATE OR REPLACE VIEW attendance_summary_analysis AS (
                WITH attendance_dates AS (
                    -- Get all dates with attendance records
                    SELECT DISTINCT
                        employee_id,
                        DATE(check_in) as attendance_date,
                        MIN(check_in) as check_in_time,
                        MAX(check_out) as check_out_time,
                        EXTRACT(EPOCH FROM (MAX(check_out) - MIN(check_in))) / 3600.0 as worked_hours
                    FROM hr_attendance
                    WHERE check_in IS NOT NULL
                    GROUP BY employee_id, DATE(check_in)
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY employee_id, attendance_date) as id,
                    employee_id,
                    attendance_date,
                    'present' as status,
                    check_in_time,
                    check_out_time,
                    COALESCE(worked_hours, 0) as worked_hours,
                    FALSE as is_late,
                    0.0 as late_minutes,
                    CASE
                        WHEN worked_hours > 8 THEN worked_hours - 8
                        ELSE 0
                    END as overtime_hours,
                    CASE
                        WHEN worked_hours < 8 THEN 8 - worked_hours
                        ELSE 0
                    END as undertime_hours,
                    8.0 as expected_hours
                FROM attendance_dates
            )
        """
        self.env.cr.execute(query)

    def _get_utc_datetime_range(self, date):
        """
        Convert a local date to UTC datetime range for proper comparison.
        This ensures we query the correct date boundaries in UTC timezone.
        """
        # Get user's timezone or default to UTC
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(tz_name)

        # Create timezone-aware datetime for start and end of day
        start_datetime = local_tz.localize(datetime.combine(date, time.min))
        end_datetime = local_tz.localize(datetime.combine(date, time.max))

        # Convert to UTC and remove timezone info (Odoo stores naive UTC datetimes)
        utc_start = start_datetime.astimezone(pytz.utc).replace(tzinfo=None)
        utc_end = end_datetime.astimezone(pytz.utc).replace(tzinfo=None)

        return utc_start, utc_end

    @api.model
    def get_attendance_summary(self, employee_ids=None, start_date=None, end_date=None):
        """
        Get comprehensive attendance summary with absences, late arrivals, overtime.
        Uses 4 batch queries instead of N*M per-employee-per-day queries.
        """
        if not start_date:
            end_date = fields.Date.today()
            start_date = end_date - timedelta(days=30)

        Employee = self.env['hr.employee']
        Attendance = self.env['hr.attendance']
        has_leave_module = 'hr.leave' in self.env

        employees = Employee.browse(employee_ids) if employee_ids else \
            Employee.search([('active', '=', True)])
        if not employees:
            return []

        emp_ids = employees.ids
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(tz_name)

        def _to_utc(d, t):
            return local_tz.localize(datetime.combine(d, t)).astimezone(pytz.utc).replace(tzinfo=None)

        utc_range_start = _to_utc(start_date, time.min)
        utc_range_end = _to_utc(end_date, time.max)

        # ── Batch 1: all attendance records for all employees in range ─────────
        all_atts = Attendance.search_read(
            [('employee_id', 'in', emp_ids),
             ('check_in', '>=', utc_range_start),
             ('check_in', '<=', utc_range_end)],
            fields=['employee_id', 'check_in', 'check_out'],
            order='check_in asc')
        att_index = defaultdict(list)
        for att in all_atts:
            emp_id = att['employee_id'][0]
            local_date = pytz.utc.localize(att['check_in']).astimezone(local_tz).date()
            att_index[(emp_id, local_date)].append(att)

        # ── Batch 2: preload all resource calendars and their attendance lines ──
        emp_cals = employees.resource_calendar_id
        company_cals = employees.mapped('company_id').resource_calendar_id
        all_cals = emp_cals | company_cals
        all_cals.mapped('attendance_ids')  # force prefetch in one query
        calendar_cache = {}
        for cal in all_cals:
            if not cal or cal.id in calendar_cache:
                continue
            day_info = {}
            for line in cal.attendance_ids:
                dow = int(line.dayofweek)
                if dow not in day_info:
                    day_info[dow] = {'hours': 0.0, 'start': line.hour_from}
                day_info[dow]['hours'] += (line.hour_to - line.hour_from)
                day_info[dow]['start'] = min(day_info[dow]['start'], line.hour_from)
            # Store the calendar's own timezone so late-check comparisons use
            # the same reference frame as hour_from (which is in calendar.tz).
            day_info['__tz__'] = cal.tz or tz_name
            calendar_cache[cal.id] = day_info

        emp_cal_map = {}
        for emp in employees:
            cal = emp.resource_calendar_id or emp.company_id.resource_calendar_id
            emp_cal_map[emp.id] = (emp.name, cal.id if cal else None)

        # ── Batch 3: all public holidays for all relevant calendars ────────────
        cal_id_list = list({cid for _, cid in emp_cal_map.values() if cid})
        pub_holidays_raw = self.env['resource.calendar.leaves'].search_read(
            [('calendar_id', 'in', cal_id_list), ('resource_id', '=', False),
             ('date_from', '<=', utc_range_end), ('date_to', '>=', utc_range_start)],
            fields=['calendar_id', 'name', 'date_from', 'date_to'])
        holiday_index = defaultdict(dict)
        for ph in pub_holidays_raw:
            cal_id = ph['calendar_id'][0]
            ph_start = pytz.utc.localize(ph['date_from']).astimezone(local_tz).date()
            ph_end = pytz.utc.localize(ph['date_to']).astimezone(local_tz).date()
            d = max(ph_start, start_date)
            while d <= min(ph_end, end_date):
                holiday_index[cal_id][d] = ph['name']
                d += timedelta(days=1)

        # ── Batch 4: all approved leaves for all employees in range ────────────
        leave_index = defaultdict(dict)
        if has_leave_module:
            raw_leaves = self.env['hr.leave'].search_read(
                [('employee_id', 'in', emp_ids), ('state', '=', 'validate'),
                 ('date_from', '<=', utc_range_end), ('date_to', '>=', utc_range_start)],
                fields=['employee_id', 'date_from', 'date_to', 'holiday_status_id'])
            lt_ids = list({lv['holiday_status_id'][0]
                           for lv in raw_leaves if lv.get('holiday_status_id')})
            lt_map = {lt.id: lt for lt in self.env['hr.leave.type'].browse(lt_ids)}
            for lv in raw_leaves:
                emp_id = lv['employee_id'][0]
                lt_id = lv['holiday_status_id'][0] if lv.get('holiday_status_id') else False
                lt = lt_map.get(lt_id)
                lv_start = pytz.utc.localize(lv['date_from']).astimezone(local_tz).date()
                lv_end = pytz.utc.localize(lv['date_to']).astimezone(local_tz).date()
                lv_info = {
                    'leave_type': lt.name if lt else 'Time Off',
                    'leave_code': (lt.leave_short_code or lt.name[:3].upper()) if lt else 'OFF',
                    'leave_type_id': lt_id,
                    'leave_category': getattr(lt, 'leave_attendance_category', 'absence') if lt else 'absence',
                }
                d = max(lv_start, start_date)
                while d <= min(lv_end, end_date):
                    leave_index[emp_id][d] = lv_info
                    d += timedelta(days=1)

        # ── Build summary (pure in-memory, zero additional DB queries) ─────────
        summary_data = []
        current_date = start_date
        while current_date <= end_date:
            dow = current_date.weekday()
            for emp in employees:
                emp_name, cal_id = emp_cal_map[emp.id]
                day_sched = calendar_cache.get(cal_id, {}).get(dow) if cal_id else None
                expected_hours = day_sched['hours'] if day_sched else 8.0
                exp_start_float = day_sched['start'] if day_sched else 9.0

                if cal_id and day_sched is None:
                    summary_data.append({
                        'employee_id': emp.id, 'employee_name': emp_name,
                        'date': current_date, 'status': 'weekend',
                        'check_in': None, 'check_out': None,
                        'worked_hours': 0, 'expected_hours': 0,
                        'is_late': False, 'late_minutes': 0, 'overtime': 0, 'undertime': 0,
                    })
                    continue

                if cal_id and current_date in holiday_index.get(cal_id, {}):
                    summary_data.append({
                        'employee_id': emp.id, 'employee_name': emp_name,
                        'date': current_date, 'status': 'public_holiday',
                        'holiday_name': holiday_index[cal_id][current_date],
                        'check_in': None, 'check_out': None,
                        'worked_hours': 0, 'expected_hours': 0,
                        'is_late': False, 'late_minutes': 0, 'overtime': 0, 'undertime': 0,
                    })
                    continue

                if emp.id in leave_index and current_date in leave_index[emp.id]:
                    lv = leave_index[emp.id][current_date]
                    summary_data.append({
                        'employee_id': emp.id, 'employee_name': emp_name,
                        'date': current_date, 'status': 'leave',
                        'leave_type': lv['leave_type'],
                        'leave_code': lv['leave_code'],
                        'leave_type_id': lv['leave_type_id'],
                        'leave_category': lv['leave_category'],
                        'check_in': None, 'check_out': None,
                        'worked_hours': 0, 'expected_hours': expected_hours,
                        'is_late': False, 'late_minutes': 0, 'overtime': 0, 'undertime': 0,
                    })
                    continue

                att_records = att_index.get((emp.id, current_date), [])
                if not att_records:
                    summary_data.append({
                        'employee_id': emp.id, 'employee_name': emp_name,
                        'date': current_date, 'status': 'absent',
                        'check_in': None, 'check_out': None,
                        'worked_hours': 0, 'expected_hours': expected_hours,
                        'is_late': False, 'late_minutes': 0, 'overtime': 0, 'undertime': expected_hours,
                    })
                    continue

                check_in_dt = att_records[0]['check_in']
                check_out_dt = att_records[-1]['check_out']
                worked_hours = (check_out_dt - check_in_dt).total_seconds() / 3600.0 \
                    if check_out_dt else 0.0

                exp_h = int(exp_start_float)
                exp_m = int((exp_start_float - exp_h) * 60)
                exp_time_obj = time(exp_h, exp_m)
                # hour_from is stored in the calendar's own timezone, so convert
                # check_in to that timezone before comparing.
                cal_tz_name = calendar_cache.get(cal_id, {}).get('__tz__', tz_name) if cal_id else tz_name
                cal_tz = pytz.timezone(cal_tz_name)
                ci_local = pytz.utc.localize(check_in_dt).astimezone(cal_tz).time()
                is_late = ci_local > exp_time_obj
                late_minutes = 0.0
                if is_late:
                    late_minutes = (datetime.combine(current_date, ci_local) -
                                    datetime.combine(current_date, exp_time_obj)).total_seconds() / 60.0

                summary_data.append({
                    'employee_id': emp.id, 'employee_name': emp_name,
                    'date': current_date, 'status': 'present',
                    'check_in': check_in_dt, 'check_out': check_out_dt,
                    'worked_hours': round(worked_hours, 2),
                    'expected_hours': expected_hours,
                    'is_late': is_late,
                    'late_minutes': round(late_minutes, 0),
                    'overtime': round(max(0.0, worked_hours - expected_hours), 2),
                    'undertime': round(max(0.0, expected_hours - worked_hours), 2),
                })
            current_date += timedelta(days=1)

        # â”€â”€ Roster override: if a shift roster exists, prefer it over the
        # employee calendar for working day/late/overtime interpretation.
        roster_index = {}
        if 'hr.shift.roster.line' in self.env:
            raw_roster_lines = self.env['hr.shift.roster.line'].search_read(
                [('employee_id', 'in', emp_ids),
                 ('date', '>=', start_date),
                 ('date', '<=', end_date),
                 ('roster_id.state', 'in', ['generated', 'confirmed', 'done'])],
                fields=['employee_id', 'date', 'start_time', 'end_time',
                        'break_duration', 'is_weekly_off'])
            for rl in raw_roster_lines:
                roster_index[(rl['employee_id'][0], fields.Date.to_date(rl['date']))] = rl

        for record in summary_data:
            roster_line = roster_index.get((record['employee_id'], record['date']))
            if not roster_line:
                continue

            if record['status'] == 'leave':
                continue

            start_float = roster_line.get('start_time') or 0.0
            end_float = roster_line.get('end_time') or 0.0
            break_duration = roster_line.get('break_duration') or 0.0
            raw_hours = end_float - start_float
            if raw_hours < 0:
                raw_hours += 24.0
            roster_expected_hours = max(0.0, raw_hours - break_duration)
            is_weekly_off = bool(roster_line.get('is_weekly_off'))

            record['expected_hours'] = roster_expected_hours if not is_weekly_off else 0.0

            if record.get('check_in'):
                check_in_dt = record['check_in']
                check_out_dt = record.get('check_out')
                worked_hours = (check_out_dt - check_in_dt).total_seconds() / 3600.0 if check_out_dt else 0.0
                exp_time_obj = time(int(start_float), int((start_float - int(start_float)) * 60))
                cal_tz_name = self.env.user.tz or tz_name
                cal_tz = pytz.timezone(cal_tz_name)
                ci_local = pytz.utc.localize(check_in_dt).astimezone(cal_tz).time()
                is_late = (ci_local > exp_time_obj) and not is_weekly_off
                late_minutes = 0.0
                if is_late:
                    late_minutes = (datetime.combine(record['date'], ci_local) -
                                    datetime.combine(record['date'], exp_time_obj)).total_seconds() / 60.0
                record.update({
                    'status': 'present',
                    'is_late': is_late,
                    'late_minutes': round(late_minutes, 0),
                    'overtime': round(max(0.0, worked_hours - record['expected_hours']), 2),
                    'undertime': round(max(0.0, record['expected_hours'] - worked_hours), 2),
                    'comp_off_eligible': is_weekly_off and worked_hours > 0,
                    'comp_off_hours': round(max(0.0, worked_hours), 2) if is_weekly_off else 0.0,
                })
            elif is_weekly_off:
                record.update({
                    'status': 'weekend',
                    'is_late': False,
                    'late_minutes': 0,
                    'overtime': 0,
                    'undertime': 0,
                    'comp_off_eligible': False,
                    'comp_off_hours': 0.0,
                })
            else:
                record.update({
                    'status': 'absent',
                    'expected_hours': roster_expected_hours,
                    'is_late': False,
                    'late_minutes': 0,
                    'overtime': 0,
                    'undertime': roster_expected_hours,
                    'comp_off_eligible': False,
                    'comp_off_hours': 0.0,
                })

        return summary_data

    def _analyze_employee_day(self, employee, date, has_leave_module=False):
        """Analyze a single employee's attendance for a single day"""
        Attendance = self.env['hr.attendance']

        # Get UTC datetime range for proper timezone handling
        utc_start, utc_end = self._get_utc_datetime_range(date)

        # Get attendance records for this day
        attendance_records = Attendance.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', utc_start),
            ('check_in', '<=', utc_end),
        ], order='check_in')

        # Get working schedule
        resource_calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id

        if not resource_calendar:
            # No calendar defined, assume standard 8-hour day
            expected_hours = 8.0
            expected_start_time = time(9, 0)  # 9 AM
        else:
            # Get calendar for this specific day
            day_name = date.strftime('%A').lower()

            # Find working hours for this day
            attendance_lines = resource_calendar.attendance_ids.filtered(
                lambda a: a.dayofweek == str(date.weekday())
            )

            if not attendance_lines:
                # Weekend or non-working day
                return {
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'date': date,
                    'status': 'weekend',
                    'check_in': None,
                    'check_out': None,
                    'worked_hours': 0,
                    'expected_hours': 0,
                    'is_late': False,
                    'late_minutes': 0,
                    'overtime': 0,
                    'undertime': 0,
                }

            # Calculate expected hours
            expected_hours = sum(
                (line.hour_to - line.hour_from) for line in attendance_lines
            )
            expected_start_time = min(line.hour_from for line in attendance_lines)

        # Check for Public Holidays (company-wide time off)
        if resource_calendar:
            CalendarLeaves = self.env['resource.calendar.leaves']
            # Check for company-wide public holidays (no specific employee)
            public_holidays = CalendarLeaves.search([
                ('calendar_id', '=', resource_calendar.id),
                ('resource_id', '=', False),  # Public holidays have no specific resource
                ('date_from', '<=', utc_end),
                ('date_to', '>=', utc_start),
            ])

            if public_holidays:
                return {
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'date': date,
                    'status': 'public_holiday',
                    'holiday_name': public_holidays[0].name,
                    'check_in': None,
                    'check_out': None,
                    'worked_hours': 0,
                    'expected_hours': 0,
                    'is_late': False,
                    'late_minutes': 0,
                    'overtime': 0,
                    'undertime': 0,
                }

        # Check if on leave (only if hr_holidays module is installed)
        if has_leave_module:
            Leave = self.env['hr.leave']
            leave_records = Leave.search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', utc_end),
                ('date_to', '>=', utc_start),
            ])

            if leave_records:
                leave_type_rec = leave_records[0].holiday_status_id
                leave_code = leave_type_rec.leave_short_code or leave_type_rec.name[:3].upper()
                leave_category = leave_type_rec.leave_attendance_category or 'absence'
                return {
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'date': date,
                    'status': 'leave',
                    'leave_type': leave_type_rec.name,  # Full name for summary
                    'leave_code': leave_code,  # Short code for display
                    'leave_type_id': leave_type_rec.id,  # For grouping
                    'leave_category': leave_category,  # 'absence' or 'worked'
                    'check_in': None,
                    'check_out': None,
                    'worked_hours': 0,
                    'expected_hours': expected_hours,
                    'is_late': False,
                    'late_minutes': 0,
                    'overtime': 0,
                    'undertime': 0,
                }

        # Analyze attendance
        if not attendance_records:
            # Absent
            return {
                'employee_id': employee.id,
                'employee_name': employee.name,
                'date': date,
                'status': 'absent',
                'check_in': None,
                'check_out': None,
                'worked_hours': 0,
                'expected_hours': expected_hours,
                'is_late': False,
                'late_minutes': 0,
                'overtime': 0,
                'undertime': expected_hours,
            }

        # Present - calculate details
        check_in = attendance_records[0].check_in
        check_out = attendance_records[-1].check_out if attendance_records[-1].check_out else None

        # Calculate worked hours
        if check_out:
            worked_hours = (check_out - check_in).total_seconds() / 3600.0
        else:
            worked_hours = 0

        # Check if late
        check_in_time = check_in.time()
        if isinstance(expected_start_time, float):
            # Convert float hours to time
            hours = int(expected_start_time)
            minutes = int((expected_start_time - hours) * 60)
            expected_time_obj = time(hours, minutes)
        else:
            expected_time_obj = expected_start_time

        # Calculate late minutes
        is_late = check_in_time > expected_time_obj
        if is_late:
            check_in_datetime = datetime.combine(date, check_in_time)
            expected_datetime = datetime.combine(date, expected_time_obj)
            late_minutes = (check_in_datetime - expected_datetime).total_seconds() / 60.0
        else:
            late_minutes = 0

        # Calculate overtime/undertime
        overtime = max(0, worked_hours - expected_hours)
        undertime = max(0, expected_hours - worked_hours)

        return {
            'employee_id': employee.id,
            'employee_name': employee.name,
            'date': date,
            'status': 'present',
            'check_in': check_in,
            'check_out': check_out,
            'worked_hours': round(worked_hours, 2),
            'expected_hours': expected_hours,
            'is_late': is_late,
            'late_minutes': round(late_minutes, 0),
            'overtime': round(overtime, 2),
            'undertime': round(undertime, 2),
        }

    @api.model
    def _compute_summary_stats(self, summary_data):
        """Aggregate statistics from pre-computed summary data (no DB queries)."""
        stats = {
            'total_days': 0, 'present_days': 0, 'absent_days': 0,
            'leave_days': 0, 'public_holiday_days': 0, 'late_arrivals': 0,
            'total_overtime': 0.0, 'total_undertime': 0.0,
            'total_worked_hours': 0.0, 'total_expected_hours': 0.0,
        }
        for record in summary_data:
            stats['total_days'] += 1
            status = record['status']
            if status == 'present':
                stats['present_days'] += 1
                stats['total_worked_hours'] += record.get('worked_hours', 0)
                if record.get('is_late'):
                    stats['late_arrivals'] += 1
                stats['total_overtime'] += record.get('overtime', 0)
                stats['total_undertime'] += record.get('undertime', 0)
            elif status == 'absent':
                stats['absent_days'] += 1
            elif status == 'leave':
                stats['leave_days'] += 1
            elif status == 'public_holiday':
                stats['public_holiday_days'] += 1
            if status in ('present', 'absent'):
                stats['total_expected_hours'] += record.get('expected_hours', 0)
        return stats

    @api.model
    def get_monthly_summary_statistics(self, start_date, end_date, employee_ids=None):
        """Get aggregated statistics for dashboard"""
        summary_data = self.get_attendance_summary(employee_ids, start_date, end_date)
        return self._compute_summary_stats(summary_data)
