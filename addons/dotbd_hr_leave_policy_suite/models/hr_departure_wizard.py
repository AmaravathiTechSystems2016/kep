# -*- coding: utf-8 -*-

from odoo import models


class HrDepartureWizard(models.TransientModel):
    _inherit = 'hr.departure.wizard'

    def action_register_departure(self):
        action = super().action_register_departure()
        employees = self.employee_ids.filtered(lambda emp: emp.leave_policy_id)
        if not employees:
            return action
        policies = employees.mapped('leave_policy_id')
        for policy in policies:
            policy_employees = employees.filtered(lambda emp: emp.leave_policy_id == policy)
            policy.action_generate_exit_encashments(policy_employees, self.departure_date)
        return action
