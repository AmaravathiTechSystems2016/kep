from odoo import api, fields, models


class CrmLeadType(models.Model):
    _name = 'crm.lead.type'
    _description = 'CRM Lead Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'Type name must be unique.',
    )

    @api.model
    def _seed_defaults(self, names, start=1):
        """Create the given values when missing (archived ones count as present)."""
        existing = set(self.with_context(active_test=False).search([]).mapped('name'))
        self.create([{'name': name, 'sequence': seq} for seq, name in enumerate(names, start) if name not in existing])


class CrmLeadSystem(models.Model):
    _name = 'crm.lead.system'
    _description = 'CRM Lead System'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'System name must be unique.',
    )

    @api.model
    def _seed_defaults(self, names, start=1):
        """Create the given values when missing (archived ones count as present)."""
        existing = set(self.with_context(active_test=False).search([]).mapped('name'))
        self.create([{'name': name, 'sequence': seq} for seq, name in enumerate(names, start) if name not in existing])


class CrmLeadCapacity(models.Model):
    _name = 'crm.lead.capacity'
    _description = 'CRM Lead Capacity'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'Capacity name must be unique.',
    )
