# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ManpowerRequisitionPartialApprovalWizard(models.TransientModel):
    _name = 'manpower.requisition.partial.approval.wizard'
    _description = 'Manpower Requisition Partial Approval Wizard'

    requisition_id = fields.Many2one(
        'manpower.requisition',
        string='Requisition',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    line_ids = fields.One2many(
        'manpower.requisition.partial.approval.wizard.line',
        'wizard_id',
        string='Approval Lines',
    )

    def action_confirm(self):
        self.ensure_one()
        if self.requisition_id.state != 'submitted':
            raise ValidationError(_('You can only approve a submitted requisition.'))
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise AccessError(_('Only an HR manager can approve this requisition.'))
        if not any(line.approved_count > 0 for line in self.line_ids):
            raise ValidationError(_('Please approve at least one position before confirming.'))

        for wiz_line in self.line_ids:
            requisition_line = wiz_line.requisition_line_id
            if wiz_line.approved_count < requisition_line.approved_count:
                raise ValidationError(_(
                    'You cannot reduce the approved so far count for "%s". Reset the requisition first if you need to correct it.'
                ) % (requisition_line.designation,))
            if wiz_line.approved_count > requisition_line.required_count:
                raise ValidationError(_(
                    'Approved so far for "%s" cannot be greater than the requested count.'
                ) % (requisition_line.designation,))
            requisition_line.approved_count = wiz_line.approved_count

        self.requisition_id.action_approve()
        return {'type': 'ir.actions.act_window_close'}


class ManpowerRequisitionPartialApprovalWizardLine(models.TransientModel):
    _name = 'manpower.requisition.partial.approval.wizard.line'
    _description = 'Manpower Requisition Partial Approval Wizard Line'
    _order = 'id asc'

    wizard_id = fields.Many2one(
        'manpower.requisition.partial.approval.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    requisition_line_id = fields.Many2one(
        'manpower.requisition.line',
        string='Requisition Line',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    designation = fields.Char(related='requisition_line_id.designation', string='Designation', readonly=True)
    required_count = fields.Integer(related='requisition_line_id.required_count', string='Requested', readonly=True)
    approved_count = fields.Integer(
        string='Approved so far',
        default=0,
        help='Set the total approved count accumulated so far for this requisition line.',
    )
