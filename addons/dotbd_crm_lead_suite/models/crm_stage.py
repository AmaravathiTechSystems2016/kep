from odoo import api, models

# (xmlid of the standard stage, name it ships with, new name, new sequence, only move if still at this sequence)
PIPELINE_RENAMES = [
    ('crm.stage_lead1', 'New', 'Inquiry', 1, None),
    ('crm.stage_lead2', 'Qualified', 'Scheme / Tech Offer', 2, None),
    ('crm.stage_lead3', 'Proposition', 'Commercial Offer', 3, None),
]


class CrmStage(models.Model):
    _inherit = 'crm.stage'

    @api.model
    def _setup_kep_pipeline(self):
        """Turn the standard pipeline into: Inquiry > Scheme / Tech Offer >
        Commercial Offer > Discussion > PO > Won (Lost is Odoo's native lost status).

        Standard stages are renamed in place, so leads keep their stage. A stage is
        only renamed while it still carries its original name, which makes this safe
        to run on every upgrade and never overrides later manual changes.
        """
        for xmlid, old_name, new_name, sequence, _only_if in PIPELINE_RENAMES:
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage and stage.exists() and stage.name == old_name:
                stage.write({'name': new_name, 'sequence': sequence})
        won = self.env.ref('crm.stage_lead4', raise_if_not_found=False)
        if won and won.exists() and won.sequence == 70:
            won.sequence = 6
