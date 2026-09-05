# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrResignation(models.Model):
    _inherit = 'hr.resignation'

    @api.depends('employee_id')
    def _compute_notice_period(self):
        """Read protected contract data without exposing it to employees."""
        today = fields.Date.today()
        Version = self.env['hr.version'].sudo()
        for resignation in self:
            employee = resignation.employee_id.sudo()
            resignation.joined_date = employee.joining_date if employee else False
            resignation.employee_contract = False
            resignation.notice_period = 0
            if not employee:
                continue
            contract = Version.search([
                ('employee_id', '=', employee.id),
                '|', ('date_start', '=', False), ('date_start', '<=', today),
                '|', ('date_end', '=', False), ('date_end', '>=', today),
            ], limit=1)
            if contract:
                resignation.employee_contract = contract.contract_template_id.name
                resignation.notice_period = (
                    employee.notice_period_days or contract.notice_days or 0
                )

    attendance_category = fields.Selection(
        related='employee_id.attendance_category',
        string='Employee Category',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='employee_id.company_id.currency_id',
        string='Currency',
        readonly=True,
    )
    handover_status = fields.Selection(
        [
            ('not_started', 'Not Started'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
        ],
        string='Knowledge Transfer Status',
        default='not_started',
        tracking=True,
    )
    handover_recipient = fields.Many2one(
        'hr.employee', string='Handover To', tracking=True)
    handover_notes = fields.Text(string='Handover Notes', tracking=True)
    department_clearance = fields.Selection(
        [('pending', 'Pending'), ('cleared', 'Cleared'), ('not_applicable', 'Not Applicable')],
        string='Department Clearance', default='pending', tracking=True)
    stores_clearance = fields.Selection(
        [('pending', 'Pending'), ('cleared', 'Cleared'), ('not_applicable', 'Not Applicable')],
        string='Stores / PPE Clearance', default='pending', tracking=True)
    admin_clearance = fields.Selection(
        [('pending', 'Pending'), ('cleared', 'Cleared'), ('not_applicable', 'Not Applicable')],
        string='Admin / Asset Clearance', default='pending', tracking=True)
    hr_clearance = fields.Selection(
        [('pending', 'Pending'), ('cleared', 'Cleared'), ('not_applicable', 'Not Applicable')],
        string='HR Clearance', default='pending', tracking=True)
    finance_clearance = fields.Selection(
        [('pending', 'Pending'), ('cleared', 'Cleared'), ('not_applicable', 'Not Applicable')],
        string='Finance Clearance', default='pending', tracking=True)
    contractor_clearance = fields.Selection(
        [('pending', 'Pending'), ('cleared', 'Cleared'), ('not_applicable', 'Not Applicable')],
        string='Contractor Clearance', default='not_applicable', tracking=True)
    clearance_notes = fields.Text(string='Clearance Notes', tracking=True)
    settlement_status = fields.Selection(
        [('pending', 'Pending'), ('in_progress', 'In Progress'), ('completed', 'Completed')],
        string='Full & Final Status', default='pending', tracking=True)
    leave_encashment_amount = fields.Monetary(
        string='Leave Encashment', currency_field='currency_id', tracking=True)
    gratuity_amount = fields.Monetary(
        string='Gratuity', currency_field='currency_id', tracking=True)
    dues_recovery_amount = fields.Monetary(
        string='Dues Recovery', currency_field='currency_id', tracking=True)
    esop_clawback_amount = fields.Monetary(
        string='ESOP Clawback', currency_field='currency_id', tracking=True)
    settlement_notes = fields.Text(string='Settlement Notes', tracking=True)
    exit_interview_completed = fields.Boolean(
        string='Exit Interview Completed', tracking=True)
    exit_interview_feedback = fields.Text(
        string='Exit Interview Feedback', tracking=True)
    relieving_letter_issued = fields.Boolean(
        string='Relieving Letter Issued', tracking=True)
    experience_certificate_issued = fields.Boolean(
        string='Experience Certificate Issued', tracking=True)
    service_certificate_issued = fields.Boolean(
        string='Service Certificate Issued', tracking=True)
    trade_skill_certificate_issued = fields.Boolean(
        string='Trade Skill Certificate Issued', tracking=True)
    pf_esi_transfer_status = fields.Selection(
        [
            ('not_applicable', 'Not Applicable'),
            ('pending', 'Pending'),
            ('assistance_provided', 'Assistance Provided'),
            ('completed', 'Completed'),
        ],
        string='PF / ESI Transfer',
        default='pending',
        tracking=True,
    )
    pf_esi_transfer_notes = fields.Text(
        string='PF / ESI Transfer Notes', tracking=True)
