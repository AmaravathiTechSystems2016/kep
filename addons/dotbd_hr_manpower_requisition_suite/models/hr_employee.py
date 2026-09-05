# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    blood_group = fields.Selection(
        [
            ('a_pos', 'A+'),
            ('a_neg', 'A-'),
            ('b_pos', 'B+'),
            ('b_neg', 'B-'),
            ('ab_pos', 'AB+'),
            ('ab_neg', 'AB-'),
            ('o_pos', 'O+'),
            ('o_neg', 'O-'),
        ],
        string='Blood Group',
        tracking=True,
    )
    aadhaar_number = fields.Char(string='Aadhaar Number', tracking=True)
    pan_number = fields.Char(string='PAN Number', tracking=True)
    nominee_name = fields.Char(string='Nominee Name', tracking=True)
    nominee_relation = fields.Char(string='Nominee Relation', tracking=True)
    nominee_phone = fields.Char(string='Nominee Phone', tracking=True)

    # Additional employee-master fields used by HR for worker and office staff.
    grade_band = fields.Char(string='Grade / Band', tracking=True)
    confirmation_date = fields.Date(string='Confirmation Date', tracking=True)
    notice_period_days = fields.Integer(string='Notice Period (Days)', tracking=True)
    cost_centre = fields.Char(string='Cost Centre', tracking=True)
    machine_line_assignment = fields.Char(
        string='Machine / Production Line', tracking=True)
    safety_certification = fields.Text(string='Safety Certification', tracking=True)
    safety_certification_expiry = fields.Date(
        string='Safety Certification Expiry', tracking=True)
    ppe_issue_log = fields.Text(string='PPE Issue Log', tracking=True)
    contractor_code = fields.Char(string='Contractor Code', tracking=True)
    joining_source = fields.Selection(
        [
            ('direct', 'Direct'),
            ('contractor', 'Contractor'),
            ('referral', 'Referral'),
            ('campus', 'Campus'),
            ('portal', 'Portal'),
            ('consultant', 'Consultant'),
            ('internal', 'Internal'),
            ('other', 'Other'),
        ],
        string='Joining Source',
        tracking=True,
    )
    employee_status = fields.Selection(
        [
            ('active', 'Active'),
            ('probation', 'Probation'),
            ('confirmed', 'Confirmed'),
            ('on_leave', 'On Leave'),
            ('separated', 'Separated'),
        ],
        string='Employee Status',
        default='active',
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('attendance_category'):
                default_category = self.env.context.get('default_attendance_category')
                if default_category in ('worker', 'office', 'other'):
                    vals['attendance_category'] = default_category
        return super().create(vals_list)
