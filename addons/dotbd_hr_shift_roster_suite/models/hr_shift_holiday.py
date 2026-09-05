# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrShiftHoliday(models.Model):
    _name = 'hr.shift.holiday'
    _description = 'Shift Holiday Master'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, tracking=True)
    department_id = fields.Many2one('hr.department', tracking=True)
    attendance_category = fields.Selection([
        ('all', 'All'),
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], string='Employee Category', default='all', tracking=True)
    holiday_type = fields.Selection([
        ('public', 'Public Holiday'),
        ('festival', 'Festival Leave'),
        ('plant', 'Plant Holiday'),
    ], default='public', tracking=True)
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    note = fields.Text(string='Notes')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('Holiday end date must be greater than or equal to start date.'))

    @api.constrains('company_id', 'department_id', 'attendance_category', 'date_from', 'date_to', 'active')
    def _check_overlap(self):
        for rec in self.filtered(lambda r: r.active and r.date_from and r.date_to):
            domain = [
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('active', '=', True),
                ('date_from', '<=', rec.date_to),
                ('date_to', '>=', rec.date_from),
            ]
            if rec.department_id:
                domain.append(('department_id', '=', rec.department_id.id))
            if rec.attendance_category and rec.attendance_category != 'all':
                domain.append(('attendance_category', '=', rec.attendance_category))

            if self.search_count(domain):
                raise ValidationError(_(
                    'Another holiday already exists for the same scope and overlapping dates.'
                ))

    @api.model
    def find_holiday_name(self, company_id, current_date, employee=None):
        """Return the best matching holiday name for a company/date/employee scope."""
        if not company_id or not current_date:
            return False

        domain = [
            ('company_id', '=', company_id.id if hasattr(company_id, 'id') else company_id),
            ('active', '=', True),
            ('date_from', '<=', current_date),
            ('date_to', '>=', current_date),
        ]
        if employee and getattr(employee, 'department_id', False):
            holiday = self.search(domain + [
                ('department_id', '=', employee.department_id.id),
                ('attendance_category', '=', getattr(employee, 'attendance_category', 'other') or 'other'),
            ], order='date_from desc, id desc', limit=1)
            if holiday:
                return holiday.name

            holiday = self.search(domain + [('department_id', '=', employee.department_id.id)], order='date_from desc, id desc', limit=1)
            if holiday:
                return holiday.name

        if employee:
            att_cat = getattr(employee, 'attendance_category', 'other') or 'other'
            holiday = self.search(domain + [('attendance_category', '=', att_cat)], order='date_from desc, id desc', limit=1)
            if holiday:
                return holiday.name

        holiday = self.search(domain, order='date_from desc, id desc', limit=1)
        return holiday.name if holiday else False
