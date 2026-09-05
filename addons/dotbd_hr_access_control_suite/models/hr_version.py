# -*- coding: utf-8 -*-

from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    contract_date_start = fields.Date(
        string='Contract Start Date',
        tracking=True,
        readonly=False,
        groups=(
            'hr.group_hr_manager,'
            'dotbd_hr_access_control_suite.group_hr_employee'
        ),
    )

    # Leave validation reads this related field through the employee record.
    # Keep it read-only for employees, but make it available to self-service.
    probation_end_date = fields.Date(
        string='Probation End Date',
        related='trial_date_end',
        readonly=True,
        groups=(
            'base.group_system,'
            'dotbd_hr_access_control_suite.group_hr_employee'
        ),
    )
