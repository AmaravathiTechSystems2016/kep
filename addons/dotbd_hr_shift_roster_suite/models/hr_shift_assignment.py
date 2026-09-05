# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrShiftAssignment(models.Model):
    _name = 'hr.shift.assignment'
    _description = 'Shift Assignment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, date_from desc, id desc'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one('hr.employee', tracking=True)
    department_id = fields.Many2one('hr.department', tracking=True)
    attendance_category = fields.Selection([
        ('all', 'All'),
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], string='Employee Category', default='all', tracking=True)
    shift_template_id = fields.Many2one(
        'hr.shift.template', required=True, tracking=True, ondelete='restrict')
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    priority = fields.Integer(default=10, tracking=True)
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')
    conflict_count = fields.Integer(compute='_compute_conflict_metrics')
    conflict_warning = fields.Text(compute='_compute_conflict_metrics')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('End date must be greater than or equal to start date.'))

    @api.constrains('employee_id', 'department_id')
    def _check_target(self):
        for rec in self:
            if not rec.employee_id and not rec.department_id and rec.attendance_category == 'all':
                raise ValidationError(_(
                    'Please set at least one target: employee, department, or employee category.'))

    @api.constrains('company_id', 'employee_id', 'department_id', 'attendance_category', 'date_from', 'date_to', 'active')
    def _check_overlap(self):
        """Avoid overlapping assignments that target the same scope.

        This keeps roster generation predictable when multiple assignment
        records exist for the same employee / department / category.
        """
        for rec in self.filtered(lambda r: r.active and r.date_from and r.date_to):
            domain = [
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('active', '=', True),
                ('date_from', '<=', rec.date_to),
                ('date_to', '>=', rec.date_from),
            ]
            if rec.employee_id:
                domain.append(('employee_id', '=', rec.employee_id.id))
            elif rec.department_id and rec.attendance_category != 'all':
                domain.extend([
                    ('department_id', '=', rec.department_id.id),
                    ('attendance_category', '=', rec.attendance_category),
                ])
            elif rec.department_id:
                domain.append(('department_id', '=', rec.department_id.id))
            elif rec.attendance_category != 'all':
                domain.append(('attendance_category', '=', rec.attendance_category))

            if self.search_count(domain):
                raise ValidationError(_(
                    'Overlapping shift assignments are not allowed for the same employee, department, or category scope.'
                ))

    def _get_conflict_domain(self):
        self.ensure_one()
        domain = [
            ('id', '!=', self.id),
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
        ]
        return domain

    def _conflicts_with_assignment(self, other):
        """Return whether two assignments overlap in time and target the same population."""
        self.ensure_one()
        other.ensure_one()
        if self.company_id != other.company_id:
            return False
        if self.date_from > other.date_to or self.date_to < other.date_from:
            return False
        return self._assignment_conflicts_with(other) or other._assignment_conflicts_with(self)

    def _assignment_conflicts_with(self, other):
        """Return True when another assignment can affect the same employee set."""
        self.ensure_one()
        other.ensure_one()

        if self.employee_id:
            if other.employee_id and other.employee_id == self.employee_id:
                return True
            if other.department_id and self.employee_id.department_id and other.department_id == self.employee_id.department_id:
                return True
            if other.attendance_category in ('all', self.employee_id.attendance_category or 'other'):
                return True
            return False

        if self.department_id:
            if other.employee_id and other.employee_id.department_id == self.department_id:
                return True
            if other.department_id and other.department_id == self.department_id:
                return True
            if other.attendance_category in ('all', self.attendance_category):
                return True
            return False

        if self.attendance_category != 'all':
            if other.employee_id and (other.employee_id.attendance_category or 'other') == self.attendance_category:
                return True
            if other.department_id and other.attendance_category in ('all', self.attendance_category):
                return True
            if other.attendance_category in ('all', self.attendance_category):
                return True
            return False

        return bool(other.employee_id or other.department_id or other.attendance_category != 'all')

    @api.depends('company_id', 'employee_id', 'department_id', 'attendance_category', 'date_from', 'date_to', 'active')
    def _compute_conflict_metrics(self):
        for rec in self:
            rec.conflict_count = 0
            rec.conflict_warning = False
            if not rec.active or not rec.company_id or not rec.date_from or not rec.date_to:
                continue

            conflicts = rec.search(rec._get_conflict_domain())
            conflicts = conflicts.filtered(rec._assignment_conflicts_with)
            rec.conflict_count = len(conflicts)
            if conflicts:
                sample = ', '.join(conflicts[:3].mapped('name'))
                if len(conflicts) > 3:
                    sample = _('%s and %s more') % (sample, len(conflicts) - 3)
                rec.conflict_warning = _(
                    'This assignment overlaps with other assignment rules that may also apply: %s'
                ) % sample

    @api.model
    def get_conflicting_assignment_ids(self, assignments):
        """Return assignment ids that conflict with another assignment in the set."""
        conflict_ids = set()
        assignments = assignments.filtered(lambda rec: rec.active and rec.company_id and rec.date_from and rec.date_to)
        ordered = assignments.sorted(lambda rec: (
            rec.company_id.id,
            rec.date_from,
            rec.date_to,
            -(rec.priority or 0),
            rec.id,
        ))
        ordered_list = list(ordered)
        for index, assignment in enumerate(ordered_list):
            for other in ordered_list[index + 1:]:
                if assignment.company_id != other.company_id:
                    continue
                if assignment.date_from > other.date_to:
                    continue
                if assignment.date_to < other.date_from:
                    continue
                if assignment._assignment_conflicts_with(other):
                    conflict_ids.add(assignment.id)
                    conflict_ids.add(other.id)
        return list(conflict_ids)

    def action_open_conflicts(self):
        self.ensure_one()
        conflicts = self.search(self._get_conflict_domain()).filtered(self._assignment_conflicts_with)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assignment Conflicts'),
            'res_model': 'hr.shift.assignment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', conflicts.ids)],
        }

    def _matches_employee(self, employee, current_date):
        """Return whether this assignment applies to the given employee on the date."""
        self.ensure_one()
        if not employee or not current_date:
            return False
        if not self.active:
            return False
        if self.company_id and self.company_id != employee.company_id:
            return False
        if self.date_from and current_date < self.date_from:
            return False
        if self.date_to and current_date > self.date_to:
            return False
        if self.employee_id and self.employee_id != employee:
            return False
        if self.department_id and self.department_id != employee.department_id:
            return False
        employee_category = employee.attendance_category or 'other'
        if self.attendance_category not in ('all', employee_category):
            return False
        return True

    def _match_rank(self, employee, current_date):
        """Return a ranking tuple for the best assignment match.

        Higher tuples win. The order is:
        1. employee-specific assignments,
        2. department assignments,
        3. category assignments,
        4. higher priority,
        5. later start date,
        6. latest record.
        """
        self.ensure_one()
        specificity = 0
        if self.employee_id:
            specificity += 4
        if self.department_id:
            specificity += 2
        if self.attendance_category != 'all':
            specificity += 1
        priority = self.priority or 0
        date_from_value = self.date_from.toordinal() if self.date_from else 0
        date_to_value = self.date_to.toordinal() if self.date_to else 0
        return (specificity, priority, date_from_value, date_to_value, self.id)
