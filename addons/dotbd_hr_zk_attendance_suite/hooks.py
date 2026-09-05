# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#
################################################################################
import logging
from odoo.tools import convert_file

_logger = logging.getLogger(__name__)

MODULE = 'dotbd_hr_zk_attendance_suite'

# Payroll data files to load conditionally
_PAYROLL_DATA_FILES = [
    'data/salary_rule_data.xml',
    'views/hr_payslip_views.xml',
]


def post_init_hook(env):
    """Post-init hook: load payroll data files if hr_payroll_community is installed."""
    payroll_installed = env['ir.module.module'].sudo().search([
        ('name', '=', 'hr_payroll_community'),
        ('state', '=', 'installed'),
    ], limit=1)

    if payroll_installed:
        _logger.info("hr_payroll_community is installed - loading payroll integration data...")
        for filename in _PAYROLL_DATA_FILES:
            try:
                # Note: `kind` parameter was deprecated in Odoo 19 — omit it
                convert_file(
                    env, MODULE, filename,
                    idref={}, mode='init', noupdate=True,
                )
                _logger.info("Loaded payroll data file: %s", filename)
            except Exception as e:
                _logger.warning("Could not load payroll data file %s: %s", filename, e)
    else:
        _logger.info("hr_payroll_community not installed - skipping payroll integration data.")


def pre_init_hook(env):
    """
    Pre-init hook to ensure biometric.device.log model exists in ir_model before
    ir.model.access.csv is loaded (which references model_biometric_device_log).

    Uses safe SQL compatible with Odoo 17/18/19 by detecting the ir_model.name
    column type (JSONB in Odoo 17+ vs VARCHAR in older versions).
    """
    _logger.info("Running pre_init_hook for dotbd_hr_zk_attendance_suite...")
    cr = env.cr

    # Check if the model already exists in ir_model
    cr.execute("SELECT id FROM ir_model WHERE model = 'biometric.device.log'")
    row = cr.fetchone()
    if row:
        model_id = row[0]
        _logger.info("biometric.device.log model entry already exists (id=%s).", model_id)
    else:
        _logger.info("Creating biometric.device.log model entry...")
        try:
            # Detect whether ir_model.name is JSONB (Odoo 17+) or VARCHAR (Odoo 16-)
            cr.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'ir_model' AND column_name = 'name'"
            )
            name_col_type = (cr.fetchone() or ['varchar'])[0].lower()

            if name_col_type == 'jsonb':
                name_value = '{"en_US": "Biometric Device Operation Log"}'
            else:
                name_value = 'Biometric Device Operation Log'

            cr.execute(
                """
                INSERT INTO ir_model (model, name, state, transient, "order")
                VALUES ('biometric.device.log', %s, 'base', False, 'id')
                RETURNING id
                """,
                (name_value,)
            )
            model_id = cr.fetchone()[0]

            # Register the external ID so the ACL CSV can resolve 'model_biometric_device_log'
            cr.execute(
                """
                INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                VALUES ('dotbd_hr_zk_attendance_suite', 'model_biometric_device_log',
                        'ir.model', %s, True)
                ON CONFLICT (module, name) DO NOTHING
                """,
                (model_id,)
            )
            _logger.info(
                "Created biometric.device.log model entry (id=%s).", model_id
            )
        except Exception as e:
            _logger.warning("Could not create biometric.device.log model entry: %s", e)
