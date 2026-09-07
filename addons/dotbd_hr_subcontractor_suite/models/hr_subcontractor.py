# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrSubcontractor(models.Model):
    _name = 'hr.subcontractor'
    _description = 'HR Subcontractor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(readonly=True, copy=False, default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string='Subcontractor Company', tracking=True)
    contact_name = fields.Char(string='Contact Person')
    phone = fields.Char()
    email = fields.Char()
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        tracking=True,
    )
    department_id = fields.Many2one('hr.department', tracking=True)
    responsible_user_id = fields.Many2one('res.users', string='Responsible HR')
    service_type = fields.Char(string='Service / Work Scope')
    contract_start = fields.Date(string='Contract Start', tracking=True)
    contract_end = fields.Date(string='Contract End', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)
    employee_ids = fields.One2many(
        'hr.employee', 'subcontractor_id', string='Assigned Employees')
    employee_count = fields.Integer(compute='_compute_employee_count')
    notes = fields.Text(string='Notes')

    _code_unique = models.Constraint(
        'UNIQUE(code, company_id)',
        'The subcontractor code must be unique per company.',
    )

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for record in self:
            record.employee_count = len(record.employee_ids)

    @api.constrains('contract_start', 'contract_end')
    def _check_contract_dates(self):
        for record in self:
            if (record.contract_start and record.contract_end
                    and record.contract_end < record.contract_start):
                raise ValidationError(_('Contract End must be after Contract Start.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'hr.subcontractor') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_activate(self):
        self.write({'state': 'active'})
        self.employee_ids.filtered(lambda employee: employee.subcontractor_status == 'assigned').write({
            'subcontractor_status': 'active',
        })

    def action_close(self):
        self.write({'state': 'closed'})
        self.employee_ids.write({'subcontractor_status': 'released'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
