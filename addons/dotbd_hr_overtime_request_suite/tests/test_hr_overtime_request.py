# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestHrOvertimeRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Manual OT Employee',
            'company_id': cls.company.id,
            'attendance_category': 'worker',
        })
        cls.internal_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'OT Internal User',
            'login': 'ot.internal.user@example.com',
            'email': 'ot.internal.user@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_request_lifecycle(self):
        request = self.env['hr.overtime.request'].create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'overtime_date': '2026-08-30',
            'requested_hours': 2.0,
            'reason': 'Production support',
        })
        self.assertEqual(request.state, 'draft')
        request.action_submit()
        self.assertEqual(request.state, 'submitted')
        request.sudo().action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertEqual(request.approved_hours, 2.0)
        request.sudo().action_revoke_approval()
        self.assertEqual(request.state, 'submitted')

    def test_duplicate_request_blocked(self):
        self.env['hr.overtime.request'].create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'overtime_date': '2026-08-30',
            'requested_hours': 1.0,
            'reason': 'First request',
        })
        with self.assertRaises(ValidationError):
            self.env['hr.overtime.request'].create({
                'employee_id': self.employee.id,
                'request_date': '2026-08-30',
                'overtime_date': '2026-08-30',
                'requested_hours': 1.5,
                'reason': 'Duplicate request',
            })

    def test_reject_requires_hr(self):
        request = self.env['hr.overtime.request'].create({
            'employee_id': self.employee.id,
            'request_date': '2026-08-30',
            'overtime_date': '2026-08-30',
            'requested_hours': 1.0,
            'reason': 'Need manager decision',
        })
        with self.assertRaises(UserError):
            request.with_user(self.internal_user).action_reject()
