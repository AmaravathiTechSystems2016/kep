from odoo import models, fields, api
from datetime import timedelta
from odoo.exceptions import UserError

class MealDailyWizard(models.TransientModel):
    _name = 'meal.daily.wizard'
    _description = 'Calculate Daily Meal Wizard'

    start_date = fields.Date(
        string="Start Date",
        required=True,
        default=fields.Date.context_today
    )

    end_date = fields.Date(
        string="End Date",
        required=True,
        default=fields.Date.context_today
    )

    meal_group_id = fields.Many2one('meal.group', string='Meal Group')
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Employees'
    )

    def action_calculate(self):
        self.ensure_one()

        if not self.start_date or not self.end_date:
            raise UserError("Please select both Start Date and End Date.")

        if self.start_date > self.end_date:
            raise UserError("Start Date cannot be after End Date.")

        MealDaily = self.env['meal.daily']
        MealAssign = self.env['meal.assign']

        # Active employees (via open contracts)
        contracts = self.env['hr.contract'].sudo().search([
            ('state', '=', 'open')
        ])

        if self.employee_ids:
            contracts = contracts.filtered(
                lambda c: c.employee_id in self.employee_ids
            )

        employees = contracts.mapped('employee_id')

        # Filter by meal group (if selected)
        if self.meal_group_id:
            employees = employees.filtered(lambda e:
                MealAssign.search_count([
                    ('employee_id', '=', e.id),
                    ('meal_group_id', '=', self.meal_group_id.id),
                ])
            )

        current_date = self.start_date

        while current_date <= self.end_date:
            for emp in employees:
                assigned = MealAssign.search([
                    ('employee_id', '=', emp.id)
                ], limit=1)

                if not assigned or not assigned.meal_type_ids:
                    continue

                # Enforce meal group match
                if self.meal_group_id and assigned.meal_group_id != self.meal_group_id:
                    continue

                for meal_type in assigned.meal_type_ids:
                    exists = MealDaily.search_count([
                        ('date', '=', current_date),
                        ('employee_id', '=', emp.id),
                        ('meal_type_id', '=', meal_type.id),
                    ])

                    if exists:
                        continue

                    MealDaily.create({
                        'date': current_date,
                        'employee_id': emp.id,
                        'meal_type_id': meal_type.id,
                        'number_of_meal': 1,
                    })

            current_date += timedelta(days=1)