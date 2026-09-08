# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#
################################################################################
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
import base64
from io import BytesIO
import xlsxwriter
import pytz
from datetime import datetime, timedelta


class AttendanceReportWizard(models.TransientModel):
    """Wizard to generate attendance reports"""
    _name = 'attendance.report.wizard'
    _description = 'Attendance Report Generator'

    start_date = fields.Date(string='Start Date', required=True,
                             default=lambda self: fields.Date.today().replace(day=1))
    end_date = fields.Date(string='End Date', required=True,
                           default=fields.Date.today)
    employee_ids = fields.Many2many('hr.employee', string='Employees',
                                    help='Leave empty for all employees')
    report_type = fields.Selection([
        ('summary', 'Summary Report'),
        ('detailed', 'Detailed Report'),
        ('anomaly', 'Anomaly Report'),
        ('late_checkin', 'Late Check-in Report'),
    ], string='Report Type', default='summary', required=True)

    report_file = fields.Binary('Report File', readonly=True)
    report_filename = fields.Char('Filename', readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')],
                            default='draft')

    def action_generate_report(self):
        """Generate Excel report"""
        self.ensure_one()
        self._check_employee_scope()

        if self.report_type == 'summary':
            report_data = self._generate_summary_report()
        elif self.report_type == 'detailed':
            report_data = self._generate_detailed_report()
        elif self.report_type == 'late_checkin':
            report_data = self._generate_late_checkin_report()
        else:
            report_data = self._generate_anomaly_report()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'attendance.report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _report_employee_ids(self):
        """Return employee IDs allowed for this user's export."""
        if self.env.user.has_group('hr.group_hr_user'):
            return self.employee_ids.ids or None
        own_employees = self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
        ])
        return self.employee_ids.ids or own_employees.ids

    def _check_employee_scope(self):
        if self.env.user.has_group('hr.group_hr_user'):
            return
        own_ids = set(self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
        ]).ids)
        if any(employee.id not in own_ids for employee in self.employee_ids):
            raise AccessError(_('Employees can export only their own attendance.'))

    def _generate_summary_report(self):
        """Generate summary Excel report"""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Attendance Summary')

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4F81BD',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center'
        })

        cell_format = workbook.add_format({'border': 1, 'align': 'center'})
        number_format = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '0.00'})

        # Title
        worksheet.merge_range('A1:K1', 'Monthly Attendance Report', title_format)
        worksheet.write('A2', f'Period: {self.start_date} to {self.end_date}')

        # Headers
        headers = [
            'Employee ID', 'Employee Name', 'Total Days', 'Present', 'Absent',
            'On Leave', 'Late Arrivals', 'Total Worked Hours', 'Expected Hours',
            'Overtime', 'Undertime'
        ]

        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)

        # Get data
        AttendanceSummary = self.env['attendance.summary.analysis']
        employee_ids = self._report_employee_ids()

        summary_data = AttendanceSummary.get_attendance_summary(
            employee_ids, self.start_date, self.end_date
        )

        # Prefetch device IDs for all employees in one query
        emp_id_set = {r['employee_id'] for r in summary_data}
        emp_device_map = {
            emp.id: emp.device_id_num or emp.barcode or 'No ID'
            for emp in self.env['hr.employee'].browse(list(emp_id_set))
        }

        # Aggregate by employee
        employee_stats = {}
        for record in summary_data:
            emp_id = record['employee_id']
            if emp_id not in employee_stats:
                employee_stats[emp_id] = {
                    'name': record['employee_name'],
                    'device_id': emp_device_map.get(emp_id, ''),
                    'total_days': 0,
                    'present': 0,
                    'absent': 0,
                    'leave': 0,
                    'late': 0,
                    'worked_hours': 0,
                    'expected_hours': 0,
                    'overtime': 0,
                    'undertime': 0,
                }

            stats = employee_stats[emp_id]
            # Count only working days (exclude weekends and public holidays)
            if record['status'] not in ('weekend', 'public_holiday'):
                stats['total_days'] += 1

            if record['status'] == 'present':
                stats['present'] += 1
                stats['worked_hours'] += record['worked_hours']
                if record['is_late']:
                    stats['late'] += 1
                stats['overtime'] += record.get('overtime', 0)
                stats['undertime'] += record.get('undertime', 0)
            elif record['status'] == 'absent':
                stats['absent'] += 1
            elif record['status'] == 'leave':
                stats['leave'] += 1

            if record['status'] in ['present', 'absent']:
                stats['expected_hours'] += record['expected_hours']

        # Write data
        row = 4
        for emp_id, stats in employee_stats.items():
            worksheet.write(row, 0, stats['device_id'], cell_format)
            worksheet.write(row, 1, stats['name'], cell_format)
            worksheet.write(row, 2, stats['total_days'], cell_format)
            worksheet.write(row, 3, stats['present'], cell_format)
            worksheet.write(row, 4, stats['absent'], cell_format)
            worksheet.write(row, 5, stats['leave'], cell_format)
            worksheet.write(row, 6, stats['late'], cell_format)
            worksheet.write(row, 7, stats['worked_hours'], number_format)
            worksheet.write(row, 8, stats['expected_hours'], number_format)
            worksheet.write(row, 9, stats['overtime'], number_format)
            worksheet.write(row, 10, stats['undertime'], number_format)
            row += 1

        # Adjust column widths
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:B', 25)
        worksheet.set_column('C:K', 15)

        workbook.close()
        output.seek(0)

        # Save file
        filename = f'Attendance_Summary_{self.start_date}_{self.end_date}.xlsx'
        self.write({
            'report_file': base64.b64encode(output.read()),
            'report_filename': filename,
            'state': 'done'
        })

        return True

    def _generate_detailed_report(self):
        """Generate detailed daily Excel report"""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Daily Attendance')

        # Formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4F81BD',
            'font_color': 'white',
            'border': 1,
            'align': 'center'
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center'
        })

        cell_format = workbook.add_format({'border': 1})
        date_format = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
        time_format = workbook.add_format({'border': 1, 'num_format': 'hh:mm:ss'})
        number_format = workbook.add_format({'border': 1, 'num_format': '0.00'})

        # Status formats
        present_format = workbook.add_format({'border': 1, 'bg_color': '#C6EFCE'})
        absent_format = workbook.add_format({'border': 1, 'bg_color': '#FFC7CE'})
        leave_format = workbook.add_format({'border': 1, 'bg_color': '#FFEB9C'})

        # Title
        worksheet.merge_range('A1:M1', 'Detailed Daily Attendance Report', title_format)
        worksheet.write('A2', f'Period: {self.start_date} to {self.end_date}')

        # Headers
        headers = [
            'Date', 'Employee ID', 'Employee', 'Status', 'Check In', 'Check Out',
            'Worked Hours', 'Expected Hours', 'Late?', 'Late Minutes',
            'Overtime', 'Undertime', 'Remarks'
        ]

        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)

        # Get data
        AttendanceSummary = self.env['attendance.summary.analysis']
        employee_ids = self._report_employee_ids()

        summary_data = AttendanceSummary.get_attendance_summary(
            employee_ids, self.start_date, self.end_date
        )

        # Prefetch device IDs for all employees in one query
        emp_id_set = {r['employee_id'] for r in summary_data}
        emp_device_map = {
            emp.id: emp.device_id_num or emp.barcode or 'No ID'
            for emp in self.env['hr.employee'].browse(list(emp_id_set))
        }

        # Convert UTC datetimes to local timezone for display
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(tz_name)

        def _to_local(dt):
            """Convert naive UTC datetime to local timezone-aware datetime."""
            if not dt:
                return None
            return pytz.utc.localize(dt).astimezone(local_tz).replace(tzinfo=None)

        # Write data
        row = 4
        for record in sorted(summary_data, key=lambda x: (x['date'], x['employee_name'])):
            # Choose format based on status
            if record['status'] == 'present':
                status_format = present_format
            elif record['status'] == 'absent':
                status_format = absent_format
            else:
                status_format = leave_format

            worksheet.write(row, 0, record['date'], date_format)
            worksheet.write(row, 1, emp_device_map.get(record['employee_id'], ''), cell_format)
            worksheet.write(row, 2, record['employee_name'], cell_format)
            worksheet.write(row, 3, record['status'].upper(), status_format)

            local_checkin = _to_local(record['check_in'])
            local_checkout = _to_local(record['check_out'])

            if local_checkin:
                worksheet.write_datetime(row, 4, local_checkin, time_format)
            else:
                worksheet.write(row, 4, '-', cell_format)

            if local_checkout:
                worksheet.write_datetime(row, 5, local_checkout, time_format)
            else:
                worksheet.write(row, 5, '-', cell_format)

            worksheet.write(row, 6, record['worked_hours'], number_format)
            worksheet.write(row, 7, record['expected_hours'], number_format)
            worksheet.write(row, 8, 'YES' if record['is_late'] else 'NO', cell_format)
            worksheet.write(row, 9, record['late_minutes'], number_format)
            worksheet.write(row, 10, record.get('overtime', 0), number_format)
            worksheet.write(row, 11, record.get('undertime', 0), number_format)

            remarks = []
            if record['is_late']:
                remarks.append(f"Late by {record['late_minutes']} min")
            if record.get('overtime', 0) > 0:
                remarks.append(f"OT: {record['overtime']:.2f}h")
            if record.get('undertime', 0) > 0 and record['status'] == 'present':
                remarks.append(f"Early leave: {record['undertime']:.2f}h")
            if record.get('comp_off_eligible'):
                remarks.append(f"Comp-off eligible: {record.get('comp_off_hours', 0):.2f}h")
            worksheet.write(row, 12, '; '.join(remarks), cell_format)

            row += 1

        # Adjust column widths
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:B', 12)
        worksheet.set_column('C:C', 25)
        worksheet.set_column('D:M', 15)

        workbook.close()
        output.seek(0)

        filename = f'Attendance_Detailed_{self.start_date}_{self.end_date}.xlsx'
        self.write({
            'report_file': base64.b64encode(output.read()),
            'report_filename': filename,
            'state': 'done'
        })

        return True

    def _generate_anomaly_report(self):
        """Generate anomaly Excel report"""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Anomalies')

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center'
        })

        date_format = workbook.add_format({
            'num_format': 'yyyy-mm-dd',
            'align': 'center',
            'border': 1
        })

        datetime_format = workbook.add_format({
            'num_format': 'yyyy-mm-dd hh:mm:ss',
            'align': 'center',
            'border': 1
        })

        cell_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True
        })

        center_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })

        # Anomaly type specific formats
        missing_checkout_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006'
        })

        duplicate_checkin_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#FFEB9C',
            'font_color': '#9C6500'
        })

        missing_checkin_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006'
        })

        # Title
        worksheet.merge_range('A1:I1', 'Attendance Anomalies Report', title_format)
        worksheet.write('A2', f'Period: {self.start_date} to {self.end_date}')

        # Write headers
        headers = [
            'Employee', 'Date', 'Anomaly Type', 'Check-in Time',
            'Last Punch Time', 'Total Punches', 'Check-in Count',
            'Check-out Count', 'Working Address'
        ]

        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)

        # Set column widths
        worksheet.set_column(0, 0, 25)  # Employee
        worksheet.set_column(1, 1, 12)  # Date
        worksheet.set_column(2, 2, 20)  # Anomaly Type
        worksheet.set_column(3, 3, 18)  # Check-in Time
        worksheet.set_column(4, 4, 18)  # Last Punch Time
        worksheet.set_column(5, 5, 12)  # Total Punches
        worksheet.set_column(6, 6, 12)  # Check-in Count
        worksheet.set_column(7, 7, 14)  # Check-out Count
        worksheet.set_column(8, 8, 25)  # Working Address

        # Query anomaly data
        domain = [
            ('attendance_date', '>=', self.start_date),
            ('attendance_date', '<=', self.end_date),
        ]

        employee_ids = self._report_employee_ids()
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))

        anomaly_records = self.env['attendance.anomaly.analysis'].search(
            domain, order='attendance_date desc, employee_id'
        )

        # Anomaly type labels
        anomaly_type_labels = {
            'missing_checkout': 'Missing Check-out',
            'duplicate_checkin': 'Duplicate Check-in',
            'missing_checkin': 'Missing Check-in',
        }

        # Write data rows
        row = 4
        for anomaly in anomaly_records:
            # Determine format based on anomaly type
            if anomaly.anomaly_type == 'missing_checkout':
                anomaly_format = missing_checkout_format
            elif anomaly.anomaly_type == 'duplicate_checkin':
                anomaly_format = duplicate_checkin_format
            elif anomaly.anomaly_type == 'missing_checkin':
                anomaly_format = missing_checkin_format
            else:
                anomaly_format = cell_format

            worksheet.write(row, 0, anomaly.employee_id.name or '', cell_format)
            worksheet.write(row, 1, anomaly.attendance_date, date_format)
            worksheet.write(row, 2, anomaly_type_labels.get(anomaly.anomaly_type, anomaly.anomaly_type or ''), anomaly_format)

            if anomaly.check_in_time:
                worksheet.write_datetime(row, 3, anomaly.check_in_time, datetime_format)
            else:
                worksheet.write(row, 3, '', center_format)

            if anomaly.last_punch_time:
                worksheet.write_datetime(row, 4, anomaly.last_punch_time, datetime_format)
            else:
                worksheet.write(row, 4, '', center_format)

            worksheet.write(row, 5, anomaly.total_punches or 0, center_format)
            worksheet.write(row, 6, anomaly.checkin_count or 0, center_format)
            worksheet.write(row, 7, anomaly.checkout_count or 0, center_format)
            worksheet.write(row, 8, anomaly.address_id.name or '', cell_format)

            row += 1

        # Add summary section
        row += 2
        summary_header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'align': 'left',
            'border': 1
        })

        worksheet.write(row, 0, 'Summary', summary_header_format)
        row += 1

        # Count anomalies by type
        missing_checkout_count = len(anomaly_records.filtered(lambda a: a.anomaly_type == 'missing_checkout'))
        duplicate_checkin_count = len(anomaly_records.filtered(lambda a: a.anomaly_type == 'duplicate_checkin'))
        missing_checkin_count = len(anomaly_records.filtered(lambda a: a.anomaly_type == 'missing_checkin'))

        worksheet.write(row, 0, 'Total Anomalies:', cell_format)
        worksheet.write(row, 1, len(anomaly_records), center_format)
        row += 1

        worksheet.write(row, 0, 'Missing Check-out:', missing_checkout_format)
        worksheet.write(row, 1, missing_checkout_count, center_format)
        row += 1

        worksheet.write(row, 0, 'Duplicate Check-in:', duplicate_checkin_format)
        worksheet.write(row, 1, duplicate_checkin_count, center_format)
        row += 1

        worksheet.write(row, 0, 'Missing Check-in:', missing_checkin_format)
        worksheet.write(row, 1, missing_checkin_count, center_format)

        workbook.close()
        output.seek(0)

        filename = f'Attendance_Anomalies_{self.start_date}_{self.end_date}.xlsx'
        self.write({
            'report_file': base64.b64encode(output.read()),
            'report_filename': filename,
            'state': 'done'
        })

        return True

    def _generate_late_checkin_report(self):
        """Generate late check-in Excel report with penalty details"""
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Late Check-in Report')

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#f59e0b',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'font_color': '#f59e0b'
        })

        cell_format = workbook.add_format({'border': 1})
        number_format = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '0'})
        currency_format = workbook.add_format({'border': 1, 'align': 'center', 'num_format': '#,##0" ৳"'})
        date_format = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})

        # Status formats with colors
        draft_format = workbook.add_format({'border': 1, 'bg_color': '#dbeafe', 'align': 'center'})
        approved_format = workbook.add_format({'border': 1, 'bg_color': '#d1fae5', 'align': 'center'})
        refused_format = workbook.add_format({'border': 1, 'bg_color': '#fee2e2', 'align': 'center'})
        deducted_format = workbook.add_format({'border': 1, 'bg_color': '#e5e7eb', 'align': 'center'})

        # Title and period
        worksheet.merge_range('A1:K1', 'Late Check-in Report with Penalties', title_format)
        worksheet.write('A2', f'Period: {self.start_date} to {self.end_date}')
        worksheet.write('A3', f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}')

        # Headers
        headers = [
            'Date', 'Employee ID', 'Employee Name', 'Actual Late (min)',
            'Counted Late (min)', 'Tolerance Applied', 'Penalty Amount (৳)',
            'Status', 'Attendance Ref', 'Approved By', 'Notes'
        ]

        for col, header in enumerate(headers):
            worksheet.write(4, col, header, header_format)

        # Get late check-in data
        LateCheckIn = self.env['late.check.in']
        domain = [
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date)
        ]

        employee_ids = self._report_employee_ids()
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))

        late_records = LateCheckIn.search(domain, order='date desc, employee_id')

        # Write data
        row = 5
        total_penalty = 0
        total_incidents = 0

        for record in late_records:
            # Select status format
            if record.state == 'draft':
                status_format = draft_format
            elif record.state == 'approved':
                status_format = approved_format
            elif record.state == 'refused':
                status_format = refused_format
            else:
                status_format = deducted_format

            tolerance_applied = record.actual_late_minutes - record.late_minutes

            worksheet.write(row, 0, record.date, date_format)
            worksheet.write(row, 1, record.employee_id.device_id_num or record.employee_id.barcode or 'No ID', cell_format)
            worksheet.write(row, 2, record.employee_id.name, cell_format)
            worksheet.write(row, 3, record.actual_late_minutes, number_format)
            worksheet.write(row, 4, record.late_minutes, number_format)
            worksheet.write(row, 5, tolerance_applied, number_format)
            worksheet.write(row, 6, record.penalty_amount, currency_format)
            worksheet.write(row, 7, record.state.upper(), status_format)
            worksheet.write(row, 8, record.name or '-', cell_format)
            worksheet.write(row, 9, '-', cell_format)  # Approved by (can be added if tracking is implemented)
            worksheet.write(row, 10, record.notes or '-', cell_format)

            total_penalty += record.penalty_amount
            total_incidents += 1

            row += 1

        # Add summary section
        row += 2
        summary_header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#f59e0b',
            'font_color': 'white',
            'border': 1
        })
        summary_value_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'right'
        })

        worksheet.write(row, 0, 'SUMMARY', summary_header_format)
        worksheet.merge_range(row, 1, row, 2, '', summary_header_format)
        row += 1

        worksheet.write(row, 0, 'Total Late Incidents:', cell_format)
        worksheet.write(row, 1, total_incidents, summary_value_format)
        row += 1

        worksheet.write(row, 0, 'Total Penalty Amount:', cell_format)
        worksheet.write(row, 1, total_penalty, workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'right',
            'num_format': '#,##0" ৳"'
        }))
        row += 1

        if total_incidents > 0:
            worksheet.write(row, 0, 'Average Penalty per Incident:', cell_format)
            worksheet.write(row, 1, total_penalty / total_incidents, workbook.add_format({
                'border': 1,
                'align': 'right',
                'num_format': '#,##0" ৳"'
            }))

        # Group by Employee Summary
        row += 3
        worksheet.merge_range(row, 0, row, 6, 'EMPLOYEE SUMMARY', summary_header_format)
        row += 1

        employee_summary_headers = [
            'Employee ID', 'Employee Name', 'Total Incidents',
            'Total Late Minutes', 'Total Penalty (৳)', 'Draft', 'Approved/Deducted', 'Refused'
        ]
        for col, header in enumerate(employee_summary_headers):
            worksheet.write(row, col, header, header_format)
        row += 1

        # Aggregate by employee
        employee_stats = {}
        for record in late_records:
            emp_id = record.employee_id.id
            if emp_id not in employee_stats:
                employee_stats[emp_id] = {
                    'device_id': record.employee_id.device_id_num or record.employee_id.barcode or 'No ID',
                    'name': record.employee_id.name,
                    'count': 0,
                    'total_minutes': 0,
                    'total_penalty': 0,
                    'draft': 0,
                    'approved': 0,
                    'refused': 0,
                }
            stats = employee_stats[emp_id]
            stats['count'] += 1
            stats['total_minutes'] += record.late_minutes
            stats['total_penalty'] += record.penalty_amount
            if record.state in ['approved', 'deducted']:
                stats['approved'] += 1
            elif record.state == 'draft':
                stats['draft'] += 1
            elif record.state == 'refused':
                stats['refused'] += 1

        # Write employee summary
        for emp_id, stats in sorted(employee_stats.items(), key=lambda x: x[1]['total_penalty'], reverse=True):
            worksheet.write(row, 0, stats['device_id'], cell_format)
            worksheet.write(row, 1, stats['name'], cell_format)
            worksheet.write(row, 2, stats['count'], number_format)
            worksheet.write(row, 3, stats['total_minutes'], number_format)
            worksheet.write(row, 4, stats['total_penalty'], currency_format)
            worksheet.write(row, 5, stats['draft'], number_format)
            worksheet.write(row, 6, stats['approved'], number_format)
            worksheet.write(row, 7, stats['refused'], number_format)
            row += 1

        # Adjust column widths
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:B', 10)
        worksheet.set_column('C:C', 25)
        worksheet.set_column('D:G', 15)
        worksheet.set_column('H:H', 12)
        worksheet.set_column('I:I', 15)
        worksheet.set_column('J:K', 20)

        workbook.close()
        output.seek(0)

        filename = f'Late_Check_in_Report_{self.start_date}_{self.end_date}.xlsx'
        self.write({
            'report_file': base64.b64encode(output.read()),
            'report_filename': filename,
            'state': 'done'
        })

        return True

    def action_download_report(self):
        """Download the generated report"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/attendance.report.wizard/{self.id}/report_file/{self.report_filename}?download=true',
            'target': 'self',
        }
