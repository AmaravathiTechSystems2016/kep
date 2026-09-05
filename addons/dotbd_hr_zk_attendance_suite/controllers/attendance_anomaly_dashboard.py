# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit

################################################################################
from odoo import http
from odoo.http import request
from datetime import datetime, timedelta, time
import json


class AttendanceAnomalyDashboard(http.Controller):

    @http.route('/attendance/anomaly/dashboard', type='http', auth='user', website=False)
    def attendance_anomaly_dashboard(self, start_date=None, end_date=None, **kwargs):
        """Main dashboard route with date range support"""
        # Parse date parameters if provided, otherwise use default (last 30 days)
        if start_date and end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                # If invalid dates, fall back to default
                end_date_obj = datetime.now().date()
                start_date_obj = end_date_obj - timedelta(days=30)
        else:
            # Default: last 30 days
            end_date_obj = datetime.now().date()
            start_date_obj = end_date_obj - timedelta(days=30)

        # Get anomaly data
        dashboard_data = self._get_dashboard_data(start_date_obj, end_date_obj)

        return request.render('dotbd_hr_zk_attendance_suite.attendance_anomaly_dashboard_template', {
            'dashboard_data': dashboard_data,
            'start_date': start_date_obj,
            'end_date': end_date_obj,
            'json': json,
        })

    @http.route('/attendance/anomaly/dashboard/data', type='jsonrpc', auth='user')
    def get_dashboard_data(self, start_date=None, end_date=None, **kwargs):
        """JSON endpoint for dashboard data"""
        if not start_date or not end_date:
            end_date_obj = datetime.now().date()
            start_date_obj = end_date_obj - timedelta(days=30)
        else:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()

        return self._get_dashboard_data(start_date_obj, end_date_obj)

    def _get_dashboard_data(self, start_date, end_date):
        """Get all dashboard statistics and data"""
        Anomaly = request.env['attendance.anomaly.analysis']
        AttendanceSummary = request.env['attendance.summary.analysis']
        LateCheckIn = request.env['late.check.in']
        HrAttendance = request.env['hr.attendance']

        # Base domain for date range
        domain = [
            ('attendance_date', '>=', start_date),
            ('attendance_date', '<=', end_date)
        ]

        # Domain for late check-in
        late_domain = [
            ('date', '>=', start_date),
            ('date', '<=', end_date)
        ]

        # ── Anomaly counts via raw SQL (SQL view — ORM _read_group unreliable) ──
        cr = request.env.cr
        cr.execute("""
            SELECT anomaly_type, COUNT(*) AS cnt
            FROM attendance_anomaly_analysis
            WHERE attendance_date >= %s AND attendance_date <= %s
              AND anomaly_type IS NOT NULL
            GROUP BY anomaly_type
        """, [start_date, end_date])
        type_counts = {r['anomaly_type']: r['cnt'] for r in cr.dictfetchall()}
        missing_checkout_count = type_counts.get('missing_checkout', 0)
        duplicate_checkin_count = type_counts.get('duplicate_checkin', 0)
        missing_checkin_count = type_counts.get('missing_checkin', 0)
        total_anomalies = missing_checkout_count + duplicate_checkin_count + missing_checkin_count

        # ── Top 10 employees by anomaly count (raw SQL) ───────────────────────
        cr.execute("""
            SELECT a.employee_id, e.name AS employee_name,
                   COALESCE(e.device_id_num, e.barcode, 'No ID') AS device_id_num,
                   a.anomaly_type, COUNT(*) AS cnt
            FROM attendance_anomaly_analysis a
            JOIN hr_employee e ON e.id = a.employee_id
            WHERE a.attendance_date >= %s AND a.attendance_date <= %s
              AND a.anomaly_type IS NOT NULL
              AND a.employee_id IS NOT NULL
            GROUP BY a.employee_id, e.name, e.device_id_num, e.barcode, a.anomaly_type
        """, [start_date, end_date])
        employee_anomaly_count = {}
        for row in cr.dictfetchall():
            emp_id = row['employee_id']
            if emp_id not in employee_anomaly_count:
                employee_anomaly_count[emp_id] = {
                    'employee': row['employee_name'],
                    'device_id_num': row['device_id_num'],
                    'count': 0,
                    'missing_checkout': 0, 'duplicate_checkin': 0, 'missing_checkin': 0,
                }
            employee_anomaly_count[emp_id]['count'] += row['cnt']
            employee_anomaly_count[emp_id][row['anomaly_type']] += row['cnt']

        top_employees = sorted(
            employee_anomaly_count.values(), key=lambda x: x['count'], reverse=True)[:10]

        # ── Daily anomaly trend (raw SQL) ─────────────────────────────────────
        cr.execute("""
            SELECT attendance_date, anomaly_type, COUNT(*) AS cnt
            FROM attendance_anomaly_analysis
            WHERE attendance_date >= %s AND attendance_date <= %s
              AND anomaly_type IS NOT NULL
            GROUP BY attendance_date, anomaly_type
            ORDER BY attendance_date
        """, [start_date, end_date])
        daily_trend = {}
        for row in cr.dictfetchall():
            date_str = str(row['attendance_date'])
            if date_str not in daily_trend:
                daily_trend[date_str] = {
                    'date': date_str,
                    'missing_checkout': 0, 'duplicate_checkin': 0,
                    'missing_checkin': 0, 'total': 0,
                }
            daily_trend[date_str][row['anomaly_type']] += row['cnt']
            daily_trend[date_str]['total'] += row['cnt']

        daily_trend_list = sorted(daily_trend.values(), key=lambda x: x['date'])

        # Get recent anomalies (last 10)
        recent_anomalies = Anomaly.search(domain, order='attendance_date desc', limit=10)
        recent_anomalies_data = [{
            'employee': a.employee_id.name,
            'date': str(a.attendance_date),
            'type': dict(Anomaly._fields['anomaly_type'].selection).get(a.anomaly_type),
            'checkin_count': a.checkin_count,
            'checkout_count': a.checkout_count,
            'total_punches': a.total_punches,
        } for a in recent_anomalies]

        # ── Single attendance summary call (was called twice before) ──────────
        attendance_summary_data = AttendanceSummary.get_attendance_summary(
            employee_ids=None, start_date=start_date, end_date=end_date)
        attendance_stats = AttendanceSummary._compute_summary_stats(attendance_summary_data)

        # Build device_id map for all employees in summary data
        _emp_ids = {r['employee_id'] for r in attendance_summary_data}
        _emp_device_map = {
            e.id: e.device_id_num or e.barcode or 'No ID'
            for e in request.env['hr.employee'].sudo().browse(list(_emp_ids))
        }

        # Process employee attendance data
        employee_attendance = {}
        for record in attendance_summary_data:
            emp_id = record['employee_id']
            emp_name = record['employee_name']

            if emp_id not in employee_attendance:
                employee_attendance[emp_id] = {
                    'employee_id': emp_id,
                    'employee_name': emp_name,
                    'device_id_num': _emp_device_map.get(emp_id, ''),
                    'present_count': 0,
                    'absent_count': 0,
                    'late_count': 0,
                    'on_time_count': 0,
                    'total_worked_hours': 0,
                    'total_overtime': 0,
                }

            if record['status'] == 'present':
                employee_attendance[emp_id]['present_count'] += 1
                employee_attendance[emp_id]['total_worked_hours'] += record.get('worked_hours', 0)
                employee_attendance[emp_id]['total_overtime'] += record.get('overtime', 0)

                if record.get('is_late'):
                    employee_attendance[emp_id]['late_count'] += 1
                else:
                    employee_attendance[emp_id]['on_time_count'] += 1
            elif record['status'] == 'absent':
                employee_attendance[emp_id]['absent_count'] += 1

        # Convert to list and sort
        employee_list = list(employee_attendance.values())

        # Top 10 most present employees
        top_present = sorted(employee_list, key=lambda x: x['present_count'], reverse=True)[:10]

        # Top 10 most absent employees
        top_absent = sorted(employee_list, key=lambda x: x['absent_count'], reverse=True)[:10]

        # Top 10 most late employees - with percentage calculation
        for emp in employee_list:
            total_days = emp['present_count']
            emp['total_present_days'] = total_days
            emp['late_percentage'] = (emp['late_count'] / total_days * 100) if total_days > 0 else 0
            emp['on_time_percentage'] = (emp['on_time_count'] / total_days * 100) if total_days > 0 else 0

        top_late = sorted(employee_list, key=lambda x: x['late_count'], reverse=True)[:10]

        # Top 10 most on-time employees
        top_on_time = sorted(employee_list, key=lambda x: x['on_time_count'], reverse=True)[:10]

        # ===== EMPLOYEE LEAVE (TIME OFF) LIST =====
        employee_leave_dict = {}
        for record in attendance_summary_data:
            if record['status'] != 'leave':
                continue
            emp_id = record['employee_id']
            if emp_id not in employee_leave_dict:
                employee_leave_dict[emp_id] = {
                    'employee_id': emp_id,
                    'employee_name': record['employee_name'],
                    'device_id_num': _emp_device_map.get(emp_id, ''),
                    'leave_days': 0,
                    'leave_hours': 0.0,
                    'leave_dates': [],
                }
            entry = employee_leave_dict[emp_id]
            entry['leave_days'] += 1
            entry['leave_hours'] += record.get('expected_hours', 8.0)
            entry['leave_dates'].append({
                'date': str(record['date']),
                'leave_type': record.get('leave_type', 'Time Off'),
            })
        employee_leave_list = sorted(
            employee_leave_dict.values(), key=lambda x: x['leave_days'], reverse=True)

        # ===== LATE CHECK-IN STATISTICS (read_group — no full table load) =====
        # State counts + totals in one query (was: search + 4 search_counts)
        state_groups = LateCheckIn._read_group(
            late_domain, ['state'],
            ['late_minutes:sum', 'penalty_amount:sum', '__count'])
        total_late_incidents = 0
        total_penalty_amount = 0.0
        total_late_minutes_all = 0.0
        state_counts = {}
        for state, late_sum, penalty_sum, count in state_groups:
            total_late_incidents += count
            total_penalty_amount += penalty_sum
            total_late_minutes_all += late_sum
            state_counts[state] = count
        avg_late_minutes = total_late_minutes_all / total_late_incidents if total_late_incidents else 0
        avg_penalty_per_incident = total_penalty_amount / total_late_incidents if total_late_incidents else 0
        draft_count = state_counts.get('draft', 0)
        approved_count = state_counts.get('approved', 0)
        refused_count = state_counts.get('refused', 0)
        deducted_count = state_counts.get('deducted', 0)

        # Daily late trend in one query
        daily_late_groups = LateCheckIn._read_group(
            late_domain, ['date:day'],
            ['late_minutes:sum', 'penalty_amount:sum', '__count'])
        daily_late_trend_list = sorted([{
            'date': str(d),
            'count': cnt,
            'total_minutes': late_sum,
            'total_penalty': penalty_sum,
        } for d, late_sum, penalty_sum, cnt in daily_late_groups], key=lambda x: x['date'])

        # Employee late stats in one query (was: Python loop over all records)
        emp_state_groups = LateCheckIn._read_group(
            late_domain, ['employee_id', 'state'],
            ['late_minutes:sum', 'penalty_amount:sum', '__count'])
        employee_late_stats = {}
        for emp, state, late_sum, penalty_sum, count in emp_state_groups:
            if not emp:
                continue
            emp_id = emp.id
            if emp_id not in employee_late_stats:
                employee_late_stats[emp_id] = {
                    'employee_id': emp_id,
                    'employee_name': emp.name,
                    'device_id_num': emp.device_id_num or emp.barcode or 'No ID',
                    'late_count': 0, 'total_late_minutes': 0.0, 'total_penalty': 0.0,
                    'draft': 0, 'approved': 0, 'refused': 0, 'deducted': 0,
                }
            s = employee_late_stats[emp_id]
            s['late_count'] += count
            s['total_late_minutes'] += late_sum
            s['total_penalty'] += penalty_sum
            s[state] += count

        top_late_employees = sorted(
            employee_late_stats.values(), key=lambda x: x['late_count'], reverse=True)[:10]
        top_penalty_employees = sorted(
            employee_late_stats.values(), key=lambda x: x['total_penalty'], reverse=True)[:10]

        # Recent late check-ins (last 10)
        recent_late_records = LateCheckIn.search(late_domain, order='date desc', limit=10)
        recent_late_data = [{
            'employee': r.employee_id.name,
            'device_id_num': r.employee_id.device_id_num or r.employee_id.barcode or 'No ID',
            'date': str(r.date),
            'late_minutes': r.late_minutes,
            'actual_late_minutes': getattr(r, 'actual_late_minutes', r.late_minutes),  # Safe fallback
            'penalty_amount': r.penalty_amount,
            'state': r.state,
            'state_label': dict(LateCheckIn._fields['state'].selection).get(r.state),
        } for r in recent_late_records]

        # ===== MANUAL ATTENDANCE TRACKING =====
        # Use datetime boundaries (not date) to avoid missing records after midnight UTC
        manual_attendance_domain = [
            ('check_in', '>=', datetime.combine(start_date, time.min)),
            ('check_in', '<=', datetime.combine(end_date, time.max)),
            ('zk_punch_count', '=', 0),  # No biometric device punches
        ]

        total_manual_entries = HrAttendance.search_count(manual_attendance_domain)
        manual_attendances = HrAttendance.search(
            manual_attendance_domain, order='check_in desc', limit=20)

        # Identify manual entry anomalies
        manual_anomalies = []
        for att in manual_attendances:
            anomaly_type = None
            if not att.check_out:
                anomaly_type = 'Missing Check-out'
            elif att.check_in and att.check_out and att.check_in >= att.check_out:
                anomaly_type = 'Invalid Time'

            manual_anomalies.append({
                'employee': att.employee_id.name,
                'device_id_num': att.employee_id.device_id_num or att.employee_id.barcode or 'No ID',
                'check_in': str(att.check_in) if att.check_in else 'N/A',
                'check_out': str(att.check_out) if att.check_out else 'N/A',
                'date': str(att.check_in.date()) if att.check_in else 'N/A',
                'anomaly_type': anomaly_type or 'Normal',
                'source': 'Manual Entry',
            })

        # Count anomalies
        manual_missing_checkout = len([a for a in manual_anomalies if a['anomaly_type'] == 'Missing Check-out'])
        manual_invalid_time = len([a for a in manual_anomalies if a['anomaly_type'] == 'Invalid Time'])

        return {
            'summary': {
                'total': total_anomalies,
                'missing_checkout': missing_checkout_count,
                'duplicate_checkin': duplicate_checkin_count,
                'missing_checkin': missing_checkin_count,
            },
            'attendance_stats': attendance_stats,
            'top_employees': top_employees,
            'daily_trend': daily_trend_list,
            'recent_anomalies': recent_anomalies_data,
            'top_present': top_present,
            'top_absent': top_absent,
            'top_late': top_late,
            'top_on_time': top_on_time,
            # Employee leave data
            'employee_leave_list': employee_leave_list,
            # Late check-in data
            'late_check_in_stats': {
                'total_incidents': total_late_incidents,
                'total_penalty': total_penalty_amount,
                'avg_late_minutes': avg_late_minutes,
                'avg_penalty': avg_penalty_per_incident,
                'draft': draft_count,
                'approved': approved_count,
                'refused': refused_count,
                'deducted': deducted_count,
            },
            'late_daily_trend': daily_late_trend_list,
            'top_late_employees': top_late_employees,
            'top_penalty_employees': top_penalty_employees,
            'recent_late_records': recent_late_data,
            # Manual attendance tracking
            'manual_attendance_stats': {
                'total_manual_entries': total_manual_entries,
                'manual_missing_checkout': manual_missing_checkout,
                'manual_invalid_time': manual_invalid_time,
            },
            'manual_attendance_list': manual_anomalies,
        }
