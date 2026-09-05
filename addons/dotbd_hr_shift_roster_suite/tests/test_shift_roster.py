# -*- coding: utf-8 -*-

from datetime import date

from odoo.tests.common import TransactionCase


class TestShiftRosterSuite(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.department = self.env['hr.department'].create({
            'name': 'Operations Test',
            'company_id': self.company.id,
        })
        self.worker = self.env['hr.employee'].create({
            'name': 'Roster Worker',
            'company_id': self.company.id,
            'department_id': self.department.id,
            'attendance_category': 'worker',
        })
        self.shift_a = self.env['hr.shift.template'].create({
            'name': 'Shift A Test',
            'company_id': self.company.id,
            'applicable_category': 'worker',
            'start_time': 6.0,
            'end_time': 14.0,
        })
        self.shift_b = self.env['hr.shift.template'].create({
            'name': 'Shift B Test',
            'company_id': self.company.id,
            'applicable_category': 'worker',
            'start_time': 14.0,
            'end_time': 22.0,
        })
        self.shift_general = self.env['hr.shift.template'].create({
            'name': 'General Shift Test',
            'company_id': self.company.id,
            'applicable_category': 'all',
            'start_time': 9.5,
            'end_time': 18.0,
        })

    def test_employee_specific_assignment_wins_over_department_assignment(self):
        roster = self.env['hr.shift.roster'].create({
            'name': 'Roster Specificity',
            'company_id': self.company.id,
            'department_id': self.department.id,
            'attendance_category': 'worker',
            'date_from': date(2026, 8, 1),
            'date_to': date(2026, 8, 1),
        })
        self.env['hr.shift.assignment'].create({
            'name': 'Department Assignment',
            'company_id': self.company.id,
            'department_id': self.department.id,
            'attendance_category': 'worker',
            'shift_template_id': self.shift_general.id,
            'date_from': date(2026, 8, 1),
            'date_to': date(2026, 8, 31),
            'priority': 10,
        })
        employee_assignment = self.env['hr.shift.assignment'].create({
            'name': 'Employee Assignment',
            'company_id': self.company.id,
            'employee_id': self.worker.id,
            'shift_template_id': self.shift_a.id,
            'date_from': date(2026, 8, 1),
            'date_to': date(2026, 8, 31),
            'priority': 1,
        })

        roster.action_generate_lines()
        line = roster.line_ids.filtered(lambda line: line.employee_id == self.worker)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.shift_template_id, self.shift_a)
        self.assertGreaterEqual(employee_assignment.conflict_count, 1)

    def test_rotation_cycle_picks_each_template_in_sequence(self):
        assignment = self.env['hr.shift.assignment'].create({
            'name': 'Rotation Assignment',
            'company_id': self.company.id,
            'department_id': self.department.id,
            'attendance_category': 'worker',
            'shift_template_id': self.shift_general.id,
            'date_from': date(2026, 8, 1),
            'date_to': date(2026, 8, 31),
            'priority': 10,
            'rotation_mode': 'cycle',
            'rotation_start_date': date(2026, 8, 1),
            'rotation_cycle_days': 1,
            'rotation_line_ids': [
                (0, 0, {'sequence': 10, 'shift_template_id': self.shift_a.id}),
                (0, 0, {'sequence': 20, 'shift_template_id': self.shift_b.id}),
            ],
        })
        roster = self.env['hr.shift.roster'].create({
            'name': 'Roster Rotation',
            'company_id': self.company.id,
            'department_id': self.department.id,
            'attendance_category': 'worker',
            'date_from': date(2026, 8, 1),
            'date_to': date(2026, 8, 2),
        })

        roster.action_generate_lines()
        day_one = roster.line_ids.filtered(lambda line: line.date == date(2026, 8, 1))
        day_two = roster.line_ids.filtered(lambda line: line.date == date(2026, 8, 2))

        self.assertEqual(day_one.shift_template_id, self.shift_a)
        self.assertEqual(day_two.shift_template_id, self.shift_b)
        self.assertEqual(assignment.rotation_mode, 'cycle')
