# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit

################################################################################
from odoo import fields, models, tools
from .zk_machine_attendance import ATTENDANCE_TYPE_SELECTION, PUNCH_TYPE_SELECTION


class DailyAttendance(models.Model):
    """Model to hold data from the biometric device"""
    _name = 'daily.attendance'
    _description = 'Daily Attendance Report'
    _auto = False
    _order = 'punching_day desc'

    employee_id = fields.Many2one('hr.employee', string='Employee',
                                  help='Employee Name')
    punching_day = fields.Date(string='Date', help='Date of punching')
    address_id = fields.Many2one('res.partner', string='Working Address',
                                 help='Working address of the employee')
    attendance_type = fields.Selection(ATTENDANCE_TYPE_SELECTION,
                                       string='Category',
                                       help='Attendance detecting methods')
    punch_type = fields.Selection(PUNCH_TYPE_SELECTION,
                                  string='Device Punch Type',
                                  help='The Punch Type reported by the device')
    odoo_punch_type = fields.Selection([
        ('check_in', 'Check In'),
        ('check_out', 'Check Out'),
    ], string='Attendance Action',
       help='How Odoo processed this punch: Check In or Check Out. '
            'In Auto mode this may differ from the device punch type.')
    punching_time = fields.Datetime(string='Punching Time',
                                    help='Punching time in the device')
    device_id = fields.Many2one('biometric.device.details', string='Source Device',
                                 help='Device that recorded this punch')
    is_complete_cycle = fields.Boolean("Complete Cycle",
                                       help='True if the hr.attendance record associated with this punch has both a check-in and check-out time.')

    def init(self):
        """Retrieve the data's for attendance report"""
        tools.drop_view_if_exists(self.env.cr, 'daily_attendance')
        query = """
                create or replace view daily_attendance as (
                    select
                        min(z.id) as id,
                        z.employee_id as employee_id,
                        DATE(z.punching_time) as punching_day,
                        z.address_id as address_id,
                        z.attendance_type as attendance_type,
                        z.punching_time as punching_time,
                        z.punch_type as punch_type,
                        z.odoo_punch_type as odoo_punch_type,
                        z.device_id as device_id,
                        CASE WHEN h.check_out IS NOT NULL THEN TRUE ELSE FALSE END as is_complete_cycle
                    from zk_machine_attendance z
                        join hr_employee e on (z.employee_id=e.id)
                        left join hr_attendance h on (z.hr_attendance_id=h.id)
                    GROUP BY
                        z.employee_id,
                        DATE(z.punching_time),
                        z.address_id,
                        z.attendance_type,
                        z.punch_type,
                        z.odoo_punch_type,
                        z.punching_time,
                        z.device_id,
                        h.check_out
                )
            """
        self.env.cr.execute(query)
