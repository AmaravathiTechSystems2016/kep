from odoo import models


class BaseImport(models.TransientModel):
    _inherit = 'base_import.import'

    def _get_mapping_suggestion(self, header, fields_tree, header_types, mapping_fields):
        # crm.lead already has a technical field named "type" (lead/opportunity).
        # A column titled "Type" is the configurable EPC master. The technical
        # header "type" still maps to the lead/opportunity flag.
        if (
            self.res_model == 'crm.lead'
            and header
            and header.strip().casefold() == 'type'
            and header.strip() != 'type'
            and any(field['name'] == 'lead_type_id' for field in fields_tree)
        ):
            return {'field_path': ['lead_type_id'], 'distance': 0}
        return super()._get_mapping_suggestion(header, fields_tree, header_types, mapping_fields)
