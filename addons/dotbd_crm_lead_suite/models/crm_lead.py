from odoo import fields, models

INQUIRY_FIELDS = [
    'lead_type_id',
    'system_id',
    'capacity_id',
    'submitted_date',
    'revision_date',
    'inquiry_date',
]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    lead_type_id = fields.Many2one(
        'crm.lead.type',
        string='Type',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='EPC or Non-EPC. Values are created under CRM Configuration.',
    )
    system_id = fields.Many2one(
        'crm.lead.system',
        string='System',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Values are created under CRM Configuration.',
    )
    capacity_id = fields.Many2one(
        'crm.lead.capacity',
        string='Capacity',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Values are created under CRM Configuration.',
    )
    submitted_date = fields.Date(string='Submitted Date', tracking=True)
    revision_date = fields.Date(string='Revision Date', tracking=True)
    inquiry_date = fields.Date(string='Inquiry Date', tracking=True)

    def _merge_get_fields(self):
        return super()._merge_get_fields() + INQUIRY_FIELDS
