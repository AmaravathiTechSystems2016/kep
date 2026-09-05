# -*- coding: utf-8 -*-
#############################################################################
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import api, fields, models


class ResUsers(models.Model):
    """ Inherited class of res user to override the create function"""
    _inherit = 'res.users'

    employee_id = fields.Many2one('hr.employee',
                                  string='Related Employee',
                                  ondelete='restrict', auto_join=True,
                                  help='Related employee based on the'
                                       ' data of the user')

    @api.model_create_multi
    def create(self, vals_list):
        """Create an employee only for standalone user creation.

        When a user is created from an existing employee, HR already links the
        new user back to that employee through `create_employee_id`. Creating a
        second employee here would violate the unique employee/user constraint
        in the same company.
        """
        results = super().create(vals_list)
        for user, vals in zip(results, vals_list):
            # HR user creation already knows which employee should receive the
            # new user. Do not create a second employee in that flow.
            if vals.get('create_employee_id') or vals.get('create_employee') or self.env.context.get('default_create_employee_id'):
                continue

            if user.employee_ids:
                user.employee_id = user.employee_ids[0]
                continue

            employee = self.env['hr.employee'].sudo().create({
                'name': user.name,
                'user_id': user.id,
                'private_street': user.partner_id.id,
            })
            user.employee_id = employee
        return results
