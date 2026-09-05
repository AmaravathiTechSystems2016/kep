# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit
################################################################################
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    """Inherit the model to add field"""
    _inherit = 'hr.employee'

    attendance_category = fields.Selection([
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], string='Attendance Category', default='other', tracking=True,
        help='Use this field to separate manufacturing workers and office staff '
             'for attendance, leave, shift, and payroll rules.')

    device_id_num = fields.Char(string='ZK Device User ID',
                                help="Give the biometric device id")
    late_check_in_count = fields.Integer(
        string="Late Check-In", compute="_compute_late_check_in_count",
        help="Count of employee's late checkin")
    fp_template_count = fields.Integer(
        string='Fingerprints', compute='_compute_fp_template_count',
        help='Number of fingerprint templates stored for this employee')

    _device_id_num_unique = models.Constraint(
        'UNIQUE(device_id_num, company_id)',
        'The ZK Device User ID must be unique per company! Duplicate IDs lead to cross-assigned attendance.',
    )

    def _compute_fp_template_count(self):
        """Compute fingerprint template count"""
        for rec in self:
            rec.fp_template_count = self.env['biometric.fp.template'].search_count(
                [('employee_id', '=', rec.id)])

    def action_to_open_late_check_in_records(self):
        """
            :return: dictionary defining the action to open the late check-in
            records window.
            :rtype: dict
        """
        return {
            'name': _('Employee Late Check-in'),
            'domain': [('employee_id', '=', self.id)],
            'res_model': 'late.check.in',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'limit': 80}

    def _compute_late_check_in_count(self):
        """Compute the late check-in count"""
        for rec in self:
            rec.late_check_in_count = self.env['late.check.in'].search_count(
                [('employee_id', '=', rec.id)])

    def action_view_fp_templates(self):
        """View fingerprint templates for this employee."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fingerprint Templates'),
            'res_model': 'biometric.fp.template',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_enroll_fingerprint(self):
        """Trigger fingerprint enrollment on an ADMS device.
        User selects which device and finger to enroll on."""
        self.ensure_one()
        if not self.device_id_num:
            raise UserError(_(
                'Please set the ZK Device User ID first before enrolling fingerprint.'))

        # Find ADMS/hybrid devices
        adms_devices = self.env['biometric.device.details'].search([
            ('connection_mode', 'in', ['adms', 'hybrid']),
        ])
        if not adms_devices:
            raise UserError(_(
                'No ADMS or Hybrid devices configured. '
                'Fingerprint enrollment from Odoo requires a device in Cloud (ADMS) or Hybrid mode.'))

        # Open enrollment wizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enroll Fingerprint'),
            'res_model': 'adms.device.command',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_command_type': 'enroll_fp',
                'default_employee_id': self.id,
                'default_device_id': adms_devices[0].id if len(adms_devices) == 1 else False,
            },
        }
