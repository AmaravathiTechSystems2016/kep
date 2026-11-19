from odoo import models

# Column titles (casefolded) that must map to a specific crm.lead field. Covers the
# exported labels (with units) and the short names people usually type in a sheet.
LEAD_HEADER_ALIASES = {
    # "type" is also the lead/opportunity flag; the capitalised "Type" column is the
    # delivery model master. The lowercase technical header "type" is left alone.
    'type': 'lead_type_id',
    'project / delivery model': 'lead_type_id',
    'delivery model': 'lead_type_id',
    'system': 'system_id',
    'system type': 'system_id',
    'ph': 'ph_value',
    'tds': 'tds',
    'tds (mg/l)': 'tds',
    'cod': 'cod',
    'cod (mg/l)': 'cod',
    'bod': 'bod',
    'bod (mg/l)': 'bod',
    'tss': 'tss',
    'tss (mg/l)': 'tss',
    'hardness': 'hardness',
    'hardness (mg/l as caco3)': 'hardness',
    'oil & grease': 'oil_grease',
    'oil & grease (mg/l)': 'oil_grease',
    'oil and grease': 'oil_grease',
    'silica': 'silica',
    'silica (ppm)': 'silica',
    'submission date': 'submitted_date',
    'submitted date': 'submitted_date',
    'proposal / revision no.': 'proposal_no',
    'proposal no': 'proposal_no',
    'proposal no.': 'proposal_no',
    'proposal / revision no': 'proposal_no',
    'revision no': 'proposal_no',
    'worked by': 'worked_by_id',
    'lead owner': 'lead_owner_id',
}


class BaseImport(models.TransientModel):
    _inherit = 'base_import.import'

    def _get_mapping_suggestion(self, header, fields_tree, header_types, mapping_fields):
        if self.res_model == 'crm.lead' and header:
            title = ' '.join(header.strip().casefold().split())
            fname = LEAD_HEADER_ALIASES.get(title)
            # The technical header "type" keeps meaning the lead/opportunity flag.
            if fname and not (fname == 'lead_type_id' and header.strip() == 'type'):
                if any(field['name'] == fname for field in fields_tree):
                    return {'field_path': [fname], 'distance': 0}
        return super()._get_mapping_suggestion(header, fields_tree, header_types, mapping_fields)
