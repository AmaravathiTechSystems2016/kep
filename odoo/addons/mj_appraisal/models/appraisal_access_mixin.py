from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

GROUP_APPRAISER = 'mj_appraisal.group_performance_appraisal_appraiser'
GROUP_VIEWER = 'mj_appraisal.group_performance_appraisal_viewer'
GROUP_MANAGER = 'mj_appraisal.group_performance_appraisal_manager'

# Fields the ORM / chatter may write on behalf of any user. They must never be
# rejected by the appraiser guard or ordinary saves and recomputes would break.
TECHNICAL_FIELDS = {
    'write_date', 'write_uid', 'create_date', 'create_uid',
    'message_ids', 'message_follower_ids', 'message_main_attachment_id',
    'message_partner_ids', 'activity_ids', '__last_update',
}


class PerformanceAppraisalAccessMixin(models.AbstractModel):
    """Shared helpers for the "Appraiser (score only)" security group.

    A user in ``group_performance_appraisal_appraiser`` who is not also a
    Performance Appraisal Manager is called an "appraiser-only" user. Record
    rules limit such a user to the ``performance.appraiser`` records where they
    are the appraiser; the guards below make sure that within those records the
    only thing they can actually change is the obtained score, and only while
    the appraisal is still in Draft.

    Note that the Viewer group deliberately does *not* lift the restriction.
    Viewer only widens what an appraiser can see; if it also lifted the write
    guard, then "Appraiser + Viewer" would be more powerful than either group
    on its own and the whole restriction would be trivially bypassable.
    """

    _name = 'performance.appraisal.access.mixin'
    _description = 'Performance Appraisal Access Helpers'

    # Fields an appraiser-only user is allowed to change explicitly.
    _appraiser_writable_fields = ()
    # Stored computed fields the ORM writes back during recomputation.
    _appraiser_recomputed_fields = ()

    is_appraiser_only = fields.Boolean(
        string="Restricted Appraiser",
        compute='_compute_is_appraiser_only',
        help="Technical field. True when the current user may only fill in "
             "obtained scores on their own evaluation lines.",
    )

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    @api.model
    def _is_appraiser_only(self):
        """Return True when the current user may only enter scores.

        Only the Manager group lifts the restriction. Viewer does not: it is
        a read-only group, so a user holding "Appraiser + Viewer" is still an
        appraiser as far as writing is concerned.
        """
        if self.env.su:
            return False
        user = self.env.user
        if user._is_superuser() or user._is_admin():
            return False
        if not user.has_group(GROUP_APPRAISER):
            return False
        return not user.has_group(GROUP_MANAGER)

    @api.depends_context('uid')
    def _compute_is_appraiser_only(self):
        restricted = self._is_appraiser_only()
        for record in self:
            record.is_appraiser_only = restricted

    def _appraiser_state(self):
        """State of the appraisal this record belongs to. Override per model."""
        self.ensure_one()
        return False

    # ------------------------------------------------------------------
    # GUARDS
    # ------------------------------------------------------------------
    def _check_appraiser_vals(self, vals):
        """Reject any field an appraiser-only user is not allowed to change."""
        if not self._is_appraiser_only():
            return
        allowed = (
            set(self._appraiser_writable_fields)
            | set(self._appraiser_recomputed_fields)
            | TECHNICAL_FIELDS
        )
        forbidden = sorted(set(vals or {}) - allowed)
        if forbidden:
            raise AccessError(_(
                "As an appraiser you may only fill in the Obtained Score of "
                "your own evaluation lines.\nYou are not allowed to modify: %s"
            ) % ', '.join(
                self._fields[name].string if name in self._fields else name
                for name in forbidden
            ))

    def _check_appraiser_state(self):
        """Appraisers may only score while the appraisal is still in Draft."""
        if not self._is_appraiser_only():
            return
        for record in self:
            state = record._appraiser_state()
            if state and state != 'draft':
                raise UserError(_(
                    "The appraisal is no longer in Draft, so its scores can "
                    "no longer be changed."
                ))

    def _forbid_appraiser(self, action):
        if self._is_appraiser_only():
            raise AccessError(_(
                "As an appraiser you are only allowed to fill in the Obtained "
                "Score of your own evaluation lines. You cannot %s records here."
            ) % action)

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def write(self, vals):
        self._check_appraiser_vals(vals)
        # Only block on the state when the appraiser is making a *real* edit.
        # Stored computed fields written back by the ORM must always go
        # through, whatever the state of the appraisal is.
        if set(vals or {}) & set(self._appraiser_writable_fields):
            self._check_appraiser_state()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        self._forbid_appraiser(_("create"))
        return super().create(vals_list)

    def unlink(self):
        self._forbid_appraiser(_("delete"))
        return super().unlink()
