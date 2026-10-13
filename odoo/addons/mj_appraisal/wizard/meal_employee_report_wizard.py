from odoo import models, fields
from odoo.exceptions import UserError


class MealEmployeeReportWizard(models.TransientModel):
    _name = 'meal.employee.report.wizard'
    _description = 'Meal Employee Report Wizard'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)

    def action_calculate(self):
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError("Invalid date range.")

        cr = self.env.cr

        cr.execute("DROP VIEW IF EXISTS meal_employee_report")

        cr.execute("""
            CREATE OR REPLACE VIEW meal_employee_report AS (
                WITH package_expense AS (
                    SELECT
                        me.meal_package_id,
                        SUM(me.amount) AS total_amount
                    FROM meal_expanse me
                    WHERE me.date BETWEEN %s AND %s
                    GROUP BY me.meal_package_id
                ),
                package_meal AS (
                    SELECT
                        mp.id AS meal_package_id,
                        SUM(md.number_of_meal * mt.weightage) AS total_weighted_meal
                    FROM meal_daily md
                    JOIN meal_type mt ON mt.id = md.meal_type_id
                    JOIN meal_package mp ON mp.id = mt.meal_package_id
                    WHERE md.date BETWEEN %s AND %s
                    GROUP BY mp.id
                ),
                package_rate AS (
                    SELECT
                        pe.meal_package_id,
                        pe.total_amount / NULLIF(pm.total_weighted_meal, 0) AS meal_rate
                    FROM package_expense pe
                    JOIN package_meal pm
                        ON pm.meal_package_id = pe.meal_package_id
                )
                SELECT
                    row_number() OVER () AS id,
                    e.id AS employee_id,
                    e.prefix_id AS emp_id,
                    e.sequence AS sequence,
                    d.name AS department_name,
                    j.name AS designation,
                    SUM(md.number_of_meal_weightage) AS total_meal,
                    COALESCE(pr.meal_rate, 0) AS meal_rate,
                    SUM(md.number_of_meal_weightage * COALESCE(pr.meal_rate, 0)) AS total_bill
                FROM meal_daily md
                JOIN meal_type mt ON mt.id = md.meal_type_id
                JOIN meal_package mp ON mp.id = mt.meal_package_id
                LEFT JOIN package_rate pr ON pr.meal_package_id = mp.id
                JOIN hr_employee e ON e.id = md.employee_id
                LEFT JOIN hr_department d ON d.id = e.department_id
                LEFT JOIN hr_job j ON j.id = e.job_id
                WHERE md.date BETWEEN %s AND %s
                GROUP BY
                    e.id, e.prefix_id, e.sequence,
                    d.name, j.name, pr.meal_rate
            )
        """, (
            self.date_from, self.date_to,
            self.date_from, self.date_to,
            self.date_from, self.date_to,
        ))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Meal Employee Report',
            'res_model': 'meal.employee.report',
            'view_mode': 'list',
            'target': 'current',
        }
