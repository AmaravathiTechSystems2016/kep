# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrEmployeeOnboarding(models.Model):
    _name = 'hr.employee.onboarding'
    _description = 'Employee Onboarding'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', required=True, copy=False, readonly=True)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', tracking=True)
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        store=True,
        readonly=True,
        string='Department',
    )
    company_id = fields.Many2one(related='employee_id.company_id', store=True, readonly=True)
    employee_category = fields.Selection(
        [
            ('common', 'Common'),
            ('worker', 'Manufacturing Worker'),
            ('office', 'Office Staff'),
            ('other', 'Other'),
        ],
        default='common',
        required=True,
        tracking=True,
    )
    template_id = fields.Many2one(
        'hr.onboarding.template',
        domain="[('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id), ('employee_category', '=', employee_category)]",
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        default='draft',
        tracking=True,
    )
    start_date = fields.Date(tracking=True)
    joining_confirmed = fields.Boolean(tracking=True)
    joining_confirmed_date = fields.Date(tracking=True)
    joining_confirmed_by = fields.Many2one('res.users', string='Joining Confirmed By', readonly=True)
    completion_date = fields.Date(tracking=True)
    probation_review_date = fields.Date(tracking=True)
    probation_review_state = fields.Selection(
        [
            ('draft', 'Not Scheduled'),
            ('scheduled', 'Scheduled'),
            ('done', 'Done'),
        ],
        default='draft',
        tracking=True,
    )
    probation_review_notes = fields.Text()
    notes = fields.Text()
    line_ids = fields.One2many('hr.employee.onboarding.line', 'onboarding_id', string='Checklist Lines', copy=True)
    line_count = fields.Integer(compute='_compute_line_count')
    done_line_count = fields.Integer(compute='_compute_line_count')
    progress_rate = fields.Integer(compute='_compute_line_count')

    def _get_notification_email(self):
        self.ensure_one()
        return (
            self.employee_id.work_email
            or self.employee_id.private_email
            or self.employee_id.user_id.email
            or self.employee_id.work_contact_id.email
        )

    def _send_template_email(self, xmlid):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            return
        for record in self:
            email_to = record._get_notification_email()
            if not email_to:
                continue
            template.send_mail(
                record.id,
                force_send=True,
                email_values={'email_to': email_to},
            )

    def _get_pending_document_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(
            lambda line: line.step_type == 'document' and line.required and line.verification_status != 'verified'
        )

    def _get_pending_checklist_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.status != 'done')

    def _notify_document_rejected(self, line):
        template = self.env.ref('dotbd_hr_onboarding_suite.email_template_hr_onboarding_document_rejected', raise_if_not_found=False)
        if not template:
            return
        email_to = self._get_notification_email()
        if not email_to:
            return
        template.send_mail(
            line.id,
            force_send=True,
            email_values={'email_to': email_to},
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.employee.onboarding') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.status')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)
            record.done_line_count = len(record.line_ids.filtered(lambda line: line.status == 'done'))
            record.progress_rate = int((record.done_line_count / record.line_count) * 100) if record.line_count else 0

    @api.onchange('template_id')
    def _onchange_template_id(self):
        for record in self:
            if record.template_id:
                record.employee_category = record.template_id.employee_category
                record.line_ids = [(5, 0, 0)] + [
                    (0, 0, {
                        'sequence': line.sequence,
                        'name': line.name,
                        'step_type': line.step_type,
                        'required': line.required,
                        'responsible_role': line.responsible_role,
                        'duration_days': line.duration_days,
                        'notes': line.notes,
                    })
                    for line in record.template_id.line_ids
                ]

    def action_load_template(self):
        for record in self:
            if not record.template_id:
                raise UserError(_('Please select an onboarding template first.'))
            record._onchange_template_id()

    def action_start(self):
        for record in self:
            if not record.line_ids and record.template_id:
                record.action_load_template()
            if not record.line_ids:
                raise UserError(_('Add checklist steps before starting onboarding.'))
            record.write({
                'state': 'in_progress',
                'start_date': record.start_date or fields.Date.context_today(self),
            })
            record._send_template_email('dotbd_hr_onboarding_suite.email_template_hr_onboarding_started')

    def action_confirm_joining(self):
        for record in self:
            record.write({
                'joining_confirmed': True,
                'joining_confirmed_date': fields.Date.context_today(self),
                'joining_confirmed_by': self.env.user.id,
            })
            if not record.start_date:
                record.start_date = fields.Date.context_today(self)

    def action_schedule_probation_review(self):
        for record in self:
            record.write({
                'probation_review_state': 'scheduled',
                'probation_review_date': record.joining_confirmed_date or record.start_date or fields.Date.context_today(self),
            })

    def action_mark_probation_review_done(self):
        for record in self:
            record.write({
                'probation_review_state': 'done',
            })

    def action_mark_done(self):
        for record in self:
            if not record.joining_confirmed:
                raise UserError(_('Please confirm joining before completing onboarding.'))
            pending_required_docs = record.line_ids.filtered(
                lambda line: line.required and line.step_type == 'document' and line.verification_status != 'verified'
            )
            if pending_required_docs:
                raise UserError(_('Please verify all required document lines before marking onboarding as done.'))
            if record.line_count and record.done_line_count < record.line_count:
                raise UserError(_('Please complete all checklist steps before marking onboarding as done.'))
            record.write({
                'state': 'done',
                'completion_date': fields.Date.context_today(self),
            })
            record._send_template_email('dotbd_hr_onboarding_suite.email_template_hr_onboarding_completed')

    def action_reset(self):
        for record in self:
            record.write({
                'state': 'draft',
                'completion_date': False,
                'start_date': False,
                'joining_confirmed': False,
                'joining_confirmed_date': False,
                'joining_confirmed_by': False,
                'probation_review_date': False,
                'probation_review_state': 'draft',
                'probation_review_notes': False,
            })
            for line in record.line_ids:
                line.action_reset()

    def action_cancel(self):
        self.write({'state': 'cancel'})


