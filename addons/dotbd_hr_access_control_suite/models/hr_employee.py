# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Leave eligibility needs the employee's contract start date. Expose the
    # date for self-service; model ACLs still prevent employee contract edits.
    contract_date_start = fields.Date(
        related='version_id.contract_date_start',
        inherited=True,
        readonly=False,
        groups=(
            'hr.group_hr_manager,'
            'dotbd_hr_access_control_suite.group_hr_employee'
        ),
    )

    # The employee dashboard reads this technical link. Keep payroll fields
    # restricted, but allow the dedicated employee group to read the link.
    version_id = fields.Many2one(
        'hr.version',
        compute='_compute_version_id',
        search='_search_version_id',
        ondelete='cascade',
        required=True,
        store=False,
        compute_sudo=True,
        groups=(
            'hr.group_hr_user,'
            'dotbd_hr_access_control_suite.group_hr_employee'
        ),
    )
