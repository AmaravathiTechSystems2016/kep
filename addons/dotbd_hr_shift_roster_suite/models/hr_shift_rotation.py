# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrShiftAssignmentRotationLine(models.Model):
    _name = 'hr.shift.assignment.rotation.line'
    _description = 'Shift Assignment Rotation Line'
    _order = 'sequence, id'

    assignment_id = fields.Many2one(
        'hr.shift.assignment', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    shift_template_id = fields.Many2one(
        'hr.shift.template', required=True, ondelete='restrict')
    note = fields.Char()

    _sql_constraints = [
        ('uniq_assignment_sequence', 'unique(assignment_id, sequence)',
         'Each rotation step must have a unique sequence number per assignment.'),
    ]


class HrShiftAssignment(models.Model):
    _inherit = 'hr.shift.assignment'

    rotation_mode = fields.Selection([
        ('none', 'No Rotation'),
        ('cycle', 'Cycle Rotation'),
    ], default='none', tracking=True)
    rotation_start_date = fields.Date(
        string='Rotation Start Date',
        help='The date from which the rotation cycle starts.')
    rotation_cycle_days = fields.Integer(
        string='Days per Step',
        default=1,
        help='How many days each shift template remains active in the cycle.')
    rotation_line_ids = fields.One2many(
        'hr.shift.assignment.rotation.line',
        'assignment_id',
        string='Rotation Sequence')

    @api.constrains('rotation_mode', 'rotation_line_ids', 'rotation_cycle_days', 'rotation_start_date')
    def _check_rotation_settings(self):
        for rec in self:
            if rec.rotation_mode != 'cycle':
                continue
            if rec.rotation_cycle_days <= 0:
                raise ValidationError(_('Days per Step must be greater than zero.'))
            if not rec.rotation_start_date:
                raise ValidationError(_('Rotation Start Date is required for cycle rotation.'))
            if len(rec.rotation_line_ids) < 2:
                raise ValidationError(_('Cycle rotation needs at least two shift templates.'))
            if not rec.rotation_line_ids.filtered('shift_template_id'):
                raise ValidationError(_('Every rotation line must have a shift template.'))

    def _get_rotation_shift_template(self, current_date):
        """Return the shift template picked by the cycle rotation, if enabled."""
        self.ensure_one()
        if self.rotation_mode != 'cycle' or not self.rotation_start_date or not self.rotation_line_ids:
            return self.shift_template_id

        ordered_lines = self.rotation_line_ids.sorted(lambda line: (line.sequence, line.id))
        if not ordered_lines:
            return self.shift_template_id

        cycle_days = max(1, self.rotation_cycle_days)
        offset = (current_date - self.rotation_start_date).days
        if offset < 0:
            offset = 0
        step_index = (offset // cycle_days) % len(ordered_lines)
        return ordered_lines[step_index].shift_template_id or self.shift_template_id
