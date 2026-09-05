# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit
#
################################################################################

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ADMSDeviceCommand(models.Model):
    """Queue of commands to be sent to ADMS-connected devices.
    Devices poll /iclock/getrequest and pick up pending commands."""
    _name = 'adms.device.command'
    _description = 'ADMS Device Command Queue'
    _order = 'create_date asc'

    device_id = fields.Many2one(
        'biometric.device.details', string='Device',
        required=True, ondelete='cascade', index=True)
    command_id = fields.Integer(
        string='Command Sequence',
        help='Auto-incremented per device, sent as C:{id}:...')
    command_type = fields.Selection([
        ('info', 'Request Info'),
        ('reboot', 'Reboot Device'),
        ('set_time', 'Set Time'),
        ('sync_user', 'Sync User'),
        ('delete_user', 'Delete User'),
        ('enroll_fp', 'Enroll Fingerprint'),
        ('clear_data', 'Clear Data'),
        ('custom', 'Custom Command'),
    ], string='Command Type', required=True)
    command_body = fields.Text(
        string='Command Body',
        help='Raw command string sent to device. '
             'Auto-generated from command_type or manually set for custom.')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent to Device'),
        ('done', 'Executed'),
        ('failed', 'Failed'),
    ], string='Status', default='pending', required=True)
    result = fields.Text(string='Device Response')
    sent_time = fields.Datetime(string='Sent Time')
    done_time = fields.Datetime(string='Completed Time')

    # For fingerprint enrollment
    employee_id = fields.Many2one('hr.employee', string='Employee')
    finger_index = fields.Integer(string='Finger Index', default=0,
        help='0-9 for 10 fingers (0=right thumb)')

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-assign command_id per device."""
        for vals in vals_list:
            if 'command_id' not in vals or not vals.get('command_id'):
                device_id = vals.get('device_id')
                last = self.search(
                    [('device_id', '=', device_id)],
                    order='command_id desc', limit=1)
                vals['command_id'] = (last.command_id + 1) if last else 1
            # Auto-generate command_body from command_type
            if not vals.get('command_body'):
                vals['command_body'] = self._build_command_body(vals)
        return super().create(vals_list)

    def _build_command_body(self, vals):
        """Generate the raw command string from type and parameters."""
        cmd_type = vals.get('command_type', '')
        if cmd_type == 'reboot':
            return 'REBOOT'
        elif cmd_type == 'info':
            return 'INFO'
        elif cmd_type == 'clear_data':
            return 'CLEAR LOG'
        elif cmd_type == 'set_time':
            import pytz
            from datetime import datetime as dt
            # Use the device's configured timezone, not the server's local time
            device = self.env['biometric.device.details'].browse(vals.get('device_id', 0))
            tz_str = 'Asia/Dhaka'
            if device.exists():
                # Must match _get_device_timezone_for_adms() in the controller.
                # effective_timezone excluded — it is PyZK-only and must NOT be
                # used for ADMS (would cause ServerLocalTime to mismatch ATTLOG).
                tz_str = (device.custom_timezone
                          or device.company_id.partner_id.tz
                          or 'Asia/Dhaka')
            try:
                local_tz = pytz.timezone(tz_str)
            except pytz.UnknownTimeZoneError:
                local_tz = pytz.UTC
            now = dt.now(pytz.utc).astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')
            return f'SET OPTION ServerLocalTime={now}'
        elif cmd_type == 'enroll_fp':
            # PIN from employee's zk_user_id, finger index
            employee = self.env['hr.employee'].browse(vals.get('employee_id', 0))
            pin = employee.device_id_num if employee else '0'
            fid = vals.get('finger_index', 0)
            return f'ENROLL_FP PIN={pin}\tFID={fid}'
        elif cmd_type == 'sync_user':
            employee = self.env['hr.employee'].browse(vals.get('employee_id', 0))
            if employee:
                pin = employee.device_id_num or ''
                name = employee.name or ''
                return f'DATA UPDATE USERINFO PIN={pin}\tName={name}\tPri=0'
            return ''
        elif cmd_type == 'delete_user':
            employee = self.env['hr.employee'].browse(vals.get('employee_id', 0))
            if employee:
                pin = employee.device_id_num or ''
                return f'DATA DELETE USERINFO PIN={pin}'
            return ''
        return vals.get('command_body', '')

    def format_for_device(self):
        """Format command for ADMS protocol: C:{id}:{body}"""
        self.ensure_one()
        return f'C:{self.command_id}:{self.command_body}'


class BiometricFpTemplate(models.Model):
    """Store fingerprint templates received from ADMS devices."""
    _name = 'biometric.fp.template'
    _description = 'Biometric Fingerprint Template'
    _order = 'employee_id, finger_index'

    employee_id = fields.Many2one('hr.employee', string='Employee',
                                   required=True, ondelete='cascade')
    device_id = fields.Many2one('biometric.device.details', string='Source Device')
    finger_index = fields.Integer(string='Finger Index', default=0,
        help='0=Right Thumb, 1=Right Index, ... 9=Left Pinky')
    template_data = fields.Text(string='Template Data',
        help='Base64-encoded fingerprint template from device')
    template_size = fields.Integer(string='Template Size')
    template_version = fields.Char(string='Template Version')
    capture_time = fields.Datetime(string='Captured At', default=fields.Datetime.now)
