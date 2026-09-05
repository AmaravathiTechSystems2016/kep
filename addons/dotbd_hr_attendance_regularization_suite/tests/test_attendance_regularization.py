# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestAttendanceRegularization(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Employee = cls.env['hr.employee'].sudo()
        cls.Attendance = cls.env['hr.attendance'].sudo()
        cls.Request = cls.env['attendance.regularization.request'].sudo()
        cls.company = cls.env.company
        cls.employee = cls.Employee.create({
            'name': 'Regularization Employee',
            'company_id': cls.company.id,
        })

    def test_reject_does_not_change_attendance(self):
        attendance = self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': '2026-08-30 09:00:00',
            'check_out': '2026-08-30 18:00:00',
        })

        request = self.Request.create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'request_type': 'both',
            'check_in': '2026-08-30 09:30:00',
            'check_out': '2026-08-30 18:15:00',
            'reason': 'Test rejected correction',
        })
        request.action_reject()

        attendance.invalidate_recordset()
        self.assertEqual(attendance.check_in.strftime('%Y-%m-%d %H:%M:%S'), '2026-08-30 09:00:00')
        self.assertEqual(attendance.check_out.strftime('%Y-%m-%d %H:%M:%S'), '2026-08-30 18:00:00')
        self.assertEqual(request.state, 'rejected')
        self.assertFalse(request.attendance_id)

    def test_second_request_reuses_same_attendance(self):
        first_request = self.Request.create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'request_type': 'missed_check_in',
            'check_in': '2026-08-30 09:10:00',
            'reason': 'First missed check-in',
        })
        first_request.action_approve()

        self.assertTrue(first_request.attendance_id)
        self.assertEqual(self.Attendance.search_count([('employee_id', '=', self.employee.id)]), 1)

        second_request = self.Request.create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'request_type': 'missed_check_out',
            'check_out': '2026-08-30 18:20:00',
            'reason': 'Second missed check-out',
        })
        second_request.action_approve()

        self.assertTrue(second_request.attendance_id)
        self.assertEqual(self.Attendance.search_count([('employee_id', '=', self.employee.id)]), 1)

        attendance = self.Attendance.search([('employee_id', '=', self.employee.id)], limit=1)
        self.assertEqual(attendance.check_in.strftime('%Y-%m-%d %H:%M:%S'), '2026-08-30 09:10:00')
        self.assertEqual(attendance.check_out.strftime('%Y-%m-%d %H:%M:%S'), '2026-08-30 18:20:00')

    def test_duplicate_draft_request_is_blocked(self):
        self.Request.create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'request_type': 'missed_check_in',
            'check_in': '2026-08-30 09:10:00',
            'reason': 'First draft request',
        })
        with self.assertRaises(ValidationError):
            self.Request.create({
                'employee_id': self.employee.id,
                'request_date': '2026-08-30',
                'request_type': 'missed_check_out',
                'check_out': '2026-08-30 18:20:00',
                'reason': 'Duplicate draft request',
            })

    def test_revoke_approval_restores_attendance(self):
        attendance = self.Attendance.create({
            'employee_id': self.employee.id,
            'check_in': '2026-08-30 09:00:00',
            'check_out': '2026-08-30 18:00:00',
        })
        request = self.Request.create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'request_type': 'both',
            'check_in': '2026-08-30 09:20:00',
            'check_out': '2026-08-30 18:10:00',
            'reason': 'Approve by mistake, then revoke',
        })
        request.action_approve()
        request.action_revoke_approval()

        attendance.invalidate_recordset()
        self.assertEqual(attendance.check_in.strftime('%Y-%m-%d %H:%M:%S'), '2026-08-30 09:00:00')
        self.assertEqual(attendance.check_out.strftime('%Y-%m-%d %H:%M:%S'), '2026-08-30 18:00:00')
        self.assertEqual(request.state, 'rejected')
        self.assertFalse(request.attendance_id)
