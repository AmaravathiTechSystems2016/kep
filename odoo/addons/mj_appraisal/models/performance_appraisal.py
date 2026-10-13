from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tools import float_compare

# Odoo's "Administration / Settings" access right. A user holding it may send
# an appraisal back to Draft at any point, including after it was approved.
GROUP_SETTINGS = 'base.group_system'


class PerformanceAppraisal(models.Model):
    _name = 'performance.appraisal'
    _description = 'Performance Appraisal'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'performance.appraisal.access.mixin']
    # _order = 'sequence asc, appraisal_date desc'
    _order = 'appraisal_date desc'

    # An appraiser-only user may not change anything on the appraisal itself;
    # the fields below are only ever written by the ORM when recomputing.
    _appraiser_writable_fields = ()
    _appraiser_recomputed_fields = ('score', 'total_weightage')

    name = fields.Char(required=True, tracking=True, string="Appraisal Name")
    employee_id = fields.Many2one(
        'hr.employee', tracking=True, copy=False
    )

    # sequence = fields.Integer(related='employee_id.sequence', store=True)

    date_from = fields.Date(
        string="Evaluation Start Date", required=True, tracking=True
    )
    date_to = fields.Date(
        string="Evaluation End Date", required=True, tracking=True
    )

    appraisal_date = fields.Date(
        default=fields.Date.context_today, tracking=True
    )

    performance_appraiser_ids = fields.One2many(
        'performance.appraiser',
        'performance_appraisal_id',
        string="Appraisers", copy=False
    )

    appraiser_count = fields.Integer(
        compute='_compute_appraiser_count'
    )

    score = fields.Float(
        compute='_compute_appraisal_score',
        store=True
    )

    total_weightage = fields.Integer(
        compute='_compute_total_weightage',
        store=True
    )

    comments = fields.Text(tracking=True)

    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted'), ('confirmed', 'Approved')],
        default='draft',
        tracking=True, copy=False
    )

    can_force_draft = fields.Boolean(
        string="Can Send to Draft",
        compute='_compute_can_force_draft',
        help="Technical field driving the visibility of the Send to Draft "
             "button. True for Settings administrators only.",
    )

    # -------------------------------------------------
    # COMPUTES
    # -------------------------------------------------
    # NOTE: the aggregations below run in sudo on purpose. An appraiser only
    # sees their own row of performance_appraiser_ids, and computing a *stored*
    # total from that record-rule filtered set would persist a wrong score.

    @api.depends('performance_appraiser_ids.weightage')
    def _compute_total_weightage(self):
        for rec in self:
            rec.total_weightage = sum(
                rec.sudo().performance_appraiser_ids.mapped('weightage')
            )

    @api.depends('performance_appraiser_ids.score',
                 'performance_appraiser_ids.weightage')


    def _compute_appraisal_score(self):
        for appraisal in self:
            weighted_score = sum(
                appraisal.sudo().performance_appraiser_ids.mapped('score')
            )
            if not weighted_score:
                appraisal.score = 0.0
                continue

            appraisal.score = weighted_score

    def _compute_appraiser_count(self):
        for rec in self:
            rec.appraiser_count = len(rec.sudo().performance_appraiser_ids)

    # Depends on the *user*, not on any field, so the context key is the only
    # dependency: without depends_context('uid') the value computed for the
    # first user would be served from cache to everybody else.
    @api.depends_context('uid')
    def _compute_can_force_draft(self):
        allowed = self._can_force_draft()
        for rec in self:
            rec.can_force_draft = allowed


    @api.constrains('performance_appraiser_ids', 'performance_appraiser_ids.weightage')
    def _check_total_weightage(self):
        for rec in self:
            appraisers = rec.sudo().performance_appraiser_ids
            if not appraisers:
                continue

            total = sum(appraisers.mapped('weightage'))
            if float_compare(total, 100.0, precision_digits=2) != 0:
                raise ValidationError(
                    _("Total allocated points must be 100. Current total: %s")
                    % total
                )


    # -------------------------------------------------
    # ACTIONS
    # -------------------------------------------------

    def _appraiser_state(self):
        self.ensure_one()
        return self.sudo().state

    def action_open_appraisers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Appraisers',
            'res_model': 'performance.appraiser',
            'view_mode': 'list,form',
            'domain': [('performance_appraisal_id', '=', self.id)],
            'context': {'default_performance_appraisal_id': self.id},
        }

    def action_submit(self):
        for rec in self:
            rec.state = 'submitted'

    def action_confirm(self):
        for rec in self:
            rec.state = 'confirmed'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'

    @api.model
    def _can_force_draft(self):
        """True when the current user may reopen an approved appraisal."""
        user = self.env.user
        return bool(
            self.env.su
            or user._is_superuser()
            or user._is_admin()
            or user.has_group(GROUP_SETTINGS)
        )

    def action_send_to_draft(self):
        """Force an appraisal back to Draft, whatever its current state.

        Unlike ``action_reset_draft`` this stays available once the appraisal
        has been approved, which is why it is reserved for Settings
        administrators. The group check here is the real security boundary --
        the ``groups`` attribute on the button only hides it -- and the write
        runs in ``sudo()`` so that a Settings admin who is not a Performance
        Appraisal Manager can still use it.
        """
        if not self._can_force_draft():
            raise AccessError(_(
                "Only a Settings administrator can send an appraisal back to "
                "Draft once it has been submitted or approved."
            ))
        labels = dict(self._fields['state'].selection)
        for rec in self:
            rec_sudo = rec.sudo()
            if rec_sudo.state == 'draft':
                raise UserError(_("This appraisal is already in Draft."))
            previous = labels.get(rec_sudo.state, rec_sudo.state)
            rec_sudo.write({'state': 'draft'})
            rec_sudo.message_post(
                body=_(
                    "Sent back to Draft from %(state)s by %(user)s.",
                    state=previous, user=self.env.user.name,
                ),
                author_id=self.env.user.partner_id.id,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        return True

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})

        # ---- Step 1: copy main record (respecting copy=False automatically)
        new_appraisal = super().copy(default)

        # ---- Step 2: duplicate appraisers
        for appraiser in self.performance_appraiser_ids:
            new_appraiser = appraiser.copy({
                'performance_appraisal_id': new_appraisal.id,
            })

        return new_appraisal


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    appraisal_score = fields.Float(
        compute='_compute_appraisal_score',
        store=True,
        string="Score"
    )

    performance_appraisal_ids = fields.One2many(
        'performance.appraisal',
        'employee_id'
    )

    appraisal_count = fields.Integer(
        compute='_compute_appraisal_count',
        string="Appraisals"
    )

    def _compute_appraisal_count(self):
        for employee in self:
            employee.appraisal_count = len(
                employee.sudo().performance_appraisal_ids.filtered(lambda a: a.state == 'confirmed')
            )

    @api.depends('performance_appraisal_ids.score', 'performance_appraisal_ids.state')
    def _compute_appraisal_score(self):
        for employee in self:
            confirmed = employee.sudo().performance_appraisal_ids.filtered(
                lambda a: a.state == 'confirmed' and a.score
            )
            employee.appraisal_score = (
                round(sum(confirmed.mapped('score')) / len(confirmed), 2)
                if confirmed else 0.0
            )

    def action_view_appraisals(self):
        self.ensure_one()
        return {
            'name': 'Performance Appraisals',
            'type': 'ir.actions.act_window',
            'res_model': 'performance.appraisal',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
            },
        }
