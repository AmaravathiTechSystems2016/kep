# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrShiftRosterBulkUpdateWizard(models.TransientModel):
    _name = 'hr.shift.roster.bulk.update.wizard'
    _description = 'Bulk Update Shift Roster Lines'

    roster_id = fields.Many2one('hr.shift.roster', required=True, readonly=True)
    line_date_from = fields.Date(string='Date From')
    line_date_to = fields.Date(string='Date To')
    shift_template_id = fields.Many2one('hr.shift.template', string='Shift Template')
    is_weekly_off = fields.Selection([
        ('keep', 'Keep'),
        ('yes', 'Set Yes'),
        ('no', 'Set No'),
    ], default='keep', string='Weekly Off')
    is_public_holiday = fields.Selection([
        ('keep', 'Keep'),
        ('yes', 'Set Yes'),
        ('no', 'Set No'),
    ], default='keep', string='Public Holiday')
    holiday_name = fields.Char(string='Holiday Name')
    notes = fields.Text(string='Notes')

    def action_apply(self):
        self.ensure_one()
        if not self.roster_id:
            raise ValidationError(_('Please choose a roster first.'))

        domain = [('roster_id', '=', self.roster_id.id)]
        if self.line_date_from:
            domain.append(('date', '>=', self.line_date_from))
        if self.line_date_to:
            domain.append(('date', '<=', self.line_date_to))

        lines = self.env['hr.shift.roster.line'].search(domain)
        if not lines:
            return {'type': 'ir.actions.act_window_close'}

        values = {}
        if self.shift_template_id:
            values['shift_template_id'] = self.shift_template_id.id
        if self.is_weekly_off != 'keep':
            values['is_weekly_off'] = self.is_weekly_off == 'yes'
        if self.is_public_holiday != 'keep':
            values['is_public_holiday'] = self.is_public_holiday == 'yes'
        if self.holiday_name is not False and self.holiday_name is not None:
            values['holiday_name'] = self.holiday_name
        if self.notes is not False and self.notes is not None:
            values['notes'] = self.notes

        if values:
            lines.write(values)
            self.roster_id._create_revision_snapshot('bulk_update', _('Bulk update applied to roster lines'))

        return {'type': 'ir.actions.act_window_close'}
