# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration script to ensure biometric.device.log model exists before loading data.
    This fixes the issue where ir.model.access.csv fails to load because the model
    doesn't exist yet in the database during upgrade.
    """
    _logger.info("Running pre-migrate script for dotbd_hr_zk_attendance_suite...")
    
    # Check if the model already exists in ir_model
    cr.execute("SELECT id FROM ir_model WHERE model = 'biometric.device.log'")
    if not cr.fetchone():
        _logger.info("Creating biometric.device.log model entry manually...")
        try:
            # 1. Insert into ir_model
            cr.execute("""
                INSERT INTO ir_model (model, name, state, transient, info, "order")
                VALUES ('biometric.device.log', '{"en_US": "Biometric Device Operation Log"}', 'base', False, 'Pre-created by migration', 'id')
                RETURNING id
            """)
            model_id = cr.fetchone()[0]
            
            # 2. Insert into ir_model_data (external ID)
            # This is crucial for the CSV file to find 'model_biometric_device_log'
            cr.execute("""
                INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                VALUES ('dotbd_hr_zk_attendance_suite', 'model_biometric_device_log', 'ir.model', %s, True)
            """, (model_id,))
            
            _logger.info("Successfully created biometric.device.log model entry and external ID.")
        except Exception as e:
            _logger.warning(f"Failed to create biometric.device.log model entry: {e}")
    else:
        _logger.info("biometric.device.log model entry already exists.")
