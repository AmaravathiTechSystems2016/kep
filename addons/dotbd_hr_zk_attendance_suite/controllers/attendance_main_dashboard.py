# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit
#
################################################################################
import calendar
from datetime import date, datetime, timedelta

from odoo import http
from odoo.http import request


def _export_flag_key(uid):
    return f'attendance.export.running.{uid}'


class AttendanceMainDashboard(http.Controller):

    def _has_group(self, xmlid):
        """Check optional access-suite groups without breaking standalone installs."""
        try:
            return request.env.user.has_group(xmlid)
        except (KeyError, ValueError):
            return False

    def _is_attendance_officer(self):
        """Return True if the current user has Officer or higher access."""
        env = request.env
        return (
            self._has_group('dotbd_hr_zk_attendance_suite.group_attendance_officer')
            or self._has_group('dotbd_hr_zk_attendance_suite.group_attendance_manager')
            or self._has_group('dotbd_hr_zk_attendance_suite.group_attendance_admin')
            or self._has_group('dotbd_hr_access_control_suite.group_hr_officer')
            or self._has_group('dotbd_hr_access_control_suite.group_hr_manager')
            or self._has_group('dotbd_hr_access_control_suite.group_hr_executive')
        )

    def _is_department_manager(self):
        return self._has_group(
            'dotbd_hr_access_control_suite.group_hr_department_manager'
        )

    @http.route('/attendance/export/status', type='jsonrpc', auth='user')
    def get_export_status(self):
        """Return whether a report generation is currently running for this user."""
        uid = request.env.uid
        key = _export_flag_key(uid)
        val = request.env['ir.config_parameter'].sudo().get_param(key, '')
        if not val:
            return {'running': False}
        # Treat flags older than 30 minutes as stale (handles server crash/restart)
        try:
            ts = datetime.fromisoformat(val)
            if (datetime.now() - ts).total_seconds() > 1800:
                request.env['ir.config_parameter'].sudo().set_param(key, '')
                return {'running': False}
        except Exception:
            pass
        return {'running': True}

    @http.route('/attendance/main/dashboard/filters', type='jsonrpc', auth='user')
    def get_filters(self):
        """Return departments and employees for filter dropdowns."""
        if self._is_department_manager():
            departments = request.env['hr.department'].sudo().search_read(
                [('manager_id.user_id', '=', request.env.uid)],
                ['id', 'name'], order='name asc'
            )
            employees = request.env['hr.employee'].sudo().search_read(
                [('active', '=', True),
                 ('department_id.manager_id.user_id', '=', request.env.uid)],
                ['id', 'name'], order='name asc'
            )
            return {'departments': departments, 'employees': employees}

        if not self._is_attendance_officer():
            # Regular employees see no filter options — data is locked to themselves
            return {'departments': [], 'employees': []}

        departments = request.env['hr.department'].sudo().search_read(
            [], ['id', 'name'], order='name asc'
        )
        employees = request.env['hr.employee'].sudo().search_read(
            [('active', '=', True)], ['id', 'name'], order='name asc'
        )
        return {
            'departments': departments,
            'employees': employees,
        }

    @http.route('/attendance/main/dashboard/data', type='jsonrpc', auth='user')
    def get_dashboard_data(self, month, year, department_id=False, employee_id=False):
        """Return today's summary counts and monthly attendance calendar matrix."""
        month = int(month)
        year = int(year)
        today = date.today()

        # ── Access control: non-officers can only see their own data ──────────
        scope_domain = []
        if self._is_department_manager():
            scope_domain = [('employee_id.department_id.manager_id.user_id', '=', request.env.uid)]
        elif not self._is_attendance_officer():
            own_employee = request.env['hr.employee'].sudo().search(
                [('user_id', '=', request.env.uid)], limit=1)
            if own_employee:
                employee_id = own_employee.id
            else:
                # No linked employee record — return empty data
                return {
                    'today': {
                        'total': 0, 'present': 0, 'absent': 0, 'on_leave': 0,
                        'late': 0, 'total_fine': 0.0, 'currency_symbol': '',
                        'late_enabled': False,
                    },
                    'days': [], 'month_name': '', 'calendar': [],
                }
            department_id = False  # ignore any dept filter passed by client

        # ── Penalty settings ───────────────────────────────────────────────────
        ICP = request.env['ir.config_parameter'].sudo()
        enable_late_raw = ICP.get_param(
            'dotbd_hr_zk_attendance_suite.enable_late_penalties', 'False')
        enable_late = enable_late_raw in ('True', '1', 'true')

        # ── Weekend day configuration ──────────────────────────────────────────
        _day_codes = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
        weekend_days = set()
        for _num, _code in _day_codes.items():
            _val = ICP.get_param(f'dotbd_hr_zk_attendance_suite.weekend_{_code}', 'False')
            if _val in ('True', '1', 'true'):
                weekend_days.add(_num)
        if not weekend_days:
            weekend_days = {4, 5}  # Default: Friday + Saturday (Bangladesh)

        currency_symbol = request.env.company.currency_id.symbol or ''

        # ── Today's holiday + upcoming holidays ───────────────────────────────
        today_holiday_name = ''
        upcoming_holidays = []
        all_holidays = request.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('date_to', '>=', datetime(today.year, today.month, today.day)),
        ], order='date_from asc', limit=30)
        for _h in all_holidays:
            _h_start = _h.date_from.date()
            _h_end = _h.date_to.date()
            if _h_start <= today <= _h_end:
                today_holiday_name = _h.name or 'Public Holiday'
            elif _h_start > today and len(upcoming_holidays) < 2:
                upcoming_holidays.append({
                    'name': _h.name or 'Public Holiday',
                    'date': _h_start.strftime('%b %d'),
                })

        # ── Build domain for summary view ──────────────────────────────────────
        domain = list(scope_domain)
        if department_id:
            domain.append(('employee_id.department_id', '=', int(department_id)))
        if employee_id:
            domain.append(('employee_id', '=', int(employee_id)))

        # ── Today's summary counts ─────────────────────────────────────────────
        today_domain = domain + [('attendance_date', '=', today)]
        summary_recs = request.env['attendance.summary.analysis'].sudo().search(today_domain)

        total_employees = request.env['hr.employee'].sudo().search_count(
            [('active', '=', True)] + (
                [('department_id', '=', int(department_id))] if department_id else []
            ) + (
                [('id', '=', int(employee_id))] if employee_id else []
            ) + (
                [('department_id.manager_id.user_id', '=', request.env.uid)]
                if scope_domain else []
            )
        )
        present = sum(1 for r in summary_recs if r.status == 'present')

        # ── Today's on-leave count (hr.leave, include pending approvals) ──────
        # The SQL view only contains present records so we query hr.leave directly.
        on_leave = 0
        if 'hr.leave' in request.env:
            today_leave_domain = [
                ('state', 'in', ['validate', 'validate1', 'confirm']),
                ('request_date_from', '<=', today),
                ('request_date_to', '>=', today),
            ]
            if department_id:
                today_leave_domain.append(
                    ('employee_id.department_id', '=', int(department_id)))
            if employee_id:
                today_leave_domain.append(('employee_id', '=', int(employee_id)))
            on_leave = request.env['hr.leave'].sudo().search_count(today_leave_domain)

        # ── Today's late & fine ────────────────────────────────────────────────
        late_today = 0
        total_fine_today = 0.0
        if enable_late:
            late_today_domain = [('date', '=', today)]
            if department_id:
                late_today_domain.append(
                    ('employee_id.department_id', '=', int(department_id)))
            if employee_id:
                late_today_domain.append(('employee_id', '=', int(employee_id)))
            late_today_recs = request.env['late.check.in'].sudo().search(
                late_today_domain)
            late_today = len(late_today_recs)
            total_fine_today = sum(r.penalty_amount for r in late_today_recs)

        absent = total_employees - present - on_leave

        # ── Monthly calendar data ──────────────────────────────────────────────
        days_in_month = calendar.monthrange(year, month)[1]
        month_domain = domain + [
            ('attendance_date', '>=', date(year, month, 1)),
            ('attendance_date', '<=', date(year, month, days_in_month)),
        ]
        month_recs = request.env['attendance.summary.analysis'].sudo().search(month_domain)

        # Index by (employee_id, attendance_date)
        rec_index = {}
        for r in month_recs:
            rec_index[(r.employee_id.id, r.attendance_date)] = r

        # ── Monthly late check-in lookup ───────────────────────────────────────
        late_set = set()  # {(employee_id, date)}
        if enable_late:
            month_late_domain = [
                ('date', '>=', date(year, month, 1)),
                ('date', '<=', date(year, month, days_in_month)),
            ]
            if department_id:
                month_late_domain.append(
                    ('employee_id.department_id', '=', int(department_id)))
            if employee_id:
                month_late_domain.append(('employee_id', '=', int(employee_id)))
            month_late_recs = request.env['late.check.in'].sudo().search(
                month_late_domain)
            for lr in month_late_recs:
                late_set.add((lr.employee_id.id, lr.date))

        # ── Monthly leave lookup ────────────────────────────────────────────────
        # Build {(employee_id, date): short_code} for all leave days in the month.
        # Includes validated, awaiting-second-approval, and pending-approval leaves
        # so that employees on leave are never shown as absent.
        leave_map = {}
        if 'hr.leave' in request.env:
            month_leave_domain = [
                ('state', 'in', ['validate', 'validate1', 'confirm']),
                ('request_date_from', '<=', date(year, month, days_in_month)),
                ('request_date_to', '>=', date(year, month, 1)),
            ]
            if department_id:
                month_leave_domain.append(
                    ('employee_id.department_id', '=', int(department_id)))
            if employee_id:
                month_leave_domain.append(('employee_id', '=', int(employee_id)))
            month_leave_recs = request.env['hr.leave'].sudo().search(month_leave_domain)
            month_start = date(year, month, 1)
            month_end = date(year, month, days_in_month)
            for lr in month_leave_recs:
                ht = lr.holiday_status_id
                code = (ht.leave_short_code if ht and ht.leave_short_code
                        else (ht.name[:2].upper() if ht else 'L'))
                lv_start = max(lr.request_date_from, month_start)
                lv_end = min(lr.request_date_to, month_end)
                d_iter = lv_start
                while d_iter <= lv_end:
                    key = (lr.employee_id.id, d_iter)
                    if key not in leave_map:
                        leave_map[key] = code
                    d_iter += timedelta(days=1)

        # Public holidays
        holiday_dates = set()
        public_holidays = request.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('date_from', '>=', datetime(year, month, 1)),
            ('date_to', '<=', datetime(year, month, days_in_month, 23, 59, 59)),
        ])
        for h in public_holidays:
            d = h.date_from.date()
            while d <= h.date_to.date():
                if d.month == month:
                    holiday_dates.add(d)
                d = date(d.year, d.month, d.day + 1) if d.day < days_in_month else date(d.year, d.month + 1, 1) if d.month < 12 else date(d.year + 1, 1, 1)

        # Get employees
        emp_domain = [('active', '=', True)]
        if department_id:
            emp_domain.append(('department_id', '=', int(department_id)))
        if employee_id:
            emp_domain.append(('id', '=', int(employee_id)))
        if scope_domain:
            emp_domain.append(('department_id.manager_id.user_id', '=', request.env.uid))
        employees = request.env['hr.employee'].sudo().search(emp_domain, order='name asc')

        # Build calendar rows
        calendar_data = []
        days_list = list(range(1, days_in_month + 1))

        for emp in employees:
            row = {
                'employee_id': emp.id,
                'employee_name': emp.name,
                'job_title': emp.job_title or emp.job_id.name if emp.job_id else '',
                'device_id_num': emp.device_id_num or 'No ID',
                'avatar_url': f'/web/image/hr.employee/{emp.id}/image_128',
                'days': [],
                'summary': {'P': 0, 'A': 0, 'L': 0, 'W': 0, 'H': 0, 'Late': 0},
            }
            for day in days_list:
                d = date(year, month, day)
                weekday = d.weekday()  # 0=Mon, 6=Sun
                is_weekend = weekday in weekend_days
                is_holiday = d in holiday_dates
                is_future = d > today
                is_late_day = (emp.id, d) in late_set

                rec = rec_index.get((emp.id, d))
                if is_holiday:
                    cell_class = 'o_cell_holiday'
                    cell_text = 'H'
                    row['summary']['H'] += 1
                elif is_weekend:
                    cell_class = 'o_cell_weekend'
                    cell_text = 'W'
                    row['summary']['W'] += 1
                elif is_future:
                    cell_class = 'o_cell_none'
                    cell_text = ''
                elif rec:
                    status = rec.status
                    if status == 'present':
                        if is_late_day:
                            cell_class = 'o_cell_present_late'
                            cell_text = '\u2713'
                            row['summary']['P'] += 1
                            row['summary']['Late'] += 1
                        else:
                            cell_class = 'o_cell_present'
                            cell_text = '\u2713'
                            row['summary']['P'] += 1
                    elif status == 'leave':
                        cell_class = 'o_cell_leave'
                        cell_text = 'L'
                        row['summary']['L'] += 1
                    else:
                        cell_class = 'o_cell_absent'
                        cell_text = 'A'
                        row['summary']['A'] += 1
                else:
                    # No attendance record — check if employee is on leave
                    leave_code = leave_map.get((emp.id, d))
                    if leave_code:
                        cell_class = 'o_cell_leave'
                        cell_text = leave_code
                        row['summary']['L'] += 1
                    else:
                        cell_class = 'o_cell_absent'
                        cell_text = 'A'
                        row['summary']['A'] += 1

                row['days'].append({
                    'day': day,
                    'day_name': d.strftime('%a'),
                    'cell_class': cell_class,
                    'cell_text': cell_text,
                    'is_weekend': is_weekend,
                    'is_today': d == today,
                })
            calendar_data.append(row)

        return {
            'today': {
                'total': total_employees,
                'present': present,
                'absent': absent,
                'on_leave': on_leave,
                'late': late_today,
                'total_fine': total_fine_today,
                'currency_symbol': currency_symbol,
                'late_enabled': enable_late,
            },
            'today_holiday': today_holiday_name,
            'upcoming_holidays': upcoming_holidays,
            'weekend_days': sorted(weekend_days),
            'days': days_list,
            'month_name': date(year, month, 1).strftime('%B %Y'),
            'calendar': calendar_data,
        }
