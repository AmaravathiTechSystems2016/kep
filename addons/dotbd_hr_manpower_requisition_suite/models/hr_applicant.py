# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    source_type = fields.Selection(
        [
            ('employee_referral', 'Employee Referral'),
            ('internal_recruitment', 'Internal Recruitment'),
            ('geographical_focus', 'Geographical Focus'),
            ('job_portal', 'Job Portal'),
            ('social_media', 'Social Media'),
            ('other', 'Other'),
        ],
        string='Source Type',
        tracking=True,
        help='How the candidate reached this recruitment pipeline.',
    )
    referred_by_employee_id = fields.Many2one(
        'hr.employee',
        string='Referred By',
        tracking=True,
        help='Employee who referred this applicant, if applicable.',
    )
    source_notes = fields.Text(
        string='Source Notes',
        help='Extra details about how the candidate was sourced or referred.',
    )
    screening_status = fields.Selection(
        [
            ('draft', 'Not Screened'),
            ('screened', 'Screened'),
            ('shortlisted', 'Shortlisted'),
            ('rejected', 'Rejected'),
        ],
        string='Screening Status',
        default='draft',
        tracking=True,
        help='Internal screening result used before interview scheduling.',
    )
    education_fit = fields.Selection(
        [
            ('match', 'Matches'),
            ('partial', 'Partially Matches'),
            ('no', 'Does Not Match'),
        ],
        string='Education Fit',
        help='How well the applicant education matches the role requirement.',
    )
    experience_fit = fields.Selection(
        [
            ('match', 'Matches'),
            ('partial', 'Partially Matches'),
            ('no', 'Does Not Match'),
        ],
        string='Experience Fit',
        help='How well the applicant experience matches the role requirement.',
    )
    skill_fit = fields.Selection(
        [
            ('match', 'Matches'),
            ('partial', 'Partially Matches'),
            ('no', 'Does Not Match'),
        ],
        string='Skill Assessment',
        help='Outcome of the skill evaluation or practical test.',
    )
    location_fit = fields.Selection(
        [
            ('match', 'Matches'),
            ('partial', 'Partially Matches'),
            ('no', 'Does Not Match'),
        ],
        string='Location Fit',
        help='Whether the candidate location is suitable for the job.',
    )
    shift_fit = fields.Selection(
        [
            ('match', 'Matches'),
            ('partial', 'Partially Matches'),
            ('no', 'Does Not Match'),
        ],
        string='Shift Fit',
        help='Whether the candidate can meet shift or work-hour requirements.',
    )
    screening_notes = fields.Text(
        string='Screening Notes',
        help='Notes captured during screening and shortlisting.',
    )
    attendance_category = fields.Selection(
        related='job_id.attendance_category',
        string='Employee Category',
        store=True,
        readonly=True,
    )
    stage_id = fields.Many2one(
        'hr.recruitment.stage',
        'Stage',
        ondelete='restrict',
        tracking=True,
        compute='_compute_stage',
        store=True,
        readonly=False,
        domain="['|', ('job_ids', '=', False), ('job_ids', '=', job_id), '|', ('attendance_category', '=', False), ('attendance_category', 'in', ['common', attendance_category])]",
        copy=False,
        index=True,
        group_expand='_read_group_stage_ids',
    )

    def _get_employee_create_vals(self):
        vals = super()._get_employee_create_vals()
        if self.job_id and self.job_id.attendance_category in ('worker', 'office', 'other'):
            vals['attendance_category'] = self.job_id.attendance_category
        else:
            default_category = self.env.context.get('default_attendance_category')
            if default_category in ('worker', 'office', 'other'):
                vals['attendance_category'] = default_category
        return vals

    def create_employee_from_applicant(self):
        action = super().create_employee_from_applicant()
        for applicant in self:
            job = applicant.job_id.sudo()
            if job and job.id and job.no_of_employee:
                if job.employee_count >= job.no_of_employee:
                    job.write({
                        'vacancy_state': 'closed',
                        'vacancy_closed_by': self.env.user.id,
                        'vacancy_closed_on': fields.Datetime.now(),
                    })
        return action

    def _get_recruitment_stage_domain(self, job=False):
        job = job or self.job_id
        if not job:
            return [
                '|',
                ('attendance_category', '=', False),
                ('attendance_category', '=', 'common'),
            ]
        return job._get_recruitment_stage_domain()

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        applicants = self.with_context(active_test=False).search(domain)
        jobs = applicants.mapped('job_id')
        if not jobs:
            search_domain = [
                ('job_ids', '=', False),
                '|',
                ('attendance_category', '=', False),
                ('attendance_category', '=', 'common'),
            ]
        else:
            categories = list({category for category in applicants.mapped('attendance_category') if category} | {'common'})
            search_domain = [
                '|',
                ('job_ids', '=', False),
                ('job_ids', 'in', jobs.ids),
                '|',
                ('attendance_category', '=', False),
                ('attendance_category', 'in', categories),
            ]
        stage_ids = stages.sudo().search(search_domain, order=stages._order)
        return stages.browse(stage_ids.ids)

    @api.depends('job_id', 'job_id.attendance_category')
    def _compute_stage(self):
        stage_model = self.env['hr.recruitment.stage']
        for applicant in self:
            if not applicant.job_id:
                if not applicant.stage_id:
                    applicant.stage_id = stage_model.search([
                        ('job_ids', '=', False),
                        '|',
                        ('attendance_category', '=', False),
                        ('attendance_category', '=', 'common'),
                    ], order='sequence asc', limit=1)
                continue

            allowed_stages = stage_model.search(applicant._get_recruitment_stage_domain(), order='sequence asc')
            if not applicant.stage_id or applicant.stage_id not in allowed_stages:
                applicant.stage_id = allowed_stages[:1] if allowed_stages else False

    def reset_applicant(self):
        """Reinsert the applicant into the recruitment pipe in the first allowed stage."""
        for applicant in self:
            applicant.write({
                'stage_id': applicant.job_id._get_first_stage().id if applicant.job_id else False,
                'refuse_reason_id': False,
            })
