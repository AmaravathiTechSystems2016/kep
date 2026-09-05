# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit
#
################################################################################
from odoo import api, fields, models


class BiometricDeviceLog(models.Model):
    """Model to store per-device operation logs (download, connection, sync, etc.)"""
    _name = 'biometric.device.log'
    _description = 'Biometric Device Operation Log'
    _order = 'log_time desc'
    _rec_name = 'display_name'

    device_id = fields.Many2one(
        'biometric.device.details', string='Device',
        required=True, ondelete='cascade', index=True,
        help='The biometric device this log belongs to')

    log_type = fields.Selection([
        ('download', 'Attendance Download'),
        ('connection', 'Connection Test'),
        ('sync', 'User Sync'),
        ('live_capture', 'Live Capture'),
        ('info_refresh', 'Device Info Refresh'),
        ('other', 'Other'),
    ], string='Operation Type', required=True, default='download', index=True)

    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('warning', 'Warning'),
    ], string='Status', required=True, default='success', index=True)

    log_time = fields.Datetime(
        string='Time', required=True,
        default=fields.Datetime.now, index=True)

    # Download-specific fields
    records_found = fields.Integer(
        string='Records on Device', default=0,
        help='Total attendance records found on device')
    records_new = fields.Integer(
        string='New Records Imported', default=0,
        help='New records successfully imported')
    records_duplicate = fields.Integer(
        string='Duplicates Skipped', default=0,
        help='Records skipped because they already existed')
    records_failed = fields.Integer(
        string='Failed Records', default=0,
        help='Records that failed to import')
    employees_not_found = fields.Integer(
        string='Unknown Employees', default=0,
        help='Punches from device user IDs not linked to any employee')

    duration = fields.Float(
        string='Duration (sec)', digits=(10, 2), default=0.0,
        help='Time taken for the operation in seconds')

    error_message = fields.Text(
        string='Error Message',
        help='Error details if the operation failed')
    details = fields.Text(
        string='Details',
        help='Additional information about the operation')

    company_id = fields.Many2one(
        'res.company', string='Company',
        related='device_id.company_id', store=True)

    display_name = fields.Char(
        string='Name', compute='_compute_display_name', store=True)

    @api.depends('device_id', 'log_type', 'log_time', 'status')
    def _compute_display_name(self):
        type_labels = dict(self._fields['log_type'].selection)
        status_labels = dict(self._fields['status'].selection)
        for rec in self:
            device_name = rec.device_id.name or 'Unknown'
            log_type = type_labels.get(rec.log_type, rec.log_type)
            status = status_labels.get(rec.status, rec.status)
            time_str = fields.Datetime.to_string(rec.log_time) if rec.log_time else ''
            rec.display_name = f"{device_name} - {log_type} [{status}] {time_str}"
