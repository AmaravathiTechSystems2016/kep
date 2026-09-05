# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ManpowerRequisition(models.Model):
    _name = 'manpower.requisition'
    _description = 'Manpower Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    department_id = fields.Many2one('hr.department', string='Department', required=True, tracking=True)
    requested_by = fields.Many2one(
        'hr.employee',
        string='Requested By',
        default=lambda self: self.env.user.employee_id,
        tracking=True,
    )
    employee_category = fields.Selection(
        [('worker', 'Manufacturing Worker'), ('office', 'Office Staff')],
        string='Employee Category',
        required=True,
        tracking=True,
    )
    request_date = fields.Date(string='Request Date', default=fields.Date.context_today, tracking=True)
    request_type = fields.Selection(
        related='employee_category',
        string='Request Type',
        store=True,
        readonly=True,
    )
    justification = fields.Text(string='Justification', tracking=True)
    requested_headcount = fields.Integer(
        string='Requested Headcount',
        compute='_compute_requested_headcount',
        store=True,
        help='Total people requested from all requisition lines.',
    )
    headcount_gap = fields.Integer(
        string='Shortfall',
        compute='_compute_headcount_gap',
        store=True,
        help='Remaining shortfall between requested and approved count.',
    )
    job_id = fields.Many2one('hr.job', string='Linked Job Position', tracking=True)
    job_count = fields.Integer(string='Generated Jobs', compute='_compute_job_count')
    line_ids = fields.One2many('manpower.requisition.line', 'requisition_id', string='Requisition Lines', copy=True)
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        readonly=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if not vals.get('employee_category'):
                employee_id = vals.get('requested_by')
                if employee_id:
                    employee = self.env['hr.employee'].browse(employee_id)
                    if employee.attendance_category in ('worker', 'office'):
                        vals['employee_category'] = employee.attendance_category
            if not vals.get('employee_category'):
                vals['employee_category'] = 'worker'
            if vals.get('name', 'New') in ('New', '/'):
                vals['name'] = seq.next_by_code('manpower.requisition') or _('New')
        return super().create(vals_list)

    @api.onchange('requested_by')
    def _onchange_requested_by(self):
        for rec in self:
            if rec.requested_by and rec.requested_by.attendance_category in ('worker', 'office'):
                rec.employee_category = rec.requested_by.attendance_category

    @api.depends('line_ids.required_count')
    def _compute_requested_headcount(self):
        for rec in self:
            rec.requested_headcount = sum(rec.line_ids.mapped('required_count'))

    @api.depends('line_ids.approved_count')
    def _compute_headcount_gap(self):
        for rec in self:
            rec.headcount_gap = max(rec.requested_headcount - sum(rec.line_ids.mapped('approved_count')), 0)

    @api.depends('line_ids.job_id')
    def _compute_job_count(self):
        for rec in self:
            rec.job_count = len(rec.line_ids.mapped('job_id'))

    def _validate_requisition(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Please add at least one requisition line before submitting.'))

            for line in rec.line_ids:
                if rec.request_type == 'worker':
                    missing = []
                    if not line.trade_skill:
                        missing.append(_('Trade / Skill'))
                    if not line.shift_requirement:
                        missing.append(_('Shift Requirement'))
                    if missing:
                        raise ValidationError(_(
                            'Worker requisitions require the following fields on each line: %s.'
                        ) % ', '.join(missing))

                if rec.request_type == 'office':
                    missing = []
                    if not line.qualification:
                        missing.append(_('Qualification'))
                    if not line.technical_skills:
                        missing.append(_('Technical / Functional Skills'))
                    if missing:
                        raise ValidationError(_(
                            'Office staff requisitions require the following fields on each line: %s.'
                        ) % ', '.join(missing))

    def action_submit(self):
        for rec in self:
            rec._validate_requisition()
            rec.state = 'submitted'
            rec.message_post(
                body=_('Manpower requisition submitted by %s.') % (self.env.user.display_name,),
                subtype_xmlid='mail.mt_comment',
            )

    def action_open_partial_approval_wizard(self):
        self.ensure_one()
        if self.state != 'submitted':
            raise ValidationError(_('You can only partially approve a submitted requisition.'))
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise AccessError(_('Only an HR manager can approve this requisition.'))

        wizard_lines = []
        for line in self.line_ids:
            wizard_lines.append((0, 0, {
                'requisition_line_id': line.id,
                'approved_count': line.approved_count,
            }))

        wizard = self.env['manpower.requisition.partial.approval.wizard'].create({
            'requisition_id': self.id,
            'line_ids': wizard_lines,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Partial Approval'),
            'res_model': 'manpower.requisition.partial.approval.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise ValidationError(_('You can only approve a submitted requisition.'))
            if not self.env.user.has_group('hr.group_hr_manager'):
                raise AccessError(_('Only an HR manager can approve this requisition.'))
            rec._validate_partial_approval()
            requested_total = rec.requested_headcount
            approved_total = sum(rec.line_ids.mapped('approved_count'))
            if approved_total <= 0:
                raise ValidationError(_('Please approve at least one position before confirming.'))
            if approved_total < requested_total:
                rec.state = 'submitted'
                rec.message_post(
                    body=_('Manpower requisition partially approved by %s. Approved %s out of %s.') % (
                        self.env.user.display_name,
                        approved_total,
                        requested_total,
                    ),
                    subtype_xmlid='mail.mt_comment',
                )
            else:
                rec.state = 'approved'
                rec.message_post(
                    body=_('Manpower requisition approved by %s.') % (self.env.user.display_name,),
                    subtype_xmlid='mail.mt_comment',
                )
            rec.action_generate_job_positions()

    def action_reject(self):
        for rec in self:
            if not self.env.user.has_group('hr.group_hr_manager'):
                raise AccessError(_('Only an HR manager can reject this requisition.'))
            rec.state = 'rejected'
            rec.message_post(
                body=_('Manpower requisition rejected by %s.') % (self.env.user.display_name,),
                subtype_xmlid='mail.mt_comment',
            )

    def action_reset_to_draft(self):
        for rec in self:
            linked_jobs = rec.line_ids.mapped('job_id')
            if linked_jobs:
                linked_jobs.write({
                    'no_of_recruitment': 0,
                    'vacancy_state': 'open',
                    'vacancy_closed_by': False,
                    'vacancy_closed_on': False,
                })
            for line in rec.line_ids:
                line.job_id = False
                line.approved_count = 0
            rec.job_id = False
        self.write({'state': 'draft'})
        self.message_post(
            body=_('Manpower requisition reset to draft by %s.') % (self.env.user.display_name,),
            subtype_xmlid='mail.mt_comment',
        )

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self.message_post(
            body=_('Manpower requisition cancelled by %s.') % (self.env.user.display_name,),
            subtype_xmlid='mail.mt_comment',
        )

    def action_generate_job_positions(self):
        HrJob = self.env['hr.job']
        for rec in self:
            rec._validate_requisition()
            for line in rec.line_ids:
                if line.approved_count <= 0:
                    continue
                job_name = line.designation or rec.department_id.name or rec.name
                job = line.job_id or HrJob.search([
                    ('name', '=', job_name),
                    ('company_id', '=', rec.company_id.id),
                    ('department_id', '=', rec.department_id.id),
                    ('attendance_category', '=', rec.request_type),
                ], limit=1)
                requirements = []
                if line.trade_skill:
                    requirements.append(_("Trade / Skill: %s") % line.trade_skill)
                if line.qualification:
                    requirements.append(_("Qualification: %s") % line.qualification)
                if line.experience_years:
                    requirements.append(_("Experience: %s years") % line.experience_years)
                if line.shift_requirement:
                    requirements.append(_("Shift: %s") % line.shift_requirement)
                if line.technical_skills:
                    requirements.append(_("Technical Skills: %s") % line.technical_skills)
                if line.expected_joining_date:
                    requirements.append(_("Expected Joining Date: %s") % line.expected_joining_date)
                if rec.justification:
                    requirements.append(_("Justification: %s") % rec.justification)

                job = HrJob.search([
                    ('name', '=', job_name),
                    ('company_id', '=', rec.company_id.id),
                    ('department_id', '=', rec.department_id.id),
                    ('attendance_category', '=', rec.request_type),
                ], limit=1)
                job_values = {
                    'name': job_name,
                    'company_id': rec.company_id.id,
                    'department_id': rec.department_id.id,
                    'no_of_recruitment': line.approved_count,
                    'requirements': "\n".join(requirements) if requirements else False,
                    'attendance_category': rec.request_type,
                    'vacancy_state': 'open',
                }
                if job:
                    job.write(job_values)
                else:
                    job = HrJob.create(job_values)
                line.job_id = job.id
                if not rec.job_id:
                    rec.job_id = job.id

    def _validate_partial_approval(self):
        for rec in self:
            if any(line.approved_count < 0 for line in rec.line_ids):
                raise ValidationError(_('Approved so far cannot be negative.'))
            if any(line.approved_count > line.required_count for line in rec.line_ids):
                raise ValidationError(_('Approved count cannot be greater than requested count on any line.'))
            if not any(line.approved_count > 0 for line in rec.line_ids):
                raise ValidationError(_('Please approve at least one position before confirming.'))

    def action_open_generated_jobs(self):
        self.ensure_one()
        job_ids = self.line_ids.mapped('job_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generated Job Positions'),
            'res_model': 'hr.job',
            'view_mode': 'list,form',
            'domain': [('id', 'in', job_ids)],
            'context': {'default_attendance_category': self.request_type},
            'target': 'current',
        }


class ManpowerRequisitionLine(models.Model):
    _name = 'manpower.requisition.line'
    _description = 'Manpower Requisition Line'
    _order = 'id asc'

    requisition_id = fields.Many2one('manpower.requisition', string='Requisition', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='requisition_id.company_id', store=True, readonly=True)
    request_type = fields.Selection(related='requisition_id.request_type', store=True, readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True, copy=False)
    designation = fields.Char(string='Designation', required=True)
    required_count = fields.Integer(string='No. of Persons', default=1, required=True)
    approved_count = fields.Integer(
        string='Approved so far',
        default=0,
        help='How many people have been approved so far for this line.',
    )
    trade_skill = fields.Char(string='Trade / Skill')
    qualification = fields.Char(string='Qualification')
    experience_years = fields.Float(string='Experience (Years)')
    shift_requirement = fields.Char(string='Shift Requirement')
    expected_joining_date = fields.Date(string='Expected Joining Date')
    technical_skills = fields.Char(string='Technical / Functional Skills')
    remarks = fields.Text(string='Remarks')

    @api.onchange('required_count')
    def _onchange_required_count(self):
        for line in self:
            if line.approved_count < 0:
                line.approved_count = 0
            if line.approved_count > line.required_count:
                line.approved_count = line.required_count

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('approved_count') is None:
                vals['approved_count'] = 0
        return super().create(vals_list)

    def write(self, vals):
        return super().write(vals)

    @api.constrains('request_type', 'trade_skill', 'qualification', 'shift_requirement', 'technical_skills', 'approved_count', 'required_count')
    def _check_required_fields_by_type(self):
        for line in self:
            if line.approved_count < 0:
                raise ValidationError(_('Approved so far cannot be negative.'))
            if line.approved_count > line.required_count:
                raise ValidationError(_('Approved count cannot be greater than requested count.'))
            if line.request_type == 'worker':
                missing = []
                if not line.trade_skill:
                    missing.append(_('Trade / Skill'))
                if not line.shift_requirement:
                    missing.append(_('Shift Requirement'))
                if missing:
                    raise ValidationError(_(
                        'Worker requisition lines require the following fields: %s.'
                    ) % ', '.join(missing))

            if line.request_type == 'office':
                missing = []
                if not line.qualification:
                    missing.append(_('Qualification'))
                if not line.technical_skills:
                    missing.append(_('Technical / Functional Skills'))
                if missing:
                    raise ValidationError(_(
                        'Office requisition lines require the following fields: %s.'
                    ) % ', '.join(missing))
