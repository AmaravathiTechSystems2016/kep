# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_DAY_CODE_BY_WEEKDAY = {
    0: 'mon',
    1: 'tue',
    2: 'wed',
    3: 'thu',
    4: 'fri',
    5: 'sat',
    6: 'sun',
}


class HrShiftRoster(models.Model):
    _name = 'hr.shift.roster'
    _description = 'Shift Roster'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char(required=True, default='New', tracking=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, tracking=True)
    department_id = fields.Many2one('hr.department', tracking=True)
    attendance_category = fields.Selection([
        ('all', 'All'),
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], string='Employee Category', default='all', tracking=True)
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)
    line_ids = fields.One2many('hr.shift.roster.line', 'roster_id', string='Roster Lines')
    line_count = fields.Integer(compute='_compute_line_count')
    revision_ids = fields.One2many('hr.shift.roster.revision', 'roster_id', string='History')
    revision_count = fields.Integer(compute='_compute_revision_count')
    note = fields.Text(string='Notes')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends('revision_ids')
    def _compute_revision_count(self):
        for rec in self:
            rec.revision_count = len(rec.revision_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('End date must be greater than or equal to start date.'))

    @api.constrains('company_id', 'department_id', 'attendance_category', 'date_from', 'date_to', 'state')
    def _check_overlap(self):
        """Prevent duplicate roster plans for the same scope and period."""
        for rec in self.filtered(lambda r: r.date_from and r.date_to and r.state != 'cancelled'):
            domain = [
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('state', '!=', 'cancelled'),
                ('date_from', '<=', rec.date_to),
                ('date_to', '>=', rec.date_from),
            ]
            if rec.department_id:
                domain.append(('department_id', '=', rec.department_id.id))
            if rec.attendance_category and rec.attendance_category != 'all':
                domain.append(('attendance_category', '=', rec.attendance_category))

            if self.search_count(domain):
                raise ValidationError(_(
                    'Another shift roster already exists for the same company, department/category, and overlapping dates.'
                ))

    def action_generate_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        self._generate_lines()
        self._create_revision_snapshot('generated', _('Generated roster lines'))
        self.state = 'generated'
        return True

    def action_rebuild_lines(self):
        self.ensure_one()
        self._create_revision_snapshot('rebuilt', _('Before rebuild'))
        self.line_ids.unlink()
        self._generate_lines()
        self._create_revision_snapshot('rebuilt', _('After rebuild'))
        self.state = 'generated'
        return True

    def action_open_bulk_update_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bulk Update Roster Lines'),
            'res_model': 'hr.shift.roster.bulk.update.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_roster_id': self.id,
            },
        }

    def action_open_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Roster History'),
            'res_model': 'hr.shift.roster.revision',
            'view_mode': 'list,form',
            'domain': [('roster_id', '=', self.id)],
            'context': {'default_roster_id': self.id},
        }

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.shift.roster') or 'New'
        return super().create(vals_list)

    def _get_target_employees(self):
        self.ensure_one()
        domain = [('active', '=', True)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.attendance_category and self.attendance_category != 'all':
            domain.append(('attendance_category', '=', self.attendance_category))
        return self.env['hr.employee'].search(domain, order='department_id, name')

    def _get_applicable_assignment(self, employee, current_date):
        Assignment = self.env['hr.shift.assignment']
        assignments = Assignment.search([
            ('active', '=', True),
            ('date_from', '<=', current_date),
            ('date_to', '>=', current_date),
        ], order='priority desc, date_from desc, id desc')
        matching_assignments = assignments.filtered(
            lambda assignment: assignment._matches_employee(employee, current_date)
        )
        if matching_assignments:
            return max(matching_assignments, key=lambda assignment: assignment._match_rank(employee, current_date))
        return Assignment.browse()

    def _generate_lines(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return
        if self.date_from > self.date_to:
            raise ValidationError(_('Start date must be before end date.'))

        employees = self._get_target_employees()
        current_date = self.date_from
        Line = self.env['hr.shift.roster.line']
        weekday_model = self.env['hr.shift.weekday']
        weekday_cache = {w.code: w for w in weekday_model.search([])}
        holiday_cache = self._get_company_holiday_cache(self.date_from, self.date_to)
        Holiday = self.env['hr.shift.holiday']

        values = []
        while current_date <= self.date_to:
            weekday_code = _DAY_CODE_BY_WEEKDAY[current_date.weekday()]
            weekday_rec = weekday_cache.get(weekday_code)
            for employee in employees:
                assignment = self._get_applicable_assignment(employee, current_date)
                shift_template = assignment._get_rotation_shift_template(current_date) if assignment else employee.default_shift_template_id
                if not shift_template:
                    continue
                holiday_name = Holiday.find_holiday_name(self.company_id, current_date, employee) or holiday_cache.get(current_date)
                values.append({
                    'roster_id': self.id,
                    'date': current_date,
                    'employee_id': employee.id,
                    'department_id': employee.department_id.id,
                    'attendance_category': employee.attendance_category,
                    'shift_template_id': shift_template.id,
                    'is_weekly_off': bool(weekday_rec and weekday_rec in shift_template.weekly_off_day_ids),
                    'is_public_holiday': bool(holiday_name),
                    'holiday_name': holiday_name or False,
                    'notes': assignment.note if assignment else False,
                })
            current_date += timedelta(days=1)

        if values:
            Line.create(values)

    def _get_company_holiday_cache(self, date_from, date_to):
        """Build a simple map of public holiday dates for the roster company.

        The attendance module already owns the broader holiday logic. For the
        roster module we only need the company-level holiday names so that
        generated lines can be flagged in the schedule.
        """
        self.ensure_one()
        calendar = self.company_id.resource_calendar_id
        if not calendar:
            return {}

        holidays = self.env['resource.calendar.leaves'].search([
            ('calendar_id', '=', calendar.id),
            ('resource_id', '=', False),
            ('date_from', '<=', fields.Datetime.to_string(datetime.combine(date_to, time.max))),
            ('date_to', '>=', fields.Datetime.to_string(datetime.combine(date_from, time.min))),
        ])
        holiday_cache = {}
        for holiday in holidays:
            start = fields.Date.to_date(holiday.date_from)
            end = fields.Date.to_date(holiday.date_to)
            current = start
            while current <= end:
                if date_from <= current <= date_to:
                    holiday_cache[current] = holiday.name
                current += timedelta(days=1)
        return holiday_cache

    def _create_revision_snapshot(self, action_type, note=None):
        """Persist a history snapshot of the current roster lines."""
        self.ensure_one()
        revision = self.env['hr.shift.roster.revision'].create({
            'roster_id': self.id,
            'action_type': action_type,
            'note': note,
            'line_count': len(self.line_ids),
        })
        if self.line_ids:
            self.env['hr.shift.roster.revision.line'].create([
                {
                    'revision_id': revision.id,
                    'date': line.date,
                    'employee_id': line.employee_id.id,
                    'department_id': line.department_id.id,
                    'attendance_category': line.attendance_category,
                    'shift_template_id': line.shift_template_id.id,
                    'start_time': line.start_time,
                    'end_time': line.end_time,
                    'break_duration': line.break_duration,
                    'is_weekly_off': line.is_weekly_off,
                    'is_public_holiday': line.is_public_holiday,
                    'holiday_name': line.holiday_name,
                    'notes': line.notes,
                }
                for line in self.line_ids
            ])
        return revision


class HrShiftRosterLine(models.Model):
    _name = 'hr.shift.roster.line'
    _description = 'Shift Roster Line'
    _order = 'date, employee_id'

    roster_id = fields.Many2one('hr.shift.roster', required=True, ondelete='cascade')
    roster_date_from = fields.Date(related='roster_id.date_from', store=True, readonly=True, index=True)
    company_id = fields.Many2one(related='roster_id.company_id', store=True, readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    attendance_category = fields.Selection([
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], readonly=True)
    date = fields.Date(required=True, index=True)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    shift_template_id = fields.Many2one('hr.shift.template', required=True, ondelete='restrict')
    start_time = fields.Float(related='shift_template_id.start_time', readonly=True, store=True)
    end_time = fields.Float(related='shift_template_id.end_time', readonly=True, store=True)
    break_duration = fields.Float(related='shift_template_id.break_duration', readonly=True, store=True)
    is_weekly_off = fields.Boolean(default=False)
    is_public_holiday = fields.Boolean(default=False)
    holiday_name = fields.Char()
    notes = fields.Text()

    _sql_constraints = [
        ('uniq_roster_employee_date', 'unique(roster_id, employee_id, date)',
         'An employee can only have one roster line per day in the same roster.'),
    ]

    @api.model
    def get_planned_line(self, employee, work_date, company_id=None):
        """Return the most relevant roster line for an employee on a given date.

        This helper is used by attendance and reporting code to treat the roster
        as the schedule source of truth whenever one exists.
        """
        if not employee or not work_date:
            return self.browse()

        domain = [
            ('employee_id', '=', employee.id),
            ('date', '=', work_date),
            ('roster_id.state', 'in', ['generated', 'confirmed', 'done']),
        ]
        if company_id:
            company = company_id if hasattr(company_id, 'id') else self.env['res.company'].browse(company_id)
            if company:
                domain.append(('company_id', '=', company.id))

        return self.search(domain, order='roster_date_from desc, roster_id desc, id desc', limit=1)
