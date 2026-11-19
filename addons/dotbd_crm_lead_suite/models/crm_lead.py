from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

INQUIRY_FIELDS = [
    'lead_type_id',
    'system_id',
    'capacity_id',
    'submitted_date',
    'revision_date',
    'inquiry_date',
    'proposal_no',
    'worked_by_id',
    'lead_owner_id',
    'ph_value',
    'tds',
    'cod',
    'bod',
    'tss',
    'hardness',
    'oil_grease',
    'silica',
]

# Effluent parameters that must be zero or positive (pH has its own 0-14 rule).
EFFLUENT_NON_NEGATIVE_FIELDS = ['tds', 'cod', 'bod', 'tss', 'hardness', 'oil_grease', 'silica']


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    lead_type_id = fields.Many2one(
        'crm.lead.type',
        string='Project / Delivery Model',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='EPC, Non-EPC or End User. Values are created under CRM Configuration.',
    )
    system_id = fields.Many2one(
        'crm.lead.system',
        string='System Type',
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
    proposal_no = fields.Char(
        string='Proposal / Revision No.',
        tracking=True,
        copy=False,
        index='trigram',
        help='Proposal code with revision, e.g. 26084-KEP-MEE-PR-101-R6.',
    )
    worked_by_id = fields.Many2one(
        'res.users',
        string='Worked By',
        domain=[('share', '=', False)],
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Engineer who drafts the proposal.',
    )
    lead_owner_id = fields.Many2one(
        'res.users',
        string='Lead Owner',
        domain=[('share', '=', False)],
        ondelete='restrict',
        index=True,
        tracking=True,
        help='Senior commercial lead responsible for this lead.',
    )

    ph_value = fields.Float(string='pH', digits=(16, 2), tracking=True, help='Effluent acidity/alkalinity, range 0-14.')
    tds = fields.Float(string='TDS (mg/L)', digits=(16, 2), tracking=True, help='Total Dissolved Solids in ppm / mg/L.')
    cod = fields.Float(string='COD (mg/L)', digits=(16, 2), tracking=True, help='Chemical Oxygen Demand in mg/L.')
    bod = fields.Float(string='BOD (mg/L)', digits=(16, 2), tracking=True, help='Biological Oxygen Demand in mg/L.')
    tss = fields.Float(string='TSS (mg/L)', digits=(16, 2), tracking=True, help='Total Suspended Solids in mg/L.')
    hardness = fields.Float(string='Hardness (mg/L as CaCO3)', digits=(16, 2), tracking=True)
    oil_grease = fields.Float(string='Oil & Grease (mg/L)', digits=(16, 2), tracking=True)
    silica = fields.Float(string='Silica (ppm)', digits=(16, 2), tracking=True, help='High-risk scaling metric for MEE/MVRE.')

    @api.constrains('ph_value')
    def _check_ph_value(self):
        for lead in self:
            if not 0 <= lead.ph_value <= 14:
                raise ValidationError(_('pH must be between 0 and 14.'))

    @api.constrains(*EFFLUENT_NON_NEGATIVE_FIELDS)
    def _check_effluent_values(self):
        for lead in self:
            for fname in EFFLUENT_NON_NEGATIVE_FIELDS:
                if lead[fname] < 0:
                    raise ValidationError(_('%s cannot be negative.', lead._fields[fname].get_description(self.env, ['string'])['string']))

    def _merge_get_fields(self):
        return super()._merge_get_fields() + INQUIRY_FIELDS
