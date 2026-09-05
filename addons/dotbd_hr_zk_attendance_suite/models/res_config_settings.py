# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#
################################################################################
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """Inherit the model to add late check-in configuration fields"""
    _inherit = 'res.config.settings'

    enable_late_penalties = fields.Boolean(
        string="Enable Late Check-in Penalties",
        config_parameter='dotbd_hr_zk_attendance_suite.enable_late_penalties',
        default=True,
        help='Enable automatic tracking and penalty calculation for late check-ins')

    late_check_in_after = fields.Integer(
        config_parameter='dotbd_hr_zk_attendance_suite.late_check_in_after',
        string="Tolerance (Minutes)",
        default=0,
        help='Grace period in minutes. Employees arriving within this time are not marked as late. '
             'For example: 15 minutes means if an employee is 10 minutes late, it will not count.')

    maximum_minutes = fields.Integer(
        config_parameter='dotbd_hr_zk_attendance_suite.maximum_minutes',
        string="Maximum Late Time (Minutes)",
        default=240,
        help="Maximum time limit an employee is considered as late. "
             "Beyond this, they may be marked as absent. (Default: 240 minutes = 4 hours)")

    deduction_amount = fields.Float(
        config_parameter='dotbd_hr_zk_attendance_suite.deduction_amount',
        string="Penalty Amount",
        help='Amount to be deducted for late check-in')

    deduction_type = fields.Selection(
        selection=[('minutes', 'Per Minute'), ('fixed', 'Fixed Amount')],
        config_parameter='dotbd_hr_zk_attendance_suite.deduction_type',
        default="minutes",
        string='Penalty Type',
        help='Per Minute: Deduct specified amount for each late minute\n'
             'Fixed Amount: Deduct fixed amount per late instance')

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id.id)

    # ── Weekend day configuration ──────────────────────────────────────────
    weekend_monday = fields.Boolean(
        string="Monday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_mon',
        default=False)
    weekend_tuesday = fields.Boolean(
        string="Tuesday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_tue',
        default=False)
    weekend_wednesday = fields.Boolean(
        string="Wednesday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_wed',
        default=False)
    weekend_thursday = fields.Boolean(
        string="Thursday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_thu',
        default=False)
    weekend_friday = fields.Boolean(
        string="Friday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_fri',
        default=True)
    weekend_saturday = fields.Boolean(
        string="Saturday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_sat',
        default=True)
    weekend_sunday = fields.Boolean(
        string="Sunday",
        config_parameter='dotbd_hr_zk_attendance_suite.weekend_sun',
        default=False)

    # NOTE: set_values/get_values are NOT needed here because all fields use
    # the config_parameter= attribute, which makes Odoo handle get/set automatically.
    # Having custom set_values/get_values with config_parameter= causes double-setting
    # and the boolean comparison bug (True == 'True' returns False on fresh install).
