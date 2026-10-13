from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError, UserError


class PerformanceAppraiserLine(models.Model):
    _name = 'performance.appraiser.line'
    _description = 'Performance Appraiser Line'
    # mail.thread is required for `tracking=True` to record anything at all.
    # Lines are always edited inline in the grid and their own form is never
    # opened, so on top of the field tracking every change is relayed to the
    # parent appraiser's chatter, which is the screen people actually use.
    _inherit = ['mail.thread', 'performance.appraisal.access.mixin']

    # An appraiser-only user may change nothing here but the obtained score.
    _appraiser_writable_fields = ('score',)

    name = fields.Many2one(
        'performance.evaluation.topic',
        string="Evaluation Line (task / goal)",
        required=True, tracking=True
    )

    performance_appraiser_id = fields.Many2one(
        'performance.appraiser',
        ondelete='cascade',
        copy=False, tracking=True
    )

    score = fields.Integer(
        required=True, tracking=True, string="Obtained Score", default=1,
        help="The score obtained for this evaluation topic. Must be less than or equal to the allocated points.",
        copy=False
    )

    weightage = fields.Integer(
        default=1, max=100, min=1, tracking=True, string="Allocated Points (Σ=100)",
        help="The allocated points for this evaluation topic. Must be between 1 and 100. The total weightage across all topics should ideally sum up to 100."
    )

    def _appraiser_state(self):
        self.ensure_one()
        return self.performance_appraiser_id.sudo().state

    # -------------------------------------------------
    # CHATTER RELAY
    # -------------------------------------------------
    def _line_label(self):
        """Name of the evaluation topic of this line."""
        self.ensure_one()
        return self.sudo().name.display_name or _("Unnamed line")

    def _log_on_appraiser(self, appraiser, body):
        """Post an internal note on the parent appraiser.

        Posted in sudo (an appraiser may only touch the score, yet must still
        leave a trail on the parent) but explicitly authored by the real user,
        otherwise the note would be attributed to OdooBot. Logged as a note so
        followers are not emailed for every score correction.
        """
        if not appraiser or self.env.context.get('tracking_disable'):
            return
        appraiser.sudo().message_post(
            body=body,
            author_id=self.env.user.partner_id.id,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for appraiser in lines.sudo().mapped('performance_appraiser_id'):
            added = lines.filtered(
                lambda line: line.performance_appraiser_id == appraiser)
            items = Markup("").join(
                Markup("<li>%s — %s: %s, %s: %s</li>") % (
                    line._line_label(),
                    _("Allocated Points"), line.weightage,
                    _("Obtained Score"), line.score,
                )
                for line in added
            )
            self._log_on_appraiser(
                appraiser,
                Markup("%s<ul>%s</ul>") % (_("Evaluation lines added:"), items),
            )
        return lines

    def write(self, vals):
        labels = {
            'name': _("Evaluation Line"),
            'weightage': _("Allocated Points"),
            'score': _("Obtained Score"),
        }
        touched = [name for name in labels if name in vals]
        before = {rec.id: {f: rec[f] for f in touched} for rec in self} if touched else {}

        result = super().write(vals)

        for rec in self:
            changes = []
            for field_name in touched:
                old, new = before[rec.id][field_name], rec[field_name]
                if old == new:
                    continue
                if field_name == 'name':
                    old = old.display_name if old else _("none")
                    new = new.display_name if new else _("none")
                changes.append(
                    Markup("%s: %s &#8594; %s") % (labels[field_name], old, new))
            if changes:
                rec._log_on_appraiser(
                    rec.performance_appraiser_id,
                    Markup("<b>%s</b><br/>%s") % (
                        rec._line_label(), Markup("<br/>").join(changes)),
                )
        return result

    def unlink(self):
        removed = [(rec.performance_appraiser_id, rec._line_label())
                   for rec in self]
        result = super().unlink()
        for appraiser, label in removed:
            self._log_on_appraiser(
                appraiser,
                Markup("%s <b>%s</b>") % (_("Evaluation line removed:"), label),
            )
        return result

    @api.constrains('weightage', 'score')
    def _check_weightage_range(self):
        for rec in self:
            if rec.weightage < 1:
                raise ValidationError(
                    "Allocated points must be a positive number."
                )

            if rec.score < 1:
                raise ValidationError(
                    "Obtained score must be a positive number."
                )

            if rec.score > rec.weightage:
                raise ValidationError(
                    "Obtained score cannot exceed allocated points."
                )
