# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrOnboardingTemplate(models.Model):
    _name = 'hr.onboarding.template'
    _description = 'HR Onboarding Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, id desc'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        tracking=True,
    )
    employee_category = fields.Selection(
        [
            ('common', 'Common'),
            ('worker', 'Manufacturing Worker'),
            ('office', 'Office Staff'),
            ('other', 'Other'),
        ],
        string='Employee Category',
        default='common',
        required=True,
        tracking=True,
    )
    description = fields.Html()
    line_ids = fields.One2many('hr.onboarding.template.line', 'template_id', string='Template Steps', copy=True)
    line_count = fields.Integer(compute='_compute_line_count')

    def _compute_line_count(self):
        for template in self:
            template.line_count = len(template.line_ids)

    @api.model
    def get_template_for_category(self, employee_category, company_id=False):
        """Return the most specific active template for an employee category."""
        category = employee_category or 'common'
        template = self.search([
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company_id),
            ('employee_category', '=', category),
        ], order='id desc', limit=1)
        if template:
            return template
        return self.search([
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company_id),
            ('employee_category', '=', 'common'),
        ], order='id desc', limit=1)


class HrOnboardingTemplateLine(models.Model):
    _name = 'hr.onboarding.template.line'
    _description = 'HR Onboarding Template Step'
    _order = 'sequence, id'

    template_id = fields.Many2one('hr.onboarding.template', required=True, ondelete='cascade')
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
    responsible_role = fields.Char(string='Responsible Role')
    duration_days = fields.Integer(string='Target Days')
    notes = fields.Text()
