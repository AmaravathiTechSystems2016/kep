# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure the hr_attendance roster context column exists before upgrade.

    The field is already present in Python, but upgraded databases may still be
    missing the physical column. Add it if needed so reads do not crash.
    """
    _logger.info("Running pre-migrate for dotbd_hr_zk_attendance_suite %s", version)

    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'hr_attendance'
          AND column_name = 'shift_roster_line_id'
    """)
    if cr.fetchone():
        _logger.info("hr_attendance.shift_roster_line_id already exists.")
        return

    _logger.warning("Adding missing hr_attendance.shift_roster_line_id column.")
    cr.execute("""
        ALTER TABLE hr_attendance
        ADD COLUMN shift_roster_line_id integer
    """)

