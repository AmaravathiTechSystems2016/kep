# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ManpowerRequisitionDashboard(models.TransientModel):
    _name = 'manpower.requisition.dashboard'
    _description = 'Manpower Requisition Dashboard'

    total_requisition_count = fields.Integer(compute='_compute_kpis')
    draft_count = fields.Integer(compute='_compute_kpis')
    submitted_count = fields.Integer(compute='_compute_kpis')
    approved_count = fields.Integer(compute='_compute_kpis')
    rejected_count = fields.Integer(compute='_compute_kpis')
    worker_count = fields.Integer(compute='_compute_kpis')
    office_count = fields.Integer(compute='_compute_kpis')
    total_requested_headcount = fields.Integer(compute='_compute_kpis')
    total_headcount_gap = fields.Integer(compute='_compute_kpis')

    @api.depends_context('uid')
    def _compute_kpis(self):
        Req = self.env['manpower.requisition'].sudo()
        for rec in self:
            rec.total_requisition_count = Req.search_count([])
            rec.draft_count = Req.search_count([('state', '=', 'draft')])
            rec.submitted_count = Req.search_count([('state', '=', 'submitted')])
            rec.approved_count = Req.search_count([('state', '=', 'approved')])
            rec.rejected_count = Req.search_count([('state', '=', 'rejected')])
            rec.worker_count = Req.search_count([('request_type', '=', 'worker')])
            rec.office_count = Req.search_count([('request_type', '=', 'office')])
            grouped = Req.read_group([], ['requested_headcount', 'headcount_gap'], [])
            totals = grouped[0] if grouped else {}
            rec.total_requested_headcount = int(totals.get('requested_headcount', 0) or 0)
            rec.total_headcount_gap = int(totals.get('headcount_gap', 0) or 0)

    def _open_requisition_list(self, domain, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'manpower.requisition',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_open_all(self):
        return self._open_requisition_list([], _('All Requisitions'))

    def action_open_draft(self):
        return self._open_requisition_list([('state', '=', 'draft')], _('Draft Requisitions'))

    def action_open_submitted(self):
        return self._open_requisition_list([('state', '=', 'submitted')], _('Submitted Requisitions'))

    def action_open_approved(self):
        return self._open_requisition_list([('state', '=', 'approved')], _('Approved Requisitions'))
