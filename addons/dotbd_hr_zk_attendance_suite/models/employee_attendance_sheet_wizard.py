# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit

################################################################################
from odoo import api, models, fields, _
from odoo.orm.registry import Registry as odoo_registry
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
import calendar
import xlsxwriter
import io
import base64


class EmployeeAttendanceSheetWizard(models.TransientModel):
    _name = 'employee.attendance.sheet.wizard'
    _description = 'Employee Attendance Sheet Generator'

    month = fields.Selection([
        ('1', 'January'),
        ('2', 'February'),
        ('3', 'March'),
        ('4', 'April'),
        ('5', 'May'),
        ('6', 'June'),
        ('7', 'July'),
        ('8', 'August'),
        ('9', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
    ], string='Month', required=True, default=lambda self: str(datetime.now().month))

    year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: datetime.now().year
    )

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees',
        help='Leave empty to include all employees'
    )

    report_format = fields.Selection([
        ('excel', 'Excel'),
        ('pdf', 'PDF'),
    ], string='Report Format', required=True, default='excel')

    sheet_type = fields.Selection([
        ('combined', 'Combined Sheet (All Employees)'),
        ('individual', 'Individual Sheets (Per Employee)'),
    ], string='Sheet Type', required=True, default='combined')

    file_data = fields.Binary(string='File', readonly=True)
    file_name = fields.Char(string='File Name', readonly=True)

    @api.constrains('year')
    def _check_year(self):
        """Validate year is reasonable"""
        for record in self:
            if record.year < 2000 or record.year > 2100:
                raise ValidationError(_('Please enter a valid year between 2000 and 2100.'))

    def _export_flag_key(self):
        return f'attendance.export.running.{self.env.uid}'

    def _set_export_flag(self, running):
        """Set or clear the export-in-progress flag using a separate cursor so it
        is immediately visible to concurrent HTTP requests (e.g. the status check)."""
        db = self.env.cr.dbname
        uid = self.env.uid
        key = self._export_flag_key()
        with odoo_registry(db).cursor() as cr:
            env2 = api.Environment(cr, uid, self.env.context)
            env2['ir.config_parameter'].set_param(key, datetime.now().isoformat() if running else '')
            cr.commit()

    def action_generate_report(self):
        """Generate attendance sheet based on selected format"""
        self.ensure_one()
        self._set_export_flag(True)
        try:
            if self.report_format == 'excel':
                return self._generate_excel_report()
            else:
                return self._generate_pdf_report()
        finally:
            self._set_export_flag(False)

    def _generate_excel_report(self):
        """Generate Excel attendance sheet"""
        # Get employees
        employees = self.employee_ids if self.employee_ids else self.env['hr.employee'].search([])

        if not employees:
            raise ValidationError(_('No employees found to generate report.'))

        # Get month details
        month_int = int(self.month)
        year_int = self.year
        month_name = dict(self._fields['month'].selection).get(self.month)

        # Get number of days in month
        num_days = calendar.monthrange(year_int, month_int)[1]

        # Get date range
        start_date = datetime(year_int, month_int, 1).date()
        end_date = datetime(year_int, month_int, num_days).date()

        # Create Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        if self.sheet_type == 'combined':
            self._create_combined_sheet(workbook, employees, start_date, end_date, month_name, year_int, num_days)
        else:
            self._create_individual_sheets(workbook, employees, start_date, end_date, month_name, year_int, num_days)

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())
        output.close()

        # Save file to wizard
        file_name = f'Attendance_Sheet_{month_name}_{year_int}.xlsx'
        self.write({
            'file_data': file_data,
            'file_name': file_name,
        })

        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/employee.attendance.sheet.wizard/{self.id}/file_data/{file_name}?download=true',
            'target': 'self',
        }

    def _create_combined_sheet(self, workbook, employees, start_date, end_date, month_name, year, num_days):
        """Create combined sheet with all employees - Horizontal layout matching template"""
        worksheet = workbook.add_worksheet(f'{month_name} {year}')

        # Load weekend days from system configuration
        ICP = self.env['ir.config_parameter'].sudo()
        _day_codes = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
        weekend_days = set()
        for _num, _code in _day_codes.items():
            if ICP.get_param(f'dotbd_hr_zk_attendance_suite.weekend_{_code}', 'False') in ('True', '1', 'true'):
                weekend_days.add(_num)
        if not weekend_days:
            weekend_days = {4, 5}  # Default: Friday + Saturday (Bangladesh)

        # Define formats
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter',
        })

        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#B4C7E7',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
        })

        weekend_header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
        })

        employee_format = workbook.add_format({
            'bold': True,
            'bg_color': '#E7E6E6',
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
        })

        present_format = workbook.add_format({
            'bg_color': '#C6EFCE',
            'font_color': '#006100',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bold': True,
        })

        absent_format = workbook.add_format({
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bold': True,
        })

        late_format = workbook.add_format({
            'bg_color': '#FFEB9C',
            'font_color': '#9C6500',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bold': True,
        })

        weekend_format = workbook.add_format({
            'bg_color': '#F2F2F2',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
        })

        leave_format = workbook.add_format({
            'bg_color': '#BDD7EE',
            'font_color': '#1F4E78',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bold': True,
        })

        public_holiday_format = workbook.add_format({
            'bg_color': '#FFF2CC',
            'font_color': '#7F6000',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bold': True,
        })

        summary_format = workbook.add_format({
            'bold': True,
            'bg_color': '#FFF2CC',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
        })

        stats_header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
        })

        # Set column widths
        worksheet.set_column(0, 0, 20)  # Employee name column
        worksheet.set_column(1, num_days, 3.5)  # Day columns (narrower)
        worksheet.set_column(num_days + 1, num_days + 13, 12)  # Stats columns

        # Title row
        worksheet.merge_range(0, 0, 0, num_days + 13, f'ATTENDANCE RECORD - {month_name} {year}', title_format)

        # Headers - Day of week row
        row = 1
        worksheet.write(row, 0, 'EMPLOYEE\nNAME', header_format)

        # Write day of week headers (M/T/W/T/F/S/S pattern)
        day_names = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
        for day in range(1, num_days + 1):
            current_date = datetime(year, int(self.month), day).date()
            weekday = current_date.weekday()
            is_weekend = weekday in weekend_days
            col = day

            day_format = weekend_header_format if is_weekend else header_format
            worksheet.write(row, col, day_names[weekday], day_format)

        # Write stats headers
        worksheet.write(row, num_days + 1, 'Total\nPresent', stats_header_format)
        worksheet.write(row, num_days + 2, 'Total\nAbsent', stats_header_format)
        worksheet.write(row, num_days + 3, 'Worked\nLeave Days', stats_header_format)
        worksheet.write(row, num_days + 4, 'Worked\nLeave Hours', stats_header_format)
        worksheet.write(row, num_days + 5, 'Absence\nLeave Days', stats_header_format)
        worksheet.write(row, num_days + 6, 'Absence\nLeave Hours', stats_header_format)
        worksheet.write(row, num_days + 7, 'Total\nLate', stats_header_format)
        worksheet.write(row, num_days + 8, 'Work\nHours', stats_header_format)
        worksheet.write(row, num_days + 9, 'Total Late\nTime (min)', stats_header_format)
        worksheet.write(row, num_days + 10, 'Late\nDays', stats_header_format)
        worksheet.write(row, num_days + 11, 'On Time\nDays', stats_header_format)
        worksheet.write(row, num_days + 12, 'Attendance\nRate %', stats_header_format)
        worksheet.write(row, num_days + 13, 'Ranking', stats_header_format)

        # Day numbers row
        row = 2
        worksheet.write(row, 0, '', header_format)
        for day in range(1, num_days + 1):
            current_date = datetime(year, int(self.month), day).date()
            is_weekend = current_date.weekday() in weekend_days
            col = day

            day_format = weekend_header_format if is_weekend else header_format
            worksheet.write(row, col, day, day_format)

        # Empty cells for stats headers row
        for col in range(num_days + 1, num_days + 14):
            worksheet.write(row, col, '', stats_header_format)

        # Get attendance data for all employees
        attendance_data = self._get_attendance_data(employees, start_date, end_date)

        # Calculate statistics for ranking
        employee_stats = []
        for employee in employees:
            emp_data = attendance_data.get(employee.id, {})

            present_count = 0
            absent_count = 0
            late_count = 0
            total_work_hours = 0
            total_late_minutes = 0
            on_time_count = 0
            leave_count = 0
            leave_types_dict = {}  # Track leave types: {leave_type_id: {name, code, count, hours}}

            daily_status = []

            for day in range(1, num_days + 1):
                current_date = datetime(year, int(self.month), day).date()
                is_weekend = current_date.weekday() in weekend_days
                day_data = emp_data.get(current_date, {})
                status = day_data.get('status', '')

                if status == 'present':
                    total_work_hours += day_data.get('worked_hours', 0)
                    if day_data.get('is_late'):
                        late_count += 1
                        total_late_minutes += day_data.get('late_minutes', 0)
                        daily_status.append('L')
                    else:
                        on_time_count += 1
                        daily_status.append('P')
                    present_count += 1
                elif status == 'leave':
                    # On Leave - show leave code (e.g., SL, PL, CL)
                    leave_count += 1
                    leave_code = day_data.get('leave_code', 'L')
                    leave_type = day_data.get('leave_type', 'Leave')
                    leave_type_id = day_data.get('leave_type_id', 0)
                    leave_category = day_data.get('leave_category', 'absence')  # 'worked' or 'absence'
                    expected_hours = day_data.get('expected_hours', 8)

                    # Track this leave type
                    if leave_type_id not in leave_types_dict:
                        leave_types_dict[leave_type_id] = {
                            'name': leave_type,
                            'code': leave_code,
                            'category': leave_category,
                            'count': 0,
                            'hours': 0
                        }
                    leave_types_dict[leave_type_id]['count'] += 1
                    leave_types_dict[leave_type_id]['hours'] += expected_hours

                    daily_status.append(leave_code)
                elif status == 'public_holiday':
                    # Public Holiday - show 'H' for holiday
                    daily_status.append('H')
                elif status == 'weekend':
                    daily_status.append('-')
                elif status == 'absent':
                    if not is_weekend:
                        absent_count += 1
                        daily_status.append('A')
                    else:
                        daily_status.append('-')
                else:
                    if is_weekend:
                        daily_status.append('-')
                    else:
                        daily_status.append('')

            # Calculate attendance rate: only days employee was expected (not on leave/holiday)
            effective_days = present_count + absent_count
            attendance_rate = (present_count / effective_days * 100) if effective_days > 0 else 100.0

            employee_stats.append({
                'employee': employee,
                'present_count': present_count,
                'absent_count': absent_count,
                'late_count': late_count,
                'total_work_hours': total_work_hours,
                'total_late_minutes': total_late_minutes,
                'on_time_count': on_time_count,
                'leave_count': leave_count,
                'leave_types': leave_types_dict,  # Leave types breakdown
                'attendance_rate': attendance_rate,
                'daily_status': daily_status,
            })

        max_work_hours = max([stat['total_work_hours'] for stat in employee_stats]) if employee_stats else 1
        max_on_time = max([stat['on_time_count'] for stat in employee_stats]) if employee_stats else 1

        for stat in employee_stats:
            # POSITIVE POINTS
            # 1. Attendance Rate Points (40 points max)
            attendance_points = (stat['attendance_rate'] / 100) * 70

            # 2. On-time Days Points (30 points max)
            on_time_points = 0
            if max_on_time > 0:
                on_time_points = (stat['on_time_count'] / max_on_time) * 15

            # 3. Work Hours Points (30 points max)
            work_hours_points = 0
            if max_work_hours > 0:
                work_hours_points = (stat['total_work_hours'] / max_work_hours) * 15

            # NEGATIVE POINTS
            # 4. Absent Days Penalty (-3 points per absent day)
            absent_penalty = stat['absent_count'] * 3

            # 5. Late Days Penalty (-1 point per late day)
            late_penalty = stat['late_count'] * 1

            # 6. Late Minutes Penalty (-0.1 points per minute)
            late_minutes_penalty = stat['total_late_minutes'] * 0.1

            # 7. Absence Leave Penalty (-2 points per absence leave day)
            absence_leave_days = sum(lt['count'] for lt in stat['leave_types'].values() if lt.get('category') == 'absence')
            absence_leave_penalty = absence_leave_days * 2

            # BONUS POINTS FOR WORKED LEAVE
            # 8. Worked Leave Bonus (+1 point per worked leave day - counts as productive time)
            worked_leave_days = sum(lt['count'] for lt in stat['leave_types'].values() if lt.get('category') == 'worked')
            worked_leave_bonus = worked_leave_days * 1

            # Calculate total points
            total_points = (attendance_points + on_time_points + work_hours_points + worked_leave_bonus -
                            absent_penalty - late_penalty - late_minutes_penalty - absence_leave_penalty)

            stat['total_points'] = round(total_points, 2)

        # Sort by total points (highest first)
        sorted_stats = sorted(employee_stats, key=lambda x: x['total_points'], reverse=True)
        for rank, stat in enumerate(sorted_stats, 1):
            stat['rank'] = rank

        # Write employee rows
        row = 3
        for stats in employee_stats:
            emp = stats['employee']
            device_id = emp.device_id_num or emp.barcode or 'No ID'
            emp_display = f"[{device_id}] {emp.name}" if device_id else emp.name
            worksheet.write(row, 0, emp_display, employee_format)

            # Write daily attendance
            for day in range(1, num_days + 1):
                current_date = datetime(year, int(self.month), day).date()
                is_weekend = current_date.weekday() in weekend_days
                col = day
                status = stats['daily_status'][day - 1]

                if status == 'P':
                    worksheet.write(row, col, 'P', present_format)
                elif status == 'A':
                    worksheet.write(row, col, 'A', absent_format)
                elif status == 'L':
                    worksheet.write(row, col, 'L', late_format)
                elif status == 'H':
                    worksheet.write(row, col, 'H', public_holiday_format)
                elif status == '-':
                    worksheet.write(row, col, '-', weekend_format)
                elif status and status not in ['P', 'A', 'L', 'H', '-', '']:
                    # Leave codes (SL, PL, CL, etc.)
                    worksheet.write(row, col, status, leave_format)
                else:
                    worksheet.write(row, col, '', weekend_format if is_weekend else None)

            # Write statistics
            worksheet.write(row, num_days + 1, stats['present_count'], summary_format)
            worksheet.write(row, num_days + 2, stats['absent_count'], summary_format)

            # Calculate worked and absence leave days/hours separately
            worked_leave_days = sum(lt['count'] for lt in stats['leave_types'].values() if lt.get('category') == 'worked')
            worked_leave_hours = sum(lt['hours'] for lt in stats['leave_types'].values() if lt.get('category') == 'worked')
            absence_leave_days = sum(lt['count'] for lt in stats['leave_types'].values() if lt.get('category') == 'absence')
            absence_leave_hours = sum(lt['hours'] for lt in stats['leave_types'].values() if lt.get('category') == 'absence')

            worksheet.write(row, num_days + 3, worked_leave_days, summary_format)
            worksheet.write(row, num_days + 4, f"{worked_leave_hours:.1f}h", summary_format)
            worksheet.write(row, num_days + 5, absence_leave_days, summary_format)
            worksheet.write(row, num_days + 6, f"{absence_leave_hours:.1f}h", summary_format)
            worksheet.write(row, num_days + 7, stats['late_count'], summary_format)
            worksheet.write(row, num_days + 8, f"{stats['total_work_hours']:.1f}h", summary_format)
            worksheet.write(row, num_days + 9, stats['total_late_minutes'], summary_format)
            worksheet.write(row, num_days + 10, stats['late_count'], summary_format)
            worksheet.write(row, num_days + 11, stats['on_time_count'], summary_format)
            worksheet.write(row, num_days + 12, f"{stats['attendance_rate']:.1f}%", summary_format)

            # Ranking with color coding
            rank_format = workbook.add_format({
                'bold': True,
                'bg_color': '#C6EFCE' if stats['rank'] <= 3 else '#FFC7CE' if stats['rank'] > len(employees) - 3 else '#FFEB9C',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
            })
            worksheet.write(row, num_days + 13, stats['rank'], rank_format)

            row += 1

        # Add legend
        # ============================================
        # RANKING CALCULATION TABLE
        # ============================================
        row += 3

        # Title
        ranking_title_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'center',
            'bg_color': '#4472C4', 'font_color': 'white', 'border': 1
        })
        worksheet.merge_range(row, 0, row, 9, 'EMPLOYEE RANKING CALCULATION BREAKDOWN', ranking_title_format)
        row += 1

        # Headers
        ranking_header_format = workbook.add_format({
            'bold': True, 'bg_color': '#B4C7E7', 'align': 'center',
            'valign': 'vcenter', 'border': 1, 'text_wrap': True
        })

        headers = ['Employee Name', 'Present\nPoints', 'Late\nPoints', 'Absent\nPoints',
                   'Leave\nPoints', 'Overtime\nPoints', 'Undertime\nPoints',
                   'Other\nPoints', 'Total\nPoints', 'Rank']

        for col, header in enumerate(headers):
            worksheet.write(row, col, header, ranking_header_format)

        worksheet.set_column(0, 0, 25)
        worksheet.set_column(1, 9, 12)
        row += 1

        # Build detailed stats by reusing the already-computed employee_stats
        # (avoids a second different formula that would produce inconsistent rankings)
        stats_by_rank = sorted(employee_stats, key=lambda x: x['total_points'], reverse=True)
        detailed_stats = []
        for rank, stat in enumerate(stats_by_rank, 1):
            lt = stat['leave_types']
            absence_leave_days = sum(v['count'] for v in lt.values() if v.get('category') == 'absence')
            worked_leave_days = sum(v['count'] for v in lt.values() if v.get('category') == 'worked')

            # Mirror the same formula used in the main ranking
            attendance_points = (stat['attendance_rate'] / 100) * 70
            on_time_points = (stat['on_time_count'] / max_on_time) * 15 if max_on_time > 0 else 0
            work_hours_points = (stat['total_work_hours'] / max_work_hours) * 15 if max_work_hours > 0 else 0
            absent_penalty = stat['absent_count'] * 3
            late_penalty = stat['late_count'] * 1
            late_minutes_penalty = stat['total_late_minutes'] * 0.1
            absence_leave_penalty = absence_leave_days * 2
            worked_leave_bonus = worked_leave_days * 1

            detailed_stats.append({
                'employee': stat['employee'],
                'present_points': round(attendance_points + on_time_points + work_hours_points, 2),
                'late_points': round(-late_penalty - late_minutes_penalty, 2),
                'absent_points': round(-absent_penalty, 2),
                'leave_points': round(worked_leave_bonus - absence_leave_penalty, 2),
                'overtime_points': 0,
                'undertime_points': 0,
                'other_points': 0,
                'total_points': stat['total_points'],
                'rank': rank,
            })

        # Formats
        positive_format = workbook.add_format({
            'border': 1, 'align': 'center', 'bg_color': '#C6EFCE',
            'font_color': '#006100', 'num_format': '0.00'
        })
        negative_format = workbook.add_format({
            'border': 1, 'align': 'center', 'bg_color': '#FFC7CE',
            'font_color': '#9C0006', 'num_format': '0.00'
        })
        neutral_format = workbook.add_format({
            'border': 1, 'align': 'center', 'num_format': '0.00'
        })
        employee_name_format = workbook.add_format({
            'border': 1, 'align': 'left', 'bold': True
        })
        total_format = workbook.add_format({
            'border': 1, 'align': 'center', 'bold': True,
            'bg_color': '#FFF2CC', 'num_format': '0.00'
        })

        # Write data
        for stat in detailed_stats:
            worksheet.write(row, 0, stat['employee'].name, employee_name_format)
            worksheet.write(row, 1, stat['present_points'],
                            positive_format if stat['present_points'] > 0 else neutral_format)
            worksheet.write(row, 2, stat['late_points'],
                            negative_format if stat['late_points'] < 0 else neutral_format)
            worksheet.write(row, 3, stat['absent_points'],
                            negative_format if stat['absent_points'] < 0 else neutral_format)
            worksheet.write(row, 4, stat['leave_points'],
                            negative_format if stat['leave_points'] < 0 else neutral_format)
            worksheet.write(row, 5, stat['overtime_points'],
                            positive_format if stat['overtime_points'] > 0 else neutral_format)
            worksheet.write(row, 6, stat['undertime_points'],
                            negative_format if stat['undertime_points'] < 0 else neutral_format)
            worksheet.write(row, 7, stat['other_points'],
                            negative_format if stat['other_points'] < 0 else neutral_format)
            worksheet.write(row, 8, stat['total_points'], total_format)

            rank_color = workbook.add_format({
                'border': 1, 'align': 'center', 'bold': True,
                'bg_color': '#C6EFCE' if stat['rank'] <= 3 else
                '#FFC7CE' if stat['rank'] > len(employees) - 3 else '#FFEB9C'
            })
            worksheet.write(row, 9, stat['rank'], rank_color)
            row += 1

        # ============================================
        # POINTS LEGEND
        # ============================================
        row += 2
        point_legend_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'bg_color': '#D9E1F2', 'border': 1
        })
        worksheet.merge_range(row, 0, row, 9, 'POINTS CALCULATION LEGEND', point_legend_format)
        row += 1

        legend_label = workbook.add_format({'bold': True, 'border': 1})
        legend_desc = workbook.add_format({'border': 1})

        legends = [
            ('Present Points:', '+1.0 point per on-time day (P status)', positive_format),
            ('Late Points:', '-1.0 point per late arrival (L status)', negative_format),
            ('Absent Points:', '-3.0 points per absent day (A status)', negative_format),
            ('Leave Points:', '-2.0 points per leave day (V status)', negative_format),
            ('Overtime Points:', '+0.25 points per extra hour worked', positive_format),
            ('Undertime Points:', '-0.25 points per hour short', negative_format),
            ('Other Points:', '-0.1 points per late minute', negative_format),
        ]

        for label, desc, fmt in legends:
            worksheet.write(row, 0, label, legend_label)
            worksheet.merge_range(row, 1, row, 8, desc, legend_desc)
            worksheet.write(row, 9, 'Sample', fmt)
            row += 1

        # ============================================
        # STATUS LEGEND (Original)
        # ============================================
        row += 2
        legend_label_format = workbook.add_format({'bold': True})
        worksheet.write(row, 0, 'STATUS LEGEND:', legend_label_format)
        row += 1
        worksheet.write(row, 0, 'P = Present (On Time)', present_format)
        row += 1
        worksheet.write(row, 0, 'A = Absent', absent_format)
        row += 1
        worksheet.write(row, 0, 'L = Late Check-in', late_format)
        row += 1
        worksheet.write(row, 0, 'H = Public Holiday', public_holiday_format)
        row += 1
        worksheet.write(row, 0, '- = Weekend/Holiday', weekend_format)

        # ============================================
        # LEAVE TYPES SUMMARY
        # ============================================
        # Collect all unique leave types from all employees
        all_leave_types = {}
        for stat in employee_stats:
            for leave_type_id, leave_data in stat.get('leave_types', {}).items():
                if leave_type_id not in all_leave_types:
                    all_leave_types[leave_type_id] = {
                        'name': leave_data['name'],
                        'code': leave_data['code'],
                        'total_days': 0,
                        'total_hours': 0
                    }
                all_leave_types[leave_type_id]['total_days'] += leave_data['count']
                all_leave_types[leave_type_id]['total_hours'] += leave_data['hours']

        if all_leave_types:
            row += 2
            worksheet.write(row, 0, 'LEAVE TYPES SUMMARY:', legend_label_format)
            row += 1

            # Table header
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            data_format = workbook.add_format({
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            worksheet.write(row, 0, 'Code', header_format)
            worksheet.write(row, 1, 'Leave Type', header_format)
            worksheet.write(row, 2, 'Total Days', header_format)
            worksheet.write(row, 3, 'Total Hours', header_format)
            row += 1

            # Sort by leave code for consistent display
            sorted_leaves = sorted(all_leave_types.values(), key=lambda x: x['code'])

            for leave_info in sorted_leaves:
                worksheet.write(row, 0, leave_info['code'], leave_format)
                worksheet.write(row, 1, leave_info['name'], data_format)
                worksheet.write(row, 2, leave_info['total_days'], data_format)
                worksheet.write(row, 3, f"{leave_info['total_hours']:.1f}h", data_format)
                row += 1

            # Add explanation
            row += 1
            explanation_format = workbook.add_format({
                'italic': True,
                'font_size': 9,
                'text_wrap': True
            })
            worksheet.merge_range(row, 0, row, 3,
                'Note: Leave codes appear in the attendance grid. Each leave type has a unique code for easy identification.',
                explanation_format)

    def _create_individual_sheets(self, workbook, employees, start_date, end_date, month_name, year, num_days):
        """Create individual sheets for each employee - Horizontal layout matching template"""
        # Get attendance data for all employees at once
        attendance_data = self._get_attendance_data(employees, start_date, end_date)

        # Load weekend days from system configuration
        ICP = self.env['ir.config_parameter'].sudo()
        _day_codes = {0: 'mon', 1: 'tue', 2: 'wed', 3: 'thu', 4: 'fri', 5: 'sat', 6: 'sun'}
        weekend_days = set()
        for _num, _code in _day_codes.items():
            if ICP.get_param(f'dotbd_hr_zk_attendance_suite.weekend_{_code}', 'False') in ('True', '1', 'true'):
                weekend_days.add(_num)
        if not weekend_days:
            weekend_days = {4, 5}  # Default: Friday + Saturday (Bangladesh)

        for employee in employees:
            # Create sheet for each employee
            # Sanitize sheet name (Excel has 31 char limit and special char restrictions)
            sheet_name = employee.name[:31].replace('/', '-').replace('\\', '-').replace('[', '(').replace(']', ')')
            worksheet = workbook.add_worksheet(sheet_name)

            # Define formats
            title_format = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'align': 'center',
                'valign': 'vcenter',
            })

            info_format = workbook.add_format({
                'bold': True,
                'align': 'left',
                'valign': 'vcenter',
                'font_size': 11,
            })

            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#B4C7E7',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'font_size': 9,
            })

            weekend_header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'font_size': 9,
            })

            present_format = workbook.add_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'bold': True,
            })

            absent_format = workbook.add_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'bold': True,
            })

            late_format = workbook.add_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C6500',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'bold': True,
            })

            weekend_format = workbook.add_format({
                'bg_color': '#F2F2F2',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
            })

            leave_format = workbook.add_format({
                'bg_color': '#BDD7EE',
                'font_color': '#1F4E78',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'bold': True,
            })

            public_holiday_format = workbook.add_format({
                'bg_color': '#FFF2CC',
                'font_color': '#7F6000',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'bold': True,
            })

            summary_format = workbook.add_format({
                'bold': True,
                'bg_color': '#FFF2CC',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
            })

            stats_header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4472C4',
                'font_color': 'white',
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
            })

            # Set column widths
            worksheet.set_column(0, 0, 20)  # Label column
            worksheet.set_column(1, num_days, 3.5)  # Day columns (narrower)
            worksheet.set_column(num_days + 1, num_days + 12, 12)  # Stats columns

            # Title row
            row = 0
            worksheet.merge_range(row, 0, row, num_days + 12,
                                 f'ATTENDANCE RECORD - {month_name} {year}', title_format)

            # Employee info section
            row += 2
            worksheet.write(row, 0, 'Employee:', info_format)
            worksheet.merge_range(row, 1, row, 5, employee.name)
            row += 1

            device_id = employee.device_id_num or employee.barcode or 'No ID'
            if device_id:
                worksheet.write(row, 0, 'Device ID:', info_format)
                worksheet.merge_range(row, 1, row, 5, device_id)
                row += 1

            if employee.department_id:
                worksheet.write(row, 0, 'Department:', info_format)
                worksheet.merge_range(row, 1, row, 5, employee.department_id.name)
                row += 1

            if employee.job_id:
                worksheet.write(row, 0, 'Job Position:', info_format)
                worksheet.merge_range(row, 1, row, 5, employee.job_id.name)
                row += 1

            row += 1

            # Headers - Day of week row
            worksheet.write(row, 0, 'Status', header_format)

            # Write day of week headers (M/T/W/T/F/S/S pattern)
            day_names = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
            for day in range(1, num_days + 1):
                current_date = datetime(year, int(self.month), day).date()
                weekday = current_date.weekday()
                is_weekend = weekday in weekend_days
                col = day

                day_format = weekend_header_format if is_weekend else header_format
                worksheet.write(row, col, day_names[weekday], day_format)

            # Write stats headers
            worksheet.write(row, num_days + 1, 'Total\nPresent', stats_header_format)
            worksheet.write(row, num_days + 2, 'Total\nAbsent', stats_header_format)
            worksheet.write(row, num_days + 3, 'Worked\nLeave Days', stats_header_format)
            worksheet.write(row, num_days + 4, 'Worked\nLeave Hours', stats_header_format)
            worksheet.write(row, num_days + 5, 'Absence\nLeave Days', stats_header_format)
            worksheet.write(row, num_days + 6, 'Absence\nLeave Hours', stats_header_format)
            worksheet.write(row, num_days + 7, 'Total\nLate', stats_header_format)
            worksheet.write(row, num_days + 8, 'Work\nHours', stats_header_format)
            worksheet.write(row, num_days + 9, 'Total Late\nTime (min)', stats_header_format)
            worksheet.write(row, num_days + 10, 'Late\nDays', stats_header_format)
            worksheet.write(row, num_days + 11, 'On Time\nDays', stats_header_format)
            worksheet.write(row, num_days + 12, 'Attendance\nRate %', stats_header_format)

            # Day numbers row
            row += 1
            worksheet.write(row, 0, '', header_format)
            for day in range(1, num_days + 1):
                current_date = datetime(year, int(self.month), day).date()
                is_weekend = current_date.weekday() in weekend_days
                col = day

                day_format = weekend_header_format if is_weekend else header_format
                worksheet.write(row, col, day, day_format)

            # Empty cells for stats headers row
            for col in range(num_days + 1, num_days + 13):
                worksheet.write(row, col, '', stats_header_format)

            # Get employee attendance data
            emp_data = attendance_data.get(employee.id, {})

            # Calculate statistics
            present_count = 0
            absent_count = 0
            late_count = 0
            total_work_hours = 0
            total_late_minutes = 0
            on_time_count = 0
            leave_count = 0
            leave_types_dict = {}  # Track leave types for this employee
            daily_status = []

            for day in range(1, num_days + 1):
                current_date = datetime(year, int(self.month), day).date()
                is_weekend = current_date.weekday() in weekend_days
                day_data = emp_data.get(current_date, {})
                status = day_data.get('status', '')

                if status == 'present':
                    total_work_hours += day_data.get('worked_hours', 0)
                    if day_data.get('is_late'):
                        late_count += 1
                        total_late_minutes += day_data.get('late_minutes', 0)
                        daily_status.append('L')
                    else:
                        on_time_count += 1
                        daily_status.append('P')
                    present_count += 1
                elif status == 'leave':
                    leave_count += 1
                    # On Leave - show leave code (e.g., SL, PL, CL)
                    leave_code = day_data.get('leave_code', 'L')
                    leave_type = day_data.get('leave_type', 'Leave')
                    leave_type_id = day_data.get('leave_type_id', 0)
                    leave_category = day_data.get('leave_category', 'absence')  # 'worked' or 'absence'
                    expected_hours = day_data.get('expected_hours', 8)

                    # Track this leave type
                    if leave_type_id not in leave_types_dict:
                        leave_types_dict[leave_type_id] = {
                            'name': leave_type,
                            'code': leave_code,
                            'category': leave_category,
                            'count': 0,
                            'hours': 0
                        }
                    leave_types_dict[leave_type_id]['count'] += 1
                    leave_types_dict[leave_type_id]['hours'] += expected_hours

                    daily_status.append(leave_code)
                elif status == 'public_holiday':
                    # Public Holiday - show 'H' for holiday
                    daily_status.append('H')
                elif status == 'weekend':
                    daily_status.append('-')
                elif status == 'absent':
                    if not is_weekend:
                        absent_count += 1
                        daily_status.append('A')
                    else:
                        daily_status.append('-')
                else:
                    if is_weekend:
                        daily_status.append('-')
                    else:
                        daily_status.append('')

            # Calculate attendance rate: only days employee was expected (not on leave/holiday)
            effective_days = present_count + absent_count
            attendance_rate = (present_count / effective_days * 100) if effective_days > 0 else 100.0

            # Write attendance row
            row += 1
            worksheet.write(row, 0, '', header_format)

            # Write daily attendance
            for day in range(1, num_days + 1):
                current_date = datetime(year, int(self.month), day).date()
                is_weekend = current_date.weekday() in weekend_days
                col = day
                status = daily_status[day - 1]

                if status == 'P':
                    worksheet.write(row, col, 'P', present_format)
                elif status == 'A':
                    worksheet.write(row, col, 'A', absent_format)
                elif status == 'L':
                    worksheet.write(row, col, 'L', late_format)
                elif status == 'H':
                    worksheet.write(row, col, 'H', public_holiday_format)
                elif status == '-':
                    worksheet.write(row, col, '-', weekend_format)
                elif status and status not in ['P', 'A', 'L', 'H', '-', '']:
                    # Leave codes (SL, PL, CL, etc.)
                    worksheet.write(row, col, status, leave_format)
                else:
                    worksheet.write(row, col, '', weekend_format if is_weekend else None)

            # Calculate worked and absence leave days/hours separately
            worked_leave_days = sum(lt['count'] for lt in leave_types_dict.values() if lt.get('category') == 'worked')
            worked_leave_hours = sum(lt['hours'] for lt in leave_types_dict.values() if lt.get('category') == 'worked')
            absence_leave_days = sum(lt['count'] for lt in leave_types_dict.values() if lt.get('category') == 'absence')
            absence_leave_hours = sum(lt['hours'] for lt in leave_types_dict.values() if lt.get('category') == 'absence')

            # Write statistics
            worksheet.write(row, num_days + 1, present_count, summary_format)
            worksheet.write(row, num_days + 2, absent_count, summary_format)
            worksheet.write(row, num_days + 3, worked_leave_days, summary_format)
            worksheet.write(row, num_days + 4, f"{worked_leave_hours:.1f}h", summary_format)
            worksheet.write(row, num_days + 5, absence_leave_days, summary_format)
            worksheet.write(row, num_days + 6, f"{absence_leave_hours:.1f}h", summary_format)
            worksheet.write(row, num_days + 7, late_count, summary_format)
            worksheet.write(row, num_days + 8, f"{total_work_hours:.1f}h", summary_format)
            worksheet.write(row, num_days + 9, total_late_minutes, summary_format)
            worksheet.write(row, num_days + 10, late_count, summary_format)
            worksheet.write(row, num_days + 11, on_time_count, summary_format)
            worksheet.write(row, num_days + 12, f"{attendance_rate:.1f}%", summary_format)

            # Add legend
            row += 3
            legend_label_format = workbook.add_format({'bold': True})
            worksheet.write(row, 0, 'Legend:', legend_label_format)
            row += 1
            worksheet.write(row, 0, 'P = Present (On Time)', present_format)
            row += 1
            worksheet.write(row, 0, 'A = Absent', absent_format)
            row += 1
            worksheet.write(row, 0, 'L = Late Check-in', late_format)
            row += 1
            worksheet.write(row, 0, 'H = Public Holiday', public_holiday_format)
            row += 1
            worksheet.write(row, 0, '- = Weekend/Holiday', weekend_format)

            # Add leave types summary for this employee if they have leaves
            if leave_types_dict:
                row += 2
                worksheet.write(row, 0, 'Leave Types Summary:', legend_label_format)
                row += 1

                # Table header
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#D9E1F2',
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter'
                })
                data_format = workbook.add_format({
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter'
                })

                worksheet.write(row, 0, 'Code', header_format)
                worksheet.write(row, 1, 'Leave Type', header_format)
                worksheet.write(row, 2, 'Days', header_format)
                worksheet.write(row, 3, 'Hours', header_format)
                row += 1

                # Sort by leave code for consistent display
                sorted_leaves = sorted(leave_types_dict.values(), key=lambda x: x['code'])

                for leave_info in sorted_leaves:
                    worksheet.write(row, 0, leave_info['code'], leave_format)
                    worksheet.write(row, 1, leave_info['name'], data_format)
                    worksheet.write(row, 2, leave_info['count'], data_format)
                    worksheet.write(row, 3, f"{leave_info['hours']:.1f}h", data_format)
                    row += 1

    def _get_attendance_data(self, employees, start_date, end_date):
        """Get attendance data for employees in date range with Time Off integration"""
        # Get attendance summary data
        AttendanceSummary = self.env['attendance.summary.analysis']

        summary_data = AttendanceSummary.get_attendance_summary(
            employee_ids=employees.ids,
            start_date=start_date,
            end_date=end_date
        )

        # Organize data by employee and date
        attendance_dict = {}
        for record in summary_data:
            emp_id = record['employee_id']
            date = record['date']

            if emp_id not in attendance_dict:
                attendance_dict[emp_id] = {}

            attendance_dict[emp_id][date] = {
                'status': record['status'],
                'is_late': record.get('is_late', False),
                'worked_hours': record.get('worked_hours', 0),
                'expected_hours': record.get('expected_hours', 8),
                'late_minutes': record.get('late_minutes', 0),
                'leave_type': record.get('leave_type', ''),
                'leave_code': record.get('leave_code', 'L'),  # Short code for display
                'leave_type_id': record.get('leave_type_id', False),  # For grouping
                'leave_category': record.get('leave_category', 'absence'),  # 'absence' or 'worked'
                'holiday_name': record.get('holiday_name', ''),
            }

        return attendance_dict

    def get_pdf_report_data(self):
        """Prepare all data needed for PDF report (QWeb template compatible)"""
        self.ensure_one()

        # Get month details
        month_int = int(self.month)
        year_int = self.year
        month_name = dict(self._fields['month'].selection).get(self.month)

        # Get number of days in month
        num_days = calendar.monthrange(year_int, month_int)[1]

        # Get date range
        start_date = datetime(year_int, month_int, 1).date()
        end_date = datetime(year_int, month_int, num_days).date()

        # Get employees
        employees = self.employee_ids if self.employee_ids else self.env['hr.employee'].search([])

        # Get attendance data
        attendance_data = self._get_attendance_data(employees, start_date, end_date)

        # Prepare day information list
        days_info = []
        for day in range(1, num_days + 1):
            current_date = datetime(year_int, month_int, day).date()
            days_info.append({
                'day': day,
                'date': current_date,
                'is_weekend': current_date.weekday() in weekend_days,
                'weekday': current_date.weekday(),
            })

        # Prepare employee data with attendance
        employees_data = []
        for employee in employees:
            emp_data = attendance_data.get(employee.id, {})

            # Build daily attendance list
            daily_attendance = []
            present_count = 0
            absent_count = 0
            late_count = 0
            total_work_hours = 0
            total_late_minutes = 0
            on_time_count = 0
            leave_count = 0
            leave_types_dict = {}  # Track leave types for PDF

            for day_info in days_info:
                current_date = day_info['date']
                is_weekend = day_info['is_weekend']
                day_data = emp_data.get(current_date, {})
                status = day_data.get('status', '')

                # Determine display status
                if status == 'present':
                    total_work_hours += day_data.get('worked_hours', 0)
                    present_count += 1
                    if day_data.get('is_late'):
                        display_status = 'L'
                        css_class = 'late'
                        late_count += 1
                        total_late_minutes += day_data.get('late_minutes', 0)
                    else:
                        display_status = 'P'
                        css_class = 'present'
                        on_time_count += 1
                elif status == 'leave':
                    # Use leave code instead of 'V'
                    leave_code = day_data.get('leave_code', 'L')
                    leave_type = day_data.get('leave_type', 'Leave')
                    leave_type_id = day_data.get('leave_type_id', 0)
                    leave_category = day_data.get('leave_category', 'absence')
                    expected_hours = day_data.get('expected_hours', 8)

                    # Track this leave type
                    if leave_type_id not in leave_types_dict:
                        leave_types_dict[leave_type_id] = {
                            'name': leave_type,
                            'code': leave_code,
                            'category': leave_category,
                            'count': 0,
                            'hours': 0
                        }
                    leave_types_dict[leave_type_id]['count'] += 1
                    leave_types_dict[leave_type_id]['hours'] += expected_hours

                    display_status = leave_code
                    css_class = 'leave'
                    leave_count += 1
                elif status == 'public_holiday':
                    display_status = 'H'
                    css_class = 'public_holiday'
                elif status == 'weekend':
                    display_status = '-'
                    css_class = 'weekend'
                elif status == 'absent':
                    if not is_weekend:
                        display_status = 'A'
                        css_class = 'absent'
                        absent_count += 1
                    else:
                        display_status = '-'
                        css_class = 'weekend'
                else:
                    if is_weekend:
                        display_status = '-'
                        css_class = 'weekend'
                    else:
                        display_status = ''
                        css_class = ''

                daily_attendance.append({
                    'day': day_info['day'],
                    'date': current_date,
                    'date_str': current_date.strftime('%d/%m/%Y'),
                    'status': display_status,
                    'css_class': css_class,
                    'is_weekend': is_weekend,
                })

            # Calculate attendance rate: only days employee was expected (not on leave/holiday)
            effective_days = present_count + absent_count
            attendance_rate = (present_count / effective_days * 100) if effective_days > 0 else 100.0

            employees_data.append({
                'id': employee.id,
                'name': employee.name,
                'device_id_num': employee.device_id_num or employee.barcode or 'No ID',
                'department': employee.department_id.name if employee.department_id else '',
                'job_position': employee.job_id.name if employee.job_id else '',
                'daily_attendance': daily_attendance,
                'present_count': present_count,
                'absent_count': absent_count,
                'late_count': late_count,
                'total_work_hours': total_work_hours,
                'total_late_minutes': total_late_minutes,
                'on_time_count': on_time_count,
                'leave_count': leave_count,
                'leave_types': leave_types_dict,  # Leave types breakdown for PDF
                'attendance_rate': attendance_rate,
            })

        # Sort by attendance rate for ranking
        max_work_hours = max([emp['total_work_hours'] for emp in employees_data]) if employees_data else 1
        max_on_time = max([emp['on_time_count'] for emp in employees_data]) if employees_data else 1

        for emp_data in employees_data:
            # POSITIVE POINTS
            attendance_points = (emp_data['attendance_rate'] / 100) * 70
            on_time_points = (emp_data['on_time_count'] / max_on_time) * 15 if max_on_time > 0 else 0
            work_hours_points = (emp_data['total_work_hours'] / max_work_hours) * 15 if max_work_hours > 0 else 0

            # NEGATIVE POINTS
            absent_penalty = emp_data['absent_count'] * 3
            late_penalty = emp_data['late_count'] * 1
            late_minutes_penalty = emp_data['total_late_minutes'] * 0.1
            # Distinguish absence leave (-2/day) vs worked leave (+1 bonus/day)
            absence_leave_days = sum(lt['count'] for lt in emp_data.get('leave_types', {}).values() if lt.get('category') == 'absence')
            worked_leave_days = sum(lt['count'] for lt in emp_data.get('leave_types', {}).values() if lt.get('category') == 'worked')
            absence_leave_penalty = absence_leave_days * 2
            worked_leave_bonus = worked_leave_days * 1

            # Calculate total points
            total_points = (attendance_points + on_time_points + work_hours_points + worked_leave_bonus -
                            absent_penalty - late_penalty - late_minutes_penalty - absence_leave_penalty)

            emp_data['total_points'] = round(total_points, 2)

        # Sort by total points (highest first)
        sorted_employees = sorted(employees_data, key=lambda x: x['total_points'], reverse=True)
        for rank, emp_data in enumerate(sorted_employees, 1):
            emp_data['rank'] = rank

        # Collect all unique leave types from all employees for summary
        all_leave_types = {}
        for emp in employees_data:
            for leave_type_id, leave_data in emp.get('leave_types', {}).items():
                if leave_type_id not in all_leave_types:
                    all_leave_types[leave_type_id] = {
                        'name': leave_data['name'],
                        'code': leave_data['code'],
                        'total_days': 0,
                        'total_hours': 0
                    }
                all_leave_types[leave_type_id]['total_days'] += leave_data['count']
                all_leave_types[leave_type_id]['total_hours'] += leave_data['hours']

        # Sort leave types by code for consistent display
        leave_types_summary = sorted(all_leave_types.values(), key=lambda x: x['code'])

        return {
            'month_int': month_int,
            'year_int': year_int,
            'month_name': month_name,
            'num_days': num_days,
            'days_info': days_info,
            'employees_data': employees_data,
            'leave_types_summary': leave_types_summary,  # Overall leave types summary
            'sheet_type': self.sheet_type,
            'total_employees': len(employees),
        }

    def _generate_pdf_report(self):
        """Generate PDF attendance sheet"""
        # This will call the QWeb PDF report
        return self.env.ref('dotbd_hr_zk_attendance_suite.action_report_employee_attendance_sheet').report_action(self)
