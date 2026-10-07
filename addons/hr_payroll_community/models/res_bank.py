# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

IFSC_PATTERN = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')


class ResBank(models.Model):
    _inherit = 'res.bank'

    ifsc_code = fields.Char(
        string='IFSC Code',
        index=True,
        help='Indian Financial System Code. 11 characters, for example SBIN0001234.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('ifsc_code'):
                vals['ifsc_code'] = self._normalize_ifsc(vals['ifsc_code'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('ifsc_code'):
            vals['ifsc_code'] = self._normalize_ifsc(vals['ifsc_code'])
        return super().write(vals)

    @api.constrains('ifsc_code')
    def _check_ifsc_code(self):
        for bank in self:
            if bank.ifsc_code and not IFSC_PATTERN.match(bank.ifsc_code):
                raise ValidationError(_(
                    'IFSC Code must be 11 characters: 4 letters, a 0, then 6 letters or numbers. Example: SBIN0001234.'
                ))

    @api.model
    def _normalize_ifsc(self, value):
        return (value or '').replace(' ', '').upper()

    @api.model
    def _copy_ifsc_from_bic(self):
        """Fill IFSC from BIC when BIC is already a valid IFSC and IFSC is empty."""
        banks = self.with_context(active_test=False).search([
            ('ifsc_code', 'in', [False, '']),
            ('bic', '!=', False),
        ])
        for bank in banks:
            bic = self._normalize_ifsc(bank.bic)
            if IFSC_PATTERN.match(bic):
                bank.ifsc_code = bic
