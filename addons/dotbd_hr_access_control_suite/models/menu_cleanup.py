# -*- coding: utf-8 -*-

from odoo import api, models


class AttendanceMenuCleanup(models.Model):
    _inherit = 'ir.ui.menu'

    def _register_hook(self):
        result = super()._register_hook()

        return result

    @api.model
    def cleanup_duplicate_attendance_menus(self):
        # Keep the standard Attendance root and archive stale duplicate roots
        # left behind by earlier menu configurations.
        self.env.cr.execute("""
            SELECT imd.res_id
              FROM ir_model_data imd
             WHERE imd.model = 'ir.ui.menu'
               AND imd.module = 'hr_attendance'
               AND imd.name = 'menu_hr_attendance_root'
             LIMIT 1
        """)
        canonical = self.env.cr.fetchone()
        if not canonical:
            return
        management = self.env.ref(
            'hr_attendance.menu_hr_attendance_view_attendances_management',
            raise_if_not_found=False,
        )
        keep_ids = [canonical[0]] + (management.ids if management else [])
        self.env.cr.execute("""
            UPDATE ir_ui_menu
               SET active = FALSE
             WHERE COALESCE(name->>'en_US', '') = 'Attendances'
               AND id != ALL(%s)
               AND active = TRUE
        """, (keep_ids,))

        # Normalize the custom dashboard menu if an earlier update created it
        # with a technical name or without the Attendance parent.
        self.env.cr.execute("""
            SELECT imd.res_id
              FROM ir_model_data imd
             WHERE imd.model = 'ir.ui.menu'
               AND imd.module = 'dotbd_hr_zk_attendance_suite'
               AND imd.name = 'menu_attendance_main_dashboard'
             LIMIT 1
        """)
        dashboard = self.env.cr.fetchone()
        if dashboard:
            self.browse(dashboard[0]).write({
                'name': 'Dashboard',
                'parent_id': canonical[0],
                'active': True,
            })