class HrEmployeeOnboardingLine(models.Model):
    _name = 'hr.employee.onboarding.line'
    _description = 'Employee Onboarding Checklist Line'
    _order = 'sequence, id'

    onboarding_id = fields.Many2one('hr.employee.onboarding', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    step_type = fields.Selection(
        [
            ('information', 'Information'),
            ('document', 'Document Verification'),
            ('training', 'Training'),
            ('access', 'Access / Asset'),
            ('review', 'Review'),
            ('other', 'Other'),
        ],
        default='other',
        required=True,
    )
    required = fields.Boolean(default=True)
    document_name = fields.Char(string='Document Name')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'hr_employee_onboarding_line_attachment_rel',
        'line_id',
        'attachment_id',
        string='Attachments',
    )
    verification_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('verified', 'Verified'),
            ('rejected', 'Rejected'),
        ],
        default='pending',
    )
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('done', 'Done'),
            ('skipped', 'Skipped'),
        ],
        default='pending',
    )
    responsible_role = fields.Char(string='Responsible Role')
    done_by = fields.Many2one('res.users', string='Done By', readonly=True)
    done_on = fields.Datetime(string='Done On', readonly=True)
    verified_by = fields.Many2one('res.users', string='Verified By', readonly=True)
    verified_on = fields.Datetime(string='Verified On', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason')
    duration_days = fields.Integer(string='Target Days')
    notes = fields.Text()

    def action_mark_done(self):
        for line in self:
            line.write({
                'status': 'done',
                'done_by': self.env.user.id,
                'done_on': fields.Datetime.now(),
            })

    def action_mark_verified(self):
        for line in self:
            line.write({
                'verification_status': 'verified',
                'status': 'done',
                'verified_by': self.env.user.id,
                'verified_on': fields.Datetime.now(),
                'done_by': self.env.user.id,
                'done_on': fields.Datetime.now(),
            })

    def action_mark_rejected(self):
        for line in self:
            line.write({
                'verification_status': 'rejected',
                'status': 'pending',
                'verified_by': self.env.user.id,
                'verified_on': fields.Datetime.now(),
            })
            line.onboarding_id._notify_document_rejected(line)

    def action_reset(self):
        self.write({
            'status': 'pending',
            'verification_status': 'pending',
            'done_by': False,
            'done_on': False,
            'verified_by': False,
            'verified_on': False,
            'rejection_reason': False,
        })
