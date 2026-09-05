# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.osv import expression


class HrShiftPlanningDashboard(models.TransientModel):
    _name = 'hr.shift.planning.dashboard'
    _description = 'Shift Planning Dashboard'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    department_id = fields.Many2one('hr.department', string='Department')
    attendance_category = fields.Selection([
        ('all', 'All'),
        ('worker', 'Manufacturing Worker'),
        ('office', 'Office Staff'),
        ('other', 'Other'),
    ], default='all', string='Employee Category')

    roster_count = fields.Integer(compute='_compute_dashboard_metrics')
    draft_roster_count = fields.Integer(compute='_compute_dashboard_metrics')
    generated_roster_count = fields.Integer(compute='_compute_dashboard_metrics')
    confirmed_roster_count = fields.Integer(compute='_compute_dashboard_metrics')
    done_roster_count = fields.Integer(compute='_compute_dashboard_metrics')
    assignment_count = fields.Integer(compute='_compute_dashboard_metrics')
    rotation_assignment_count = fields.Integer(compute='_compute_dashboard_metrics')
    conflicting_assignment_count = fields.Integer(compute='_compute_dashboard_metrics')
    template_count = fields.Integer(compute='_compute_dashboard_metrics')
    roster_line_count = fields.Integer(compute='_compute_dashboard_metrics')
    weekly_off_line_count = fields.Integer(compute='_compute_dashboard_metrics')
    public_holiday_line_count = fields.Integer(compute='_compute_dashboard_metrics')
    exception_line_count = fields.Integer(compute='_compute_dashboard_metrics')
    active_employee_count = fields.Integer(compute='_compute_dashboard_metrics')

    @api.depends('company_id', 'date_from', 'date_to', 'department_id', 'attendance_category')
    def _compute_dashboard_metrics(self):
        Roster = self.env['hr.shift.roster']
        Assignment = self.env['hr.shift.assignment']
        Template = self.env['hr.shift.template']
        Employee = self.env['hr.employee']
        Line = self.env['hr.shift.roster.line']

        for rec in self:
            roster_domain = [('company_id', '=', rec.company_id.id)]
            assignment_domain = [('company_id', '=', rec.company_id.id)]
            employee_domain = [('company_id', '=', rec.company_id.id), ('active', '=', True)]
            line_domain = [('company_id', '=', rec.company_id.id)]
            template_domain = [('company_id', '=', rec.company_id.id)]

            if rec.department_id:
                roster_domain.append(('department_id', '=', rec.department_id.id))
                assignment_domain.append(('department_id', '=', rec.department_id.id))
                employee_domain.append(('department_id', '=', rec.department_id.id))
                line_domain.append(('department_id', '=', rec.department_id.id))
            if rec.attendance_category and rec.attendance_category != 'all':
                roster_domain.append(('attendance_category', '=', rec.attendance_category))
                assignment_domain.append(('attendance_category', '=', rec.attendance_category))
                employee_domain.append(('attendance_category', '=', rec.attendance_category))
                line_domain.append(('attendance_category', '=', rec.attendance_category))
                template_domain.append(('applicable_category', 'in', ('all', rec.attendance_category)))

            if rec.date_from:
                roster_domain.append(('date_from', '>=', rec.date_from))
                assignment_domain.append(('date_from', '>=', rec.date_from))
                line_domain.append(('date', '>=', rec.date_from))
            if rec.date_to:
                roster_domain.append(('date_to', '<=', rec.date_to))
                assignment_domain.append(('date_to', '<=', rec.date_to))
                line_domain.append(('date', '<=', rec.date_to))

            rec.roster_count = Roster.search_count(roster_domain)
            rec.draft_roster_count = Roster.search_count(roster_domain + [('state', '=', 'draft')])
            rec.generated_roster_count = Roster.search_count(roster_domain + [('state', '=', 'generated')])
            rec.confirmed_roster_count = Roster.search_count(roster_domain + [('state', '=', 'confirmed')])
            rec.done_roster_count = Roster.search_count(roster_domain + [('state', '=', 'done')])
            assignments = Assignment.search(assignment_domain + [('active', '=', True)])
            rec.assignment_count = len(assignments)
            rec.rotation_assignment_count = len(assignments.filtered(lambda assignment: assignment.rotation_mode == 'cycle'))
            rec.conflicting_assignment_count = len(Assignment.browse(
                Assignment.get_conflicting_assignment_ids(assignments)
            ))
            rec.template_count = Template.search_count(template_domain + [('active', '=', True)])
            rec.roster_line_count = Line.search_count(line_domain)
            rec.weekly_off_line_count = Line.search_count(line_domain + [('is_weekly_off', '=', True)])
            rec.public_holiday_line_count = Line.search_count(line_domain + [('is_public_holiday', '=', True)])
            rec.exception_line_count = rec.weekly_off_line_count + rec.public_holiday_line_count
            rec.active_employee_count = Employee.search_count(employee_domain)

    def action_open_rosters(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.attendance_category and self.attendance_category != 'all':
            domain.append(('attendance_category', '=', self.attendance_category))
        if self.date_from:
            domain.append(('date_from', '>=', self.date_from))
        if self.date_to:
            domain.append(('date_to', '<=', self.date_to))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shift Rosters'),
            'res_model': 'hr.shift.roster',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_open_assignments(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.attendance_category and self.attendance_category != 'all':
            domain.append(('attendance_category', '=', self.attendance_category))
        if self.date_from:
            domain.append(('date_from', '>=', self.date_from))
        if self.date_to:
            domain.append(('date_to', '<=', self.date_to))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shift Assignments'),
            'res_model': 'hr.shift.assignment',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_open_conflicting_assignments(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id), ('active', '=', True)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.attendance_category and self.attendance_category != 'all':
            domain.append(('attendance_category', '=', self.attendance_category))
        if self.date_from:
            domain.append(('date_from', '<=', self.date_to or self.date_from))
        if self.date_to:
            domain.append(('date_to', '>=', self.date_from or self.date_to))
        assignments = self.env['hr.shift.assignment'].search(domain)
        conflict_ids = self.env['hr.shift.assignment'].get_conflicting_assignment_ids(assignments)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Conflicting Assignments'),
            'res_model': 'hr.shift.assignment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', conflict_ids)],
        }

    def action_open_exception_lines(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.attendance_category and self.attendance_category != 'all':
            domain.append(('attendance_category', '=', self.attendance_category))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        domain = expression.AND([domain, expression.OR([[('is_weekly_off', '=', True)], [('is_public_holiday', '=', True)]])])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Roster Exceptions'),
            'res_model': 'hr.shift.roster.line',
            'view_mode': 'list,form',
            'domain': domain,
        }

    def action_refresh(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shift Planning Dashboard'),
            'res_model': 'hr.shift.planning.dashboard',
            'view_mode': 'form',
            'target': 'current',
            'res_id': self.id,
        }
