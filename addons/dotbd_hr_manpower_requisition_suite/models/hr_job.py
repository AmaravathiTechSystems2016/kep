# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class HrJob(models.Model):
    _inherit = 'hr.job'

    attendance_category = fields.Selection(
        [
            ('worker', 'Manufacturing Worker'),
            ('office', 'Office Staff'),
            ('other', 'Other'),
        ],
        string='Employee Category',
        tracking=True,
        help='Category used to create employees in the correct worker/office bucket.',
    )
    vacancy_state = fields.Selection(
        [('open', 'Open'), ('closed', 'Closed')],
        string='Vacancy Status',
        default='open',
        tracking=True,
    )
    vacancy_reason = fields.Selection(
        [
            ('new_position', 'New Position'),
            ('replacement', 'Replacement'),
            ('expansion', 'Expansion'),
            ('turnover', 'Turnover'),
            ('seasonal', 'Seasonal Demand'),
            ('other', 'Other'),
        ],
        string='Vacancy Reason',
        tracking=True,
    )
    replacement_employee_id = fields.Many2one('hr.employee', string='Replacement For', tracking=True)
    vacancy_closed_by = fields.Many2one('res.users', string='Vacancy Closed By', readonly=True, copy=False)
    vacancy_closed_on = fields.Datetime(string='Vacancy Closed On', readonly=True, copy=False)
    sourcing_channel_line_ids = fields.One2many(
        'hr.job.sourcing.channel',
        'job_id',
        string='Sourcing Channels',
        copy=True,
    )

    def action_close_vacancy(self):
        for job in self:
            job.write({
                'vacancy_state': 'closed',
                'vacancy_closed_by': self.env.user.id,
                'vacancy_closed_on': fields.Datetime.now(),
            })

    def action_reopen_vacancy(self):
        self.write({
            'vacancy_state': 'open',
            'vacancy_closed_by': False,
            'vacancy_closed_on': False,
        })

    def _get_recruitment_stage_domain(self):
        self.ensure_one()
        category = self.attendance_category or 'common'
        return [
            '|',
            ('job_ids', '=', False),
            ('job_ids', '=', self.id),
            '|',
            ('attendance_category', '=', False),
            ('attendance_category', 'in', ['common', category]),
        ]

    def _get_first_stage(self):
        self.ensure_one()
        return self.env['hr.recruitment.stage'].search(
            self._get_recruitment_stage_domain(),
            order='sequence asc',
            limit=1,
        )


class HrJobSourcingChannel(models.Model):
    _name = 'hr.job.sourcing.channel'
    _description = 'Job Sourcing Channel'
    _order = 'id asc'

    job_id = fields.Many2one('hr.job', string='Job Position', required=True, ondelete='cascade')
    channel_type = fields.Selection(
        [
            ('employee_referral', 'Employee Referrals'),
            ('internal_recruitment', 'Internal Recruitment'),
            ('geographical_focus', 'Geographical Focus'),
        ],
        string='Channel',
        required=True,
        default='employee_referral',
    )
    primary_source = fields.Char(
        string='Primary Source',
        required=True,
        help='Main source used for this hiring channel, such as internal notice board, referral pool, or local area hiring.',
    )
    notes = fields.Text(string='Notes')
