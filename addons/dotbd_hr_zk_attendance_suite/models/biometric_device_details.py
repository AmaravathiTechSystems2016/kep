# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit
#
################################################################################

import datetime
import logging
import pytz
import threading
import time as _time
from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.orm.registry import Registry as odoo_registry
from odoo.exceptions import UserError, ValidationError
from .zk_machine_attendance import ZkMachineAttendance

_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Please Install pyzk library.")


class BiometricDeviceDetails(models.Model):
    """Enhanced Model for biometric device with full pyzk capabilities"""
    _name = 'biometric.device.details'
    _description = 'Biometric Device Details - Enhanced'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ==================== BASIC DEVICE INFORMATION ====================
    name = fields.Char(string='Name', required=True, help='Device Name', tracking=True)
    device_ip = fields.Char(string='Device IP',
                            help='The IP address of the Device', tracking=True)
    port_number = fields.Integer(string='Port Number', default=4370,
                                 help="The Port Number of the Device (default: 4370)", tracking=True)
    device_password = fields.Char(string='Device Password',
                                   groups='dotbd_hr_zk_attendance_suite.group_attendance_manager',
                                   help='Password for the biometric device. Leave empty for default (0). '
                                        'Most ZKteco devices use password 0 by default.')
    address_id = fields.Many2one('res.partner', string='Working Address',
                                 help='Working address of the partner')
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.user.company_id.id,
                                 help='Current Company')
    last_download_time = fields.Datetime(string='Last Download Time',
                                         help='The last time the attendance data was downloaded')

    # ==================== DEVICE INFORMATION (NEW - from pyzk) ====================
    firmware_version = fields.Char(string='Firmware Version', readonly=True, copy=False,
                                   help='Device firmware version retrieved from device')
    serial_number = fields.Char(string='Serial Number', readonly=True, copy=False,
                               help='Unique device serial number')
    platform = fields.Char(string='Platform', readonly=True, copy=False,
                          help='Device platform/model')
    mac_address = fields.Char(string='MAC Address', readonly=True, copy=False,
                             help='Device MAC address')
    device_name_from_device = fields.Char(string='Device Name (from Device)', readonly=True, copy=False,
                                          help='Device name stored in the device itself')
    face_version = fields.Char(string='Face Recognition Version', readonly=True, copy=False,
                               help='Face recognition module version')
    fp_version = fields.Char(string='Fingerprint Version', readonly=True, copy=False,
                            help='Fingerprint module version')
    pin_width = fields.Integer(string='PIN Width', readonly=True, copy=False,
                               help='Maximum width of user PIN/password')

    # Network Information
    network_ip = fields.Char(string='Network IP', readonly=True, copy=False)
    network_mask = fields.Char(string='Network Mask', readonly=True, copy=False)
    network_gateway = fields.Char(string='Network Gateway', readonly=True, copy=False)

    # ==================== DEVICE CAPACITY (NEW - from pyzk) ====================
    user_capacity = fields.Integer(string='User Capacity', readonly=True, copy=False, default=0,
                                   help='Maximum number of users device can store')
    user_count = fields.Integer(string='Users Enrolled', readonly=True, copy=False, default=0,
                                help='Current number of users enrolled')
    finger_capacity = fields.Integer(string='Fingerprint Capacity', readonly=True, copy=False, default=0,
                                     help='Maximum number of fingerprints device can store')
    finger_count = fields.Integer(string='Fingerprints Enrolled', readonly=True, copy=False, default=0,
                                  help='Current number of fingerprints stored')
    record_capacity = fields.Integer(string='Record Capacity', readonly=True, copy=False, default=0,
                                     help='Maximum number of attendance records device can store')
    record_count = fields.Integer(string='Records Stored', readonly=True, copy=False, default=0,
                                  help='Current number of attendance records')
    face_capacity = fields.Integer(string='Face Capacity', readonly=True, copy=False, default=0,
                                   help='Maximum number of face templates device can store')
    face_count = fields.Integer(string='Faces Enrolled', readonly=True, copy=False, default=0,
                                help='Current number of face templates stored')

    # Computed Storage Fields
    user_usage_percent = fields.Float(string='User Storage %', compute='_compute_usage_percent',
                                      store=True, help='Percentage of user capacity used')
    record_usage_percent = fields.Float(string='Record Storage %', compute='_compute_usage_percent',
                                        store=True, help='Percentage of record capacity used')
    storage_warning = fields.Boolean(string='Storage Warning', compute='_compute_storage_warning',
                                     store=True, help='True if device storage is >80% full')

    # ==================== CONNECTION MODE ====================
    connection_mode = fields.Selection([
        ('direct', 'Direct Connection (PyZK)'),
        ('adms', 'Cloud Connection (ADMS Push)'),
        ('hybrid', 'Hybrid (ADMS Attendance + PyZK Control)'),
    ], string='Connection Mode', default='direct', required=True,
       help='Direct: Odoo connects to device via TCP/IP (same LAN / VPN required).\n'
            'Cloud (ADMS): Device pushes data to Odoo via HTTP (works behind firewalls, cloud-compatible).\n'
            'Hybrid: ADMS for automatic attendance push + PyZK for hardware control (LCD, voice, door).')

    device_serial = fields.Char(
        string='Device Serial Number',
        help='Serial number used for ADMS device matching. '
             'Auto-filled on first ADMS heartbeat, or set manually.')
    adms_last_heartbeat = fields.Datetime(
        string='Last ADMS Heartbeat', readonly=True,
        help='Last time this device contacted the server via ADMS push protocol.')
    adms_status = fields.Selection([
        ('offline', 'Offline'),
        ('online', 'Online'),
    ], string='ADMS Status', compute='_compute_adms_status', store=True,
       help='Online if heartbeat received within the last 5 minutes.')
    adms_push_count = fields.Integer(
        string='ADMS Records Pushed', readonly=True, default=0,
        help='Total attendance records received via ADMS push.')
    adms_command_count = fields.Integer(
        string='Pending Commands', compute='_compute_adms_command_count')

    @api.depends('adms_last_heartbeat')
    def _compute_adms_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.adms_last_heartbeat:
                diff = (now - rec.adms_last_heartbeat).total_seconds()
                rec.adms_status = 'online' if diff < 300 else 'offline'  # 5 min
            else:
                rec.adms_status = 'offline'

    def _compute_adms_command_count(self):
        command_model = self.env['adms.device.command']
        for rec in self:
            rec.adms_command_count = command_model.search_count([
                ('device_id', '=', rec.id),
                ('status', '=', 'pending'),
            ])

    # ==================== EMPLOYEE SMART BUTTON ====================
    employee_biometric_count = fields.Integer(
        string='Employees',
        compute='_compute_employee_biometric_count',
        help='Total active employees (assigned and unassigned)')

    def _compute_employee_biometric_count(self):
        count = self.env['hr.employee'].search_count([('active', '=', True)])
        for rec in self:
            rec.employee_biometric_count = count

    def action_view_biometric_employees(self):
        """Open an editable employee list to manage Device User IDs."""
        self.ensure_one()
        list_view_id = self.env.ref(
            'dotbd_hr_zk_attendance_suite.view_employee_biometric_id_list').id
        return {
            'name': _('Employee Biometric IDs'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'views': [(list_view_id, 'list'), (False, 'form')],
            'domain': [('active', '=', True)],
            'context': {'no_create': False},
        }

    # ==================== ATTENDANCE MODE SETTINGS (Existing) ====================
    attendance_mode = fields.Selection([
        ('traditional', 'Traditional Mode (Use Device Punch Type)'),
        ('auto', 'Auto Mode (Auto Check-in/Check-out)'),
        ('auto_per_day', 'Auto Per Day (First Punch = In, Last Punch = Out)'),
        ('traditional_per_day', 'Traditional Per Day (One Check-in & One Check-out Per Day)'),
    ], string='Attendance Mode', default='traditional', required=True,
       help='Traditional: Uses punch type from device (0=Check-in, 1=Check-out)\n'
            'Auto: Automatically determines Check-in/Check-out based on last attendance, '
            'ignores device punch type. Prevents HR mistakes.\n'
            'Auto Per Day: First punch of the day is check-in, every subsequent punch updates '
            'check-out (last punch = final check-out). One record per employee per day.\n'
            'Traditional Per Day: Uses device punch type but only allows one check-in and '
            'one check-out per employee per day. Subsequent punches are ignored.')

    duplicate_threshold = fields.Integer(
        string='Duplicate Prevention (Minutes)',
        default=2,
        help='Time window in minutes to ignore duplicate punches. '
             'If employee punches multiple times within this period, only first punch is counted. '
             'Default: 2 minutes')

    # ==================== TIME SYNCHRONIZATION SETTINGS (NEW) ====================
    time_sync_method = fields.Selection([
        ('odoo', 'Odoo User Timezone'),
        ('server', 'Server Timezone (UTC)'),
        ('custom', 'Custom Timezone'),
        ('manual', 'Manual Time')
    ], string='Time Sync Method', default='odoo', required=True,
       help='Method to determine the correct time for this device.')

    custom_timezone = fields.Selection('_tz_get', string='Custom Timezone', default='Asia/Dhaka',
                                       help='Select the timezone to use for this device.')

    manual_datetime = fields.Datetime(string='Manual Date & Time',
                                      help='Set an exact date and time to push to the device.')

    effective_timezone = fields.Char(
        string='Effective Device Timezone',
        readonly=True, copy=False,
        help='Timezone the device clock is currently set to. '
             'Auto-updated on every time sync and attendance download. '
             'Used to correctly interpret device timestamps.')

    # ==================== LIVE CAPTURE SETTINGS (NEW - from pyzk) ====================
    live_capture_enabled = fields.Boolean(
        string='Enable Live Capture',
        default=False,
        help='Enable real-time attendance monitoring. When enabled, attendance events '
             'are captured instantly as they happen instead of periodic polling.')
    live_capture_active = fields.Boolean(
        string='Live Capture Running',
        readonly=True,
        default=False,
        copy=False,
        help='Indicates if live capture is currently active')
    live_capture_timeout = fields.Integer(
        string='Live Capture Timeout (seconds)',
        default=60,
        help='Timeout in seconds for live capture. Recommended: 60 seconds.')
    last_live_event_time = fields.Datetime(
        string='Last Live Event',
        readonly=True,
        copy=False,
        help='Timestamp of last captured live event')
    live_events_today = fields.Integer(
        string='Live Events Today',
        readonly=True,
        compute='_compute_live_events_today',
        help='Number of events captured today via live capture')

    # ==================== LCD & AUDIO SETTINGS (NEW - from pyzk) ====================
    lcd_enabled = fields.Boolean(
        string='Enable LCD Messages',
        default=False,
        help='Enable custom LCD messages on device screen')
    lcd_welcome_message = fields.Char(
        string='Welcome Message',
        default='Welcome!',
        help='Message to display on check-in (max 20 chars)')
    lcd_goodbye_message = fields.Char(
        string='Goodbye Message',
        default='Goodbye!',
        help='Message to display on check-out (max 20 chars)')

    audio_enabled = fields.Boolean(
        string='Enable Audio Feedback',
        default=False,
        help='Enable custom audio alerts on device')
    checkin_voice_index = fields.Integer(
        string='Check-in Voice',
        default=0,
        help='Voice index for check-in (0-55). 0=default beep')
    checkout_voice_index = fields.Integer(
        string='Check-out Voice',
        default=0,
        help='Voice index for check-out (0-55). 0=default beep')
    error_voice_index = fields.Integer(
        string='Error Voice',
        default=1,
        help='Voice index for errors (0-55). 1=error beep')

    # ==================== DOOR CONTROL SETTINGS (NEW - from pyzk) ====================
    door_control_enabled = fields.Boolean(
        string='Enable Door Control',
        default=False,
        help='Enable door unlock control via device')
    default_unlock_duration = fields.Integer(
        string='Default Unlock Duration (seconds)',
        default=3,
        help='Default duration in seconds to keep door unlocked')
    current_lock_state = fields.Selection([
        ('locked', 'Locked'),
        ('unlocked', 'Unlocked'),
        ('unknown', 'Unknown')
    ], string='Door Lock State', default='unknown', readonly=True,
       help='Current door lock status')

    # ==================== LOG & ATTENDANCE TRACKING ====================
    device_log_ids = fields.One2many(
        'biometric.device.log', 'device_id', string='Device Logs')
    device_log_count = fields.Integer(
        string='Log Count', compute='_compute_device_log_count')
    device_attendance_ids = fields.One2many(
        'zk.machine.attendance', 'device_id', string='Device Attendance Records')
    device_attendance_count = fields.Integer(
        string='Attendance Count', compute='_compute_device_attendance_count')

    # ==================== DEVICE STATUS ====================
    device_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('unknown', 'Unknown')
    ], string='Device Status', default='unknown', readonly=True, compute='_compute_device_status',
       store=True, help='Current device connection status')
    last_online_time = fields.Datetime(string='Last Online', readonly=True, copy=False)

    # ==================== COMPUTED FIELDS ====================

    def _compute_device_log_count(self):
        """Count logs for each device"""
        groups = self.env['biometric.device.log'].sudo()._read_group(
            [('device_id', 'in', self.ids)],
            ['device_id'], ['__count'],
        )
        mapped = {device.id: count for device, count in groups}
        for device in self:
            device.device_log_count = mapped.get(device.id, 0)

    def _compute_device_attendance_count(self):
        """Count attendance records for each device"""
        groups = self.env['zk.machine.attendance'].sudo()._read_group(
            [('device_id', 'in', self.ids)],
            ['device_id'], ['__count'],
        )
        mapped = {device.id: count for device, count in groups}
        for device in self:
            device.device_attendance_count = mapped.get(device.id, 0)

    @api.depends('user_capacity', 'user_count', 'record_capacity', 'record_count')
    def _compute_usage_percent(self):
        """Calculate storage usage percentage"""
        for device in self:
            # User storage %
            if device.user_capacity > 0:
                device.user_usage_percent = round((device.user_count / device.user_capacity) * 100, 2)
            else:
                device.user_usage_percent = 0.0

            # Record storage %
            if device.record_capacity > 0:
                device.record_usage_percent = round((device.record_count / device.record_capacity) * 100, 2)
            else:
                device.record_usage_percent = 0.0

    @api.depends('record_usage_percent', 'user_usage_percent')
    def _compute_storage_warning(self):
        """Check if device storage is critical (>80%)"""
        for device in self:
            device.storage_warning = (
                device.record_usage_percent > 80 or
                device.user_usage_percent > 80
            )

    @api.depends('last_online_time')
    def _compute_device_status(self):
        """Determine device status based on last online time"""
        for device in self:
            if not device.last_online_time:
                device.device_status = 'unknown'
            else:
                time_diff = fields.Datetime.now() - device.last_online_time
                if time_diff.total_seconds() < 300:  # 5 minutes
                    device.device_status = 'online'
                else:
                    device.device_status = 'offline'

    def _compute_live_events_today(self):
        """Count live events captured today"""
        for device in self:
            if device.live_capture_enabled:
                today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0)
                count = self.env['zk.machine.attendance'].search_count([
                    ('address_id', '=', device.address_id.id if device.address_id else False),
                    ('punching_time', '>=', today_start)
                ])
                device.live_events_today = count
            else:
                device.live_events_today = 0

    # ==================== HELPER METHODS ====================

    @api.model
    def _tz_get(self):
        return [(x, x) for x in pytz.all_timezones]

    def _get_device_password(self):
        """Get device password or return default value (0)"""
        self.ensure_one()
        if self.device_password:
            try:
                return int(self.device_password)
            except ValueError:
                return self.device_password
        return 0

    def _get_device_timezone(self):
        """Return the timezone string this device's clock should be running in,
        based on the configured time_sync_method."""
        self.ensure_one()
        if self.time_sync_method == 'server':
            return 'UTC'
        elif self.time_sync_method == 'custom' and self.custom_timezone:
            return self.custom_timezone
        elif self.time_sync_method == 'manual':
            return 'UTC'
        else:  # 'odoo' mode
            # On Odoo.sh, cron jobs run in UTC with empty context and no user tz.
            # Fall through a reliable chain before resorting to UTC.
            return (self.env.context.get('tz')
                    or self.env.user.tz
                    or self.company_id.partner_id.tz
                    or self.effective_timezone   # last known good device tz
                    or 'UTC')

    def _compute_expected_device_time(self):
        """Compute the naive datetime the device clock should show right now,
        based on the configured time_sync_method."""
        self.ensure_one()
        if self.time_sync_method == 'manual' and self.manual_datetime:
            return fields.Datetime.context_timestamp(
                self, self.manual_datetime).replace(tzinfo=None)
        device_tz = self._get_device_timezone()
        utc_now = pytz.utc.localize(fields.Datetime.now())
        local_now = utc_now.astimezone(pytz.timezone(device_tz))
        return local_now.replace(tzinfo=None)

    def _auto_sync_time(self, conn):
        """Check device time and auto-sync if drifted beyond 30 seconds.
        Also persists the effective_timezone on the device record.
        Returns the timezone string the device clock is running in.
        """
        self.ensure_one()
        device_tz_str = self._get_device_timezone()
        expected_time = self._compute_expected_device_time()

        try:
            device_time = conn.get_time()
            if device_time:
                drift = abs((expected_time - device_time).total_seconds())
                if drift > 30:  # More than 30 seconds drift
                    _logger.info(
                        "Device %s time drift: %.1fs (device=%s, expected=%s). Auto-syncing...",
                        self.name, drift, device_time, expected_time)
                    conn.set_time(expected_time)
                    _logger.info("Device %s time auto-synced to %s (%s)",
                                 self.name, expected_time, device_tz_str)
                else:
                    _logger.debug(
                        "Device %s time OK (drift: %.1fs)", self.name, drift)
            else:
                # Can't read time, force sync
                conn.set_time(expected_time)
                _logger.info(
                    "Device %s time could not be read, forced sync to %s",
                    self.name, expected_time)
        except Exception as e:
            _logger.warning(
                "Device %s auto-sync time failed: %s. Proceeding with download.",
                self.name, e)

        # Persist the effective timezone
        self.write({'effective_timezone': device_tz_str})
        return device_tz_str

    def device_connect(self, zk):
        """Connect to device"""
        try:
            conn = zk.connect()
            if conn:
                self.last_online_time = fields.Datetime.now()
            return conn
        except Exception as e:
            _logger.error(f"Connection failed for device {self.name}: {str(e)}")
            return False

    # ==================== EXISTING METHODS (Enhanced) ====================

    def action_test_connection(self):
        """Test connection and retrieve device info"""
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=30,
                password=device_password, ommit_ping=True)
        try:
            conn = self.device_connect(zk)
            if conn:
                # Also fetch basic device info on successful connection
                try:
                    self.firmware_version = conn.get_firmware_version()
                    self.serial_number = conn.get_serialnumber()
                except Exception as e:
                    _logger.debug("Could not fetch device info for %s: %s", self.name, e)
                finally:
                    conn.disconnect()

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'Successfully Connected to {self.name}',
                        'type': 'success',
                        'sticky': False
                    }
                }
        except Exception as error:
            raise ValidationError(f'Connection failed: {error}')

    def action_set_timezone(self):
        """Sync server timezone to device using configured time_sync_method."""
        for info in self:
            machine_ip = info.device_ip
            zk_port = info.port_number
            device_password = info._get_device_password()
            try:
                zk = ZK(machine_ip, port=zk_port, timeout=15,
                        password=device_password,
                        force_udp=False, ommit_ping=True)
            except NameError:
                raise UserError(
                    _("Pyzk module not Found. Please install it with 'pip3 install pyzk'."))

            conn = self.device_connect(zk)
            if conn:
                try:
                    device_tz_str = info._get_device_timezone()
                    expected_time = info._compute_expected_device_time()
                    conn.set_time(expected_time)
                    info.effective_timezone = device_tz_str
                    _logger.info(
                        "Device %s time synced to %s (tz=%s)",
                        info.name, expected_time, device_tz_str)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'message': f'Time synchronized successfully on {self.name} ({device_tz_str})',
                            'type': 'success',
                            'sticky': False
                        }
                    }
                finally:
                    conn.disconnect()
            else:
                raise UserError(_("Unable to connect to device. Please check connection."))

    def action_restart_device(self):
        """Restart the device"""
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=device_password, force_udp=False, ommit_ping=True)
        conn = self.device_connect(zk)
        if conn:
            try:
                conn.restart()
                self.message_post(body=f"Device {self.name} restarted successfully")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'Device {self.name} is restarting...',
                        'type': 'warning',
                        'sticky': False
                    }
                }
            finally:
                conn.disconnect()

    # ==================== NEW PYZK METHODS - DEVICE INFORMATION ====================

    def action_refresh_device_info(self):
        """
        Refresh all device information from the device
        Uses pyzk methods: get_firmware_version, get_serialnumber, get_platform,
        get_mac, get_device_name, get_face_version, get_fp_version, get_pin_width,
        get_network_params, read_sizes
        """
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=30,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device. Please check IP address and port.'))

        try:
            # Get device information
            firmware = conn.get_firmware_version()
            serial = conn.get_serialnumber()
            platform = conn.get_platform()
            mac = conn.get_mac()
            device_name = conn.get_device_name()
            pin_width = conn.get_pin_width()

            # Get face and fingerprint versions
            try:
                face_ver = conn.get_face_version()
            except Exception:
                face_ver = 'N/A'

            try:
                fp_ver = conn.get_fp_version()
            except Exception:
                fp_ver = 'N/A'

            # Get network parameters
            try:
                network_params = conn.get_network_params()
                if network_params and isinstance(network_params, dict):
                    network_ip = network_params.get('ip', '')
                    network_mask = network_params.get('mask', '')
                    network_gateway = network_params.get('gateway', '')
                else:
                    network_ip = self.device_ip
                    network_mask = 'N/A'
                    network_gateway = 'N/A'
            except Exception:
                network_ip = self.device_ip
                network_mask = 'N/A'
                network_gateway = 'N/A'

            # Get capacity information
            sizes = {}
            try:
                raw_sizes = conn.read_sizes()
                _logger.info(f"Device {self.name} read_sizes() returned: {raw_sizes}")

                if raw_sizes and isinstance(raw_sizes, dict):
                    sizes = raw_sizes
                else:
                    _logger.warning(f"Device {self.name} read_sizes() returned invalid data: {raw_sizes}")
            except Exception as e:
                _logger.error(f"Device {self.name} read_sizes() failed: {str(e)}")

            # Try to get user count from get_users if read_sizes failed
            users_list = []
            if not sizes:
                try:
                    users_list = conn.get_users()
                    if users_list:
                        _logger.info(f"Device {self.name} has {len(users_list)} users via get_users()")
                except Exception as e:
                    _logger.error(f"Device {self.name} get_users() failed: {str(e)}")

            # Update device record
            update_vals = {
                'firmware_version': firmware,
                'serial_number': serial,
                'platform': platform,
                'mac_address': mac,
                'device_name_from_device': device_name,
                'face_version': face_ver,
                'fp_version': fp_ver,
                'pin_width': pin_width,
                'network_ip': network_ip,
                'network_mask': network_mask,
                'network_gateway': network_gateway,
            }

            # Add capacity info if available
            if sizes:
                update_vals.update({
                    'user_capacity': sizes.get('users', 0),
                    'user_count': sizes.get('users_cap', 0) or len(users_list),
                    'finger_capacity': sizes.get('fingers', 0),
                    'finger_count': sizes.get('fingers_cap', 0),
                    'record_capacity': sizes.get('records', 0),
                    'record_count': sizes.get('records_cap', 0),
                    'face_capacity': sizes.get('faces', 0),
                    'face_count': sizes.get('faces_cap', 0),
                })
            elif users_list:
                # If read_sizes() failed but we got users, at least update user count
                update_vals['user_count'] = len(users_list)

            self.write(update_vals)

            # Send alert if storage is critical
            if self.storage_warning:
                self._send_storage_alert()

            # Log activity
            message_body = f"Device information refreshed successfully.\n" \
                          f"Firmware: {firmware}\n" \
                          f"Serial: {serial}\n"

            if sizes:
                message_body += f"Users: {sizes.get('users_cap', 0)}/{sizes.get('users', 0)}\n" \
                               f"Records: {sizes.get('records_cap', 0)}/{sizes.get('records', 0)}"
            elif users_list:
                message_body += f"Users: {len(users_list)} (capacity info not available)"
            else:
                message_body += "Capacity information not supported by this device"

            self.message_post(body=message_body)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Device information refreshed successfully!',
                    'type': 'success',
                    'sticky': False
                }
            }

        except Exception as e:
            raise UserError(_(f'Failed to retrieve device information: {str(e)}'))
        finally:
            conn.disconnect()

    def _send_storage_alert(self):
        """Send storage warning notification"""
        self.ensure_one()
        self.message_post(
            subject='Device Storage Warning',
            body=f'Device {self.name} storage is critical!\n\n'
                 f'User Storage: {self.user_usage_percent:.1f}% '
                 f'({self.user_count}/{self.user_capacity})\n'
                 f'Record Storage: {self.record_usage_percent:.1f}% '
                 f'({self.record_count}/{self.record_capacity})\n\n'
                 f'Please clear old records to prevent data loss.',
            message_type='notification',
            subtype_xmlid='mail.mt_comment'
        )

    # ==================== CONTINUED IN NEXT PART ====================
    # ==================== NEW PYZK METHODS - LIVE CAPTURE ====================

    def action_start_live_capture(self):
        """
        Start real-time attendance monitoring
        Uses pyzk method: live_capture()
        This captures attendance events in REAL-TIME as they happen
        """
        self.ensure_one()

        if self.live_capture_active:
            raise UserError(_('Live capture is already running for this device!'))

        # Start live capture in background thread
        thread = threading.Thread(target=self._live_capture_worker)
        thread.daemon = True
        thread.start()

        self.write({'live_capture_active': True})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Live capture started on {self.name}',
                'type': 'success',
                'sticky': False
            }
        }

    def action_stop_live_capture(self):
        """Stop live capture"""
        self.ensure_one()
        self.write({'live_capture_enabled': False, 'live_capture_active': False})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Live capture stopped on {self.name}',
                'type': 'warning',
                'sticky': False
            }
        }

    def _live_capture_worker(self):
        """
        Background worker for live capture
        Runs in separate thread to capture real-time events
        IMPORTANT: This creates its own database cursor for thread safety
        """
        device_id = self.id
        device_name = self.name
        device_ip = self.device_ip
        port_number = self.port_number
        device_password = self._get_device_password()
        live_capture_timeout = self.live_capture_timeout

        # Guard: live capture requires a real IP (ADMS-only devices have no IP)
        if not device_ip or device_ip in ('0.0.0.0', 'False', ''):
            _logger.error(
                "Live capture aborted for %s: no device IP configured. "
                "Live capture requires a direct TCP/IP connection.",
                device_name)
            with self.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['biometric.device.details'].browse(device_id).write(
                    {'live_capture_active': False})
                cr.commit()
            return

        # Create ZK connection
        zk = ZK(device_ip, port=port_number, timeout=30,
                password=device_password, ommit_ping=True)

        # Connect to device
        try:
            conn = zk.connect()
            if not conn:
                _logger.error(f"Live capture failed: Unable to connect to {device_name}")
                # Create new cursor for thread-safe write
                with self.pool.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    device = env['biometric.device.details'].browse(device_id)
                    device.write({'live_capture_active': False})
                    cr.commit()
                return
        except Exception as e:
            _logger.error(f"Live capture connection failed for {device_name}: {str(e)}")
            return

        try:
            conn.disable_device()

            _logger.info(f"Live capture started for device: {device_name}")

            # Check if live_capture method exists
            if not hasattr(conn, 'live_capture'):
                _logger.error(f"Device {device_name} does not support live_capture() method")
                raise UserError(_('Live capture is not supported by this device or PyZK version'))

            # Start live capture loop
            for attendance in conn.live_capture(new_timeout=live_capture_timeout):
                # Create new cursor for each event (thread-safe)
                with self.pool.cursor() as cr:
                    try:
                        env = api.Environment(cr, SUPERUSER_ID, {})
                        device = env['biometric.device.details'].browse(device_id)

                        # Check if we should stop
                        if not device.live_capture_enabled:
                            conn.end_live_capture = True
                            _logger.info(f"Live capture stop requested for {device_name}")
                            break

                        if attendance is None:
                            # No new events, continue listening
                            continue

                        _logger.info(f"Live event captured: User={attendance.user_id}, "
                                   f"Time={attendance.timestamp}, Punch={attendance.punch}")

                        # Process attendance event immediately
                        device._process_live_attendance_with_env(env, attendance)

                        # Update last event time
                        device.write({'last_live_event_time': fields.Datetime.now()})

                        # Send real-time notification via bus
                        device._send_live_event_notification_with_env(env, attendance)

                        # Commit the transaction
                        cr.commit()

                    except Exception as e:
                        _logger.error(f"Error processing live event: {str(e)}")
                        cr.rollback()

        except AttributeError as e:
            _logger.error(f"Live capture not supported on {device_name}: {str(e)}")
        except Exception as e:
            _logger.error(f"Live capture error on {device_name}: {str(e)}")
        finally:
            try:
                conn.enable_device()
                conn.disconnect()
            except Exception as e:
                _logger.debug("Error during live capture cleanup for %s: %s", device_name, e)

            # Update device status with new cursor
            with self.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                device = env['biometric.device.details'].browse(device_id)
                device.write({'live_capture_active': False})
                cr.commit()

            _logger.info(f"Live capture stopped for device: {device_name}")

    def _process_live_attendance_with_env(self, env, attendance):
        """Process a single live attendance event.
        Accepts explicit environment for thread-safe operation.
        Converts device local time to UTC, runs stale check, updates zk record."""
        # Find employee by device ID
        employee = env['hr.employee'].search([
            ('device_id_num', '=', attendance.user_id)
        ], limit=1)

        if not employee:
            _logger.warning(f"Live capture: Unknown user ID {attendance.user_id}")
            return

        # Convert device local timestamp to UTC (same as action_download_attendance)
        device_tz_str = self._get_device_timezone()
        try:
            local_tz = pytz.timezone(device_tz_str)
        except pytz.UnknownTimeZoneError:
            local_tz = pytz.UTC

        raw_time = attendance.timestamp  # device naive local time
        if raw_time.tzinfo is None:
            local_dt = local_tz.localize(raw_time, is_dst=None)
        else:
            local_dt = raw_time
        utc_dt = local_dt.astimezone(pytz.utc)
        atten_time_str = fields.Datetime.to_string(utc_dt)  # naive UTC string for Odoo

        # Create ZK attendance record (sanitize device values to prevent ValueError)
        zk_att = env['zk.machine.attendance'].sudo().create({
            'employee_id': employee.id,
            'device_id': self.id,
            'device_id_num': attendance.user_id,
            'attendance_type': ZkMachineAttendance._sanitize_attendance_type(attendance.status),
            'punch_type': ZkMachineAttendance._sanitize_punch_type(attendance.punch),
            'punching_time': atten_time_str,
            'address_id': self.address_id.id if self.address_id else False,
            'source': 'live',
        })

        # Handle stale attendance (open > 24 hours)
        hr_attendance = env['hr.attendance'].sudo()
        att_var = hr_attendance.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ])
        if att_var:
            atten_aware = pytz.UTC.localize(utc_dt.replace(tzinfo=None))
            for old_att in att_var:
                old_check_in = old_att.check_in
                if old_check_in.tzinfo is None:
                    old_check_in = pytz.UTC.localize(old_check_in)
                hours_open = (atten_aware - old_check_in).total_seconds() / 3600.0
                if hours_open > 24:
                    check_in_date = old_att.check_in.date()
                    auto_checkout = datetime.datetime.combine(
                        check_in_date, datetime.time(23, 59, 59))
                    auto_checkout_utc = local_tz.localize(auto_checkout).astimezone(
                        pytz.UTC).replace(tzinfo=None)
                    old_att.write({'check_out': auto_checkout_utc})
                    _logger.warning(
                        f"Live capture: Auto-closed stale attendance for {employee.name} "
                        f"(check-in: {old_att.check_in}, auto check-out: {auto_checkout_utc})")

        # Create/update hr.attendance based on mode
        if self.attendance_mode == 'auto':
            odoo_action, att_record = self._process_auto_attendance(
                employee, atten_time_str, hr_attendance)
        elif self.attendance_mode == 'auto_per_day':
            odoo_action, att_record = self._process_auto_per_day_attendance(
                employee, atten_time_str, hr_attendance)
        elif self.attendance_mode == 'traditional_per_day':
            odoo_action, att_record = self._process_traditional_per_day_attendance(
                employee, atten_time_str, attendance.punch, hr_attendance)
        else:
            odoo_action, att_record = self._process_traditional_attendance(
                employee, atten_time_str, attendance.punch, hr_attendance)

        if odoo_action and att_record:
            zk_att.write({
                'hr_attendance_id': att_record.id,
                'processed': True,
                'odoo_punch_type': odoo_action,
            })

        _logger.info(f"Live attendance processed for employee: {employee.name}")

        # Display LCD message if enabled
        if self.lcd_enabled:
            self._display_attendance_lcd_message(employee, attendance.punch)

        # Play audio if enabled
        if self.audio_enabled:
            self._play_attendance_audio(attendance.punch)

        _logger.info(f"Live capture: Processed attendance for {employee.name} at {atten_time_str} (UTC)")

    def _send_live_event_notification(self, attendance):
        """Send real-time notification via Odoo bus"""
        try:
            employee = self.env['hr.employee'].search([('device_id_num', '=', attendance.user_id)], limit=1)
            if employee:
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id,
                    'attendance_live_event',
                    {
                        'device': self.name,
                        'employee': employee.name,
                        'time': str(attendance.timestamp),
                        'type': 'Check-in' if attendance.punch == 0 else 'Check-out'
                    }
                )
        except Exception as e:
            _logger.error(f"Failed to send live event notification: {str(e)}")

    def _send_live_event_notification_with_env(self, env, attendance):
        """
        Send real-time notification via Odoo bus
        This version accepts explicit environment for thread-safe operation
        """
        try:
            employee = env['hr.employee'].search([('device_id_num', '=', attendance.user_id)], limit=1)
            if employee:
                # Send bus notification to all users
                env['bus.bus']._sendmany([
                    (env.user.partner_id, 'attendance_live_event', {
                        'device': self.name,
                        'employee': employee.name,
                        'time': str(attendance.timestamp),
                        'type': 'Check-in' if attendance.punch == 0 else 'Check-out'
                    })
                ])
                _logger.info(f"Live event notification sent for {employee.name}")
        except Exception as e:
            _logger.error(f"Failed to send live event notification: {str(e)}")

    # ==================== NEW PYZK METHODS - LCD MESSAGES ====================

    def action_test_lcd(self):
        """
        Test LCD display with custom message
        Uses pyzk methods: write_lcd(), clear_lcd()
        """
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            # Check if LCD methods are available
            if not hasattr(conn, 'clear_lcd') or not hasattr(conn, 'write_lcd'):
                raise UserError(_('LCD display methods are not supported by this device or PyZK version'))

            # Clear LCD first
            conn.clear_lcd()

            # Write test message
            conn.write_lcd(line_number=1, text="Test Message")
            conn.write_lcd(line_number=2, text=f"From: {self.env.user.name[:15]}")

            self.message_post(body="LCD test message sent successfully")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Test message displayed on device LCD',
                    'type': 'success',
                    'sticky': False
                }
            }
        except AttributeError as e:
            raise UserError(_('LCD display is not supported by this device or PyZK version'))
        finally:
            conn.disconnect()

    def action_clear_lcd(self):
        """Clear LCD display"""
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            if not hasattr(conn, 'clear_lcd'):
                raise UserError(_('LCD display is not supported by this device or PyZK version'))

            conn.clear_lcd()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'LCD cleared successfully',
                    'type': 'success',
                    'sticky': False
                }
            }
        except AttributeError as e:
            raise UserError(_('LCD display is not supported by this device or PyZK version'))
        finally:
            conn.disconnect()

    def _display_attendance_lcd_message(self, employee, punch_type):
        """Display personalized LCD message on attendance"""
        if not self.lcd_enabled:
            return

        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=5,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if conn:
            try:
                # Check if LCD methods are available
                if hasattr(conn, 'write_lcd'):
                    # Display employee name and message
                    message = self.lcd_welcome_message if punch_type == 0 else self.lcd_goodbye_message
                    conn.write_lcd(1, employee.name[:20])
                    conn.write_lcd(2, message[:20])
            except Exception as e:
                _logger.debug("LCD write failed for device %s: %s", self.name, e)
            finally:
                conn.disconnect()

    # ==================== NEW PYZK METHODS - AUDIO FEEDBACK ====================

    def action_test_voice(self):
        """
        Test device voice/audio feedback
        Uses pyzk method: test_voice(index)
        Available indices: 0-55 (different sounds/voices)
        """
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            if not hasattr(conn, 'test_voice'):
                raise UserError(_('Audio/voice feedback is not supported by this device or PyZK version'))

            # Test with check-in voice
            conn.test_voice(index=self.checkin_voice_index)

            self.message_post(body=f"Voice test played (index: {self.checkin_voice_index})")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Playing voice index {self.checkin_voice_index}',
                    'type': 'success',
                    'sticky': False
                }
            }
        except AttributeError as e:
            raise UserError(_('Audio/voice feedback is not supported by this device or PyZK version'))
        finally:
            conn.disconnect()

    def _play_attendance_audio(self, punch_type):
        """Play audio feedback on attendance"""
        if not self.audio_enabled:
            return

        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=5,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if conn:
            try:
                if hasattr(conn, 'test_voice'):
                    voice_index = self.checkin_voice_index if punch_type == 0 else self.checkout_voice_index
                    conn.test_voice(index=voice_index)
            except Exception as e:
                _logger.debug("Voice feedback failed for device %s: %s", self.name, e)
            finally:
                conn.disconnect()

    # ==================== NEW PYZK METHODS - DOOR CONTROL ====================

    def action_unlock_door(self):
        """
        Unlock door for configured duration
        Uses pyzk method: unlock(time)
        """
        self.ensure_one()

        if not self.door_control_enabled:
            raise UserError(_('Door control is not enabled for this device'))

        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            # Unlock door
            conn.unlock(time=self.default_unlock_duration)

            # Update lock state
            self.write({'current_lock_state': 'unlocked'})

            # Log activity
            self.message_post(
                body=f"Door unlocked by {self.env.user.name} for {self.default_unlock_duration} seconds"
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Door unlocked for {self.default_unlock_duration} seconds',
                    'type': 'success',
                    'sticky': False
                }
            }
        finally:
            conn.disconnect()

    def action_get_lock_state(self):
        """
        Get current door lock state
        Uses pyzk method: get_lock_state()
        """
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=15,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            if not hasattr(conn, 'get_lock_state'):
                raise UserError(_('Door lock status check is not supported by this device or PyZK version'))

            lock_state = conn.get_lock_state()
            state = 'locked' if lock_state else 'unlocked'
            self.write({'current_lock_state': state})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Door is currently: {state.upper()}',
                    'type': 'info',
                    'sticky': False
                }
            }
        except AttributeError as e:
            raise UserError(_('Door lock status check is not supported by this device or PyZK version'))
        finally:
            conn.disconnect()

    # ==================== NEW PYZK METHODS - USER MANAGEMENT ====================

    def action_sync_users_to_device(self):
        """
        Sync all Odoo employees to device
        Uses pyzk method: set_user()
        """
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=30,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            conn.disable_device()

            # Get all employees with device ID
            employees = self.env['hr.employee'].search([
                ('device_id_num', '!=', False),
                ('company_id', '=', self.company_id.id)
            ])

            # Get all current users from device to map user_id -> uid
            try:
                device_users = conn.get_users()
                user_map = {str(u.user_id): u.uid for u in device_users} if device_users else {}
                
                # Log any users found on the device that aren't mapped in Odoo
                odoo_employee_ids = [str(e.device_id_num) for e in employees]
                for unknown_user in (device_users or []):
                    if str(unknown_user.user_id) not in odoo_employee_ids:
                        self.env['biometric.device.log'].sudo().create({
                            'device_id': self.id,
                            'log_type': 'sync',
                            'status': 'warning',
                            'error_message': f'Unmapped User on Device: {unknown_user.name} (ID: {unknown_user.user_id})',
                            'details': 'This user exists on the biometric device but has no linked hr.employee in Odoo.',
                        })
            except Exception as e:
                _logger.warning(f"Failed to fetch existing users prior to sync: {e}")
                user_map = {}

            enrolled_count = 0
            for employee in employees:
                try:
                    # Get existing internal uid if user already exists on device
                    internal_uid = user_map.get(str(employee.device_id_num))
                    
                    # Create/update user on device safely without destroying fingerprint links
                    conn.set_user(
                        uid=internal_uid,  # Use existing UID if present, otherwise let device auto-assign
                        name=employee.name[:24],  # Max 24 chars
                        privilege=0,  # 0=User, 14=Admin
                        password='',
                        group_id='',
                        user_id=str(employee.device_id_num),
                        card=0
                    )
                    enrolled_count += 1
                    _logger.info(f"Synced {employee.name} to device {self.name}")
                except Exception as e:
                    _logger.error(f"Failed to sync {employee.name}: {str(e)}")

            # Refresh device info to get updated user count
            sizes = conn.read_sizes()
            if sizes and isinstance(sizes, dict):
                self.write({
                    'user_count': sizes.get('users_cap', 0),
                })

            self.message_post(
                body=f"Successfully synced {enrolled_count} employees to device"
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Synced {enrolled_count} employees to device',
                    'type': 'success',
                    'sticky': False
                }
            }

        finally:
            conn.enable_device()
            conn.disconnect()

    def action_view_attendance_records(self):
        """View all attendance records downloaded from this device"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Attendance Records - {self.name}',
            'res_model': 'zk.machine.attendance',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

    def action_view_device_logs(self):
        """View download/operation logs for this device"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Device Logs - {self.name}',
            'res_model': 'biometric.device.log',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

    def action_view_enrolled_users(self):
        """View list of users enrolled on this device"""
        self.ensure_one()
        # Get all employees with device ID
        employees = self.env['hr.employee'].search([
            ('device_id_num', '!=', False),
            ('company_id', '=', self.company_id.id)
        ])

        return {
            'type': 'ir.actions.act_window',
            'name': f'Enrolled Users - {self.name}',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', employees.ids)],
            'context': {
                'default_company_id': self.company_id.id,
                'search_default_group_department': 1,
            },
        }

    # ==================== BIOMETRIC TEMPLATE MANAGEMENT ====================

    def action_backup_templates(self):
        """
        Backup all biometric templates from device
        Uses pyzk method: get_templates()
        """
        self.ensure_one()
        device_password = self._get_device_password()
        zk = ZK(self.device_ip, port=self.port_number, timeout=60,
                password=device_password, ommit_ping=True)

        conn = self.device_connect(zk)
        if not conn:
            raise UserError(_('Unable to connect to device'))

        try:
            if not hasattr(conn, 'get_templates'):
                raise UserError(_('Template backup is not supported by this device or PyZK version'))

            # Get all templates from device
            templates = conn.get_templates()

            if not templates:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No templates found on device',
                        'type': 'warning',
                        'sticky': False
                    }
                }

            # Count templates by type
            # PyZK templates have different attributes depending on the version
            # Try multiple attribute names for categorization
            finger_count = 0
            face_count = 0

            for t in templates:
                # Log first template attributes for debugging
                if templates.index(t) == 0:
                    _logger.info(f"Template attributes: {dir(t)}")
                    _logger.info(f"Template sample: uid={getattr(t, 'uid', 'N/A')}, "
                                f"fid={getattr(t, 'fid', 'N/A')}, "
                                f"size={getattr(t, 'size', 'N/A')}, "
                                f"mark={getattr(t, 'mark', 'N/A')}")

                # Check various attribute combinations
                if hasattr(t, 'mark'):
                    if t.mark == 1:  # Finger
                        finger_count += 1
                    elif t.mark == 12:  # Face
                        face_count += 1
                elif hasattr(t, 'fid'):
                    # fid (finger ID) 0-9 are fingers, 10+ are faces
                    if t.fid < 10:
                        finger_count += 1
                    else:
                        face_count += 1
                else:
                    # Default to fingerprint if unknown
                    finger_count += 1

            self.message_post(
                body=f"Biometric templates backed up successfully.\n"
                     f"Fingerprints: {finger_count}\n"
                     f"Faces: {face_count}\n"
                     f"Total templates: {len(templates)}"
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Backed up {len(templates)} templates ({finger_count} fingerprints, {face_count} faces)',
                    'type': 'success',
                    'sticky': False
                }
            }
        except AttributeError:
            raise UserError(_('Template backup is not supported by this device or PyZK version'))
        except Exception as e:
            raise UserError(_(f'Failed to backup templates: {str(e)}'))
        finally:
            conn.disconnect()

    def action_verify_employee_biometric(self):
        """
        Verify employee biometric against device
        Uses pyzk method: verify_user()
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Verify Employee Biometric',
            'res_model': 'hr.employee',
            'view_mode': 'list',
            'domain': [('device_id_num', '!=', False), ('company_id', '=', self.company_id.id)],
            'context': {
                'default_company_id': self.company_id.id,
                'biometric_device_id': self.id,
            },
            'target': 'new',
        }

    # ==================== DELETE OPERATIONS (COMMENTED FOR SAFETY) ====================

    # UNCOMMENT BELOW METHODS ONLY WHEN EXPLICITLY REQUESTED BY USER
    # These operations are DESTRUCTIVE and cannot be undone!

    # def action_clear_attendance(self):
    #     """
    #     ⚠️ DANGER: Clear ALL attendance records from device
    #     Uses pyzk method: clear_attendance()
    #     """
    #     self.ensure_one()
    #     device_password = self._get_device_password()
    #     zk = ZK(self.device_ip, port=self.port_number, timeout=30,
    #             password=device_password, ommit_ping=True)
    #
    #     conn = self.device_connect(zk)
    #     if not conn:
    #         raise UserError(_('Unable to connect to device'))
    #
    #     try:
    #         conn.disable_device()
    #         attendance = conn.get_attendance()
    #
    #         if attendance:
    #             # Clear attendance from device
    #             conn.clear_attendance()
    #
    #             # Also clear from zk.machine.attendance table
    #             self.env['zk.machine.attendance'].search([
    #                 ('address_id', '=', self.address_id.id if self.address_id else False)
    #             ]).unlink()
    #
    #             # Update record count
    #             sizes = conn.read_sizes()
    #             self.write({'record_count': sizes.get('records_cap', 0)})
    #
    #             self.message_post(
    #                 subject='⚠️ Attendance Records Cleared',
    #                 body=f"ALL attendance records cleared from device by {self.env.user.name}",
    #                 message_type='notification'
    #             )
    #
    #             return {
    #                 'type': 'ir.actions.client',
    #                 'tag': 'display_notification',
    #                 'params': {
    #                     'message': 'All attendance records cleared from device',
    #                     'type': 'warning',
    #                     'sticky': True
    #                 }
    #             }
    #         else:
    #             raise UserError(_('No attendance records found to clear'))
    #
    #     finally:
    #         conn.enable_device()
    #         conn.disconnect()

    # def action_delete_user_from_device(self, user_id):
    #     """
    #     ⚠️ DANGER: Delete user from device
    #     Uses pyzk method: delete_user()
    #     """
    #     self.ensure_one()
    #     device_password = self._get_device_password()
    #     zk = ZK(self.device_ip, port=self.port_number, timeout=15,
    #             password=device_password, ommit_ping=True)
    #
    #     conn = self.device_connect(zk)
    #     if not conn:
    #         raise UserError(_('Unable to connect to device'))
    #
    #     try:
    #         conn.disable_device()
    #         conn.delete_user(uid=None, user_id=user_id)
    #
    #         # Update user count
    #         sizes = conn.read_sizes()
    #         self.write({'user_count': sizes.get('users_cap', 0)})
    #
    #         self.message_post(
    #             body=f"User {user_id} deleted from device by {self.env.user.name}"
    #         )
    #
    #         return True
    #     finally:
    #         conn.enable_device()
    #         conn.disconnect()

    # def action_clear_all_data(self):
    #     """
    #     ⚠️⚠️⚠️ EXTREME DANGER: Clear ALL data from device (Factory Reset)
    #     Uses pyzk method: clear_data()
    #     This will delete EVERYTHING: users, fingerprints, attendance, face templates
    #     """
    #     self.ensure_one()
    #     device_password = self._get_device_password()
    #     zk = ZK(self.device_ip, port=self.port_number, timeout=30,
    #             password=device_password, ommit_ping=True)
    #
    #     conn = self.device_connect(zk)
    #     if not conn:
    #         raise UserError(_('Unable to connect to device'))
    #
    #     try:
    #         conn.disable_device()
    #         conn.clear_data()
    #
    #         # Reset all capacity counters
    #         self.write({
    #             'user_count': 0,
    #             'finger_count': 0,
    #             'record_count': 0,
    #             'face_count': 0,
    #         })
    #
    #         self.message_post(
    #             subject='⚠️⚠️⚠️ DEVICE FACTORY RESET',
    #             body=f"ALL DATA CLEARED from device {self.name} by {self.env.user.name}<br/>"
    #                  f"Users, fingerprints, attendance records, and face templates deleted.",
    #             message_type='notification'
    #         )
    #
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'message': '⚠️ ALL DATA CLEARED FROM DEVICE',
    #                 'type': 'danger',
    #                 'sticky': True
    #             }
    #         }
    #
    #     finally:
    #         conn.enable_device()
    #         conn.disconnect()

    # def action_delete_user_template(self, uid, temp_id):
    #     """
    #     ⚠️ DANGER: Delete specific fingerprint template
    #     Uses pyzk method: delete_user_template()
    #     """
    #     self.ensure_one()
    #     device_password = self._get_device_password()
    #     zk = ZK(self.device_ip, port=self.port_number, timeout=15,
    #             password=device_password, ommit_ping=True)
    #
    #     conn = self.device_connect(zk)
    #     if not conn:
    #         raise UserError(_('Unable to connect to device'))
    #
    #     try:
    #         conn.disable_device()
    #         conn.delete_user_template(uid=uid, temp_id=temp_id, user_id=None)
    #
    #         # Update finger count
    #         sizes = conn.read_sizes()
    #         self.write({'finger_count': sizes.get('fingers_cap', 0)})
    #
    #         return True
    #     finally:
    #         conn.enable_device()
    #         conn.disconnect()

    # def action_poweroff_device(self):
    #     """
    #     ⚠️ DANGER: Shutdown device
    #     Uses pyzk method: poweroff()
    #     """
    #     self.ensure_one()
    #     device_password = self._get_device_password()
    #     zk = ZK(self.device_ip, port=self.port_number, timeout=15,
    #             password=device_password, ommit_ping=True)
    #
    #     conn = self.device_connect(zk)
    #     if not conn:
    #         raise UserError(_('Unable to connect to device'))
    #
    #     try:
    #         conn.poweroff()
    #
    #         self.message_post(
    #             subject='Device Powered Off',
    #             body=f"Device {self.name} powered off by {self.env.user.name}"
    #         )
    #
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'message': 'Device is powering off...',
    #                 'type': 'warning',
    #                 'sticky': True
    #             }
    #         }
    #
    #     finally:
    #         conn.disconnect()

    # ==================== EXISTING DOWNLOAD METHOD (Keep as is) ====================

    def _is_duplicate_punch(self, employee_id, punch_time, threshold_minutes):
        """Check if this punch is a duplicate within threshold time window"""
        if threshold_minutes <= 0:
            return False

        zk_attendance = self.env['zk.machine.attendance']
        # Odoo 19 requires naive (no tzinfo) datetimes in search domains
        naive_punch = punch_time.replace(tzinfo=None) if punch_time.tzinfo else punch_time
        time_from = naive_punch - datetime.timedelta(minutes=threshold_minutes)
        time_to = naive_punch + datetime.timedelta(minutes=threshold_minutes)

        duplicate = zk_attendance.search([
            ('employee_id', '=', employee_id),
            ('punching_time', '>=', time_from),
            ('punching_time', '<=', time_to),
        ], limit=1)

        return bool(duplicate)

    def _process_traditional_attendance(self, employee, atten_time, punch_type, hr_attendance):
        """Process attendance in traditional mode (uses device punch type).
        Returns (odoo_action, hr_attendance_record) or (None, None) if no action taken."""
        # Always use sudo() to bypass record rules (multi-company, etc.)
        hr_att_sudo = hr_attendance.sudo()
        att_var = hr_att_sudo.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False)
        ])

        if punch_type == 0:  # check-in from device
            if not att_var:
                new_att = hr_att_sudo.create({
                    'employee_id': employee.id,
                    'check_in': atten_time
                })
                _logger.info(f"Traditional mode: Check-in created for {employee.name}")
                return ('check_in', new_att)
        elif punch_type == 1:  # check-out from device
            if len(att_var) == 1:
                att_var.write({'check_out': atten_time})
                _logger.info(f"Traditional mode: Check-out added for {employee.name}")
                return ('check_out', att_var)
        return (None, None)

    def _process_auto_attendance(self, employee, atten_time, hr_attendance):
        """Process attendance in auto mode (ignores device punch type, auto-determines check-in/check-out).
        Returns (odoo_action, hr_attendance_record)."""
        # Always use sudo() to bypass record rules — otherwise the search
        # may return empty and EVERY punch becomes a check-in.
        hr_att_sudo = hr_attendance.sudo()
        last_attendance = hr_att_sudo.search([
            ('employee_id', '=', employee.id)
        ], order='check_in desc', limit=1)

        if not last_attendance or last_attendance.check_out:
            new_att = hr_att_sudo.create({
                'employee_id': employee.id,
                'check_in': atten_time
            })
            _logger.info(f"Auto mode: Check-in created for {employee.name} at {atten_time}")
            return ('check_in', new_att)
        else:
            # Safety: ensure check_out is strictly after check_in
            check_in_naive = last_attendance.check_in
            if check_in_naive.tzinfo is not None:
                check_in_naive = check_in_naive.astimezone(pytz.UTC).replace(tzinfo=None)
            atten_dt = fields.Datetime.from_string(atten_time) if isinstance(atten_time, str) else atten_time
            if atten_dt.tzinfo is not None:
                atten_dt = atten_dt.astimezone(pytz.UTC).replace(tzinfo=None)
            if atten_dt <= check_in_naive:
                # Punch is at or before existing check-in — create new check-in
                _logger.warning(
                    f"Auto mode: Punch at {atten_time} is not after check_in {last_attendance.check_in} "
                    f"for {employee.name}. Creating new check-in instead.")
                new_att = hr_att_sudo.create({
                    'employee_id': employee.id,
                    'check_in': atten_time
                })
                return ('check_in', new_att)
            last_attendance.write({'check_out': atten_time})
            _logger.info(f"Auto mode: Check-out added for {employee.name} at {atten_time}")
            return ('check_out', last_attendance)

    # ==================== PER-DAY MODE HELPERS ====================

    def _get_day_boundaries_utc(self, atten_time):
        """Convert punch time to local date and return (day_start_utc, day_end_utc, local_tz).
        day_start_utc and day_end_utc are naive datetimes for Odoo search domains."""
        # Parse the attendance time
        if isinstance(atten_time, str):
            atten_dt = fields.Datetime.from_string(atten_time)
        else:
            atten_dt = atten_time

        # Determine device timezone
        tz_str = self._get_device_timezone()
        try:
            local_tz = pytz.timezone(tz_str)
        except pytz.UnknownTimeZoneError:
            local_tz = pytz.UTC

        # Convert to local to find the calendar date
        if atten_dt.tzinfo is None:
            atten_dt_utc = pytz.UTC.localize(atten_dt)
        else:
            atten_dt_utc = atten_dt
        local_dt = atten_dt_utc.astimezone(local_tz)
        punch_date = local_dt.date()

        # Build start/end of local day in UTC (naive for Odoo)
        day_start_local = local_tz.localize(
            datetime.datetime.combine(punch_date, datetime.time.min))
        day_end_local = local_tz.localize(
            datetime.datetime.combine(punch_date, datetime.time(23, 59, 59)))
        day_start_utc = day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        day_end_utc = day_end_local.astimezone(pytz.UTC).replace(tzinfo=None)

        return day_start_utc, day_end_utc, local_tz

    def _auto_close_stale_per_day(self, employee, day_start_utc, hr_att_sudo):
        """Close any open attendance records from previous days at 23:59:59."""
        stale = hr_att_sudo.search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
            ('check_in', '<', day_start_utc),
        ])
        tz_str = self._get_device_timezone()
        try:
            local_tz = pytz.timezone(tz_str)
        except pytz.UnknownTimeZoneError:
            local_tz = pytz.UTC

        for rec in stale:
            # Close at 23:59:59 of the check-in's local date
            checkin_utc = rec.check_in
            if checkin_utc.tzinfo is None:
                checkin_utc = pytz.UTC.localize(checkin_utc)
            checkin_local = checkin_utc.astimezone(local_tz)
            eod_local = local_tz.localize(
                datetime.datetime.combine(checkin_local.date(), datetime.time(23, 59, 59)))
            eod_utc = eod_local.astimezone(pytz.UTC).replace(tzinfo=None)
            rec.write({'check_out': eod_utc})
            _logger.warning(
                f"Per-Day mode: Auto-closed stale attendance for {employee.name} "
                f"(check-in: {rec.check_in}, auto check-out: {eod_utc})")

    def _process_auto_per_day_attendance(self, employee, atten_time, hr_attendance):
        """Auto Per Day: first punch of the day = check-in,
        every subsequent punch updates check-out.
        Result: one hr.attendance per employee per day.
        Returns (odoo_action, hr_attendance_record)."""
        hr_att_sudo = hr_attendance.sudo()

        day_start_utc, day_end_utc, local_tz = self._get_day_boundaries_utc(atten_time)

        # Auto-close any open attendance from previous days
        self._auto_close_stale_per_day(employee, day_start_utc, hr_att_sudo)

        # Find today's attendance for this employee
        today_att = hr_att_sudo.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', day_start_utc),
            ('check_in', '<=', day_end_utc),
        ], order='check_in asc', limit=1)

        if not today_att:
            # First punch of the day -> create check-in
            new_att = hr_att_sudo.create({
                'employee_id': employee.id,
                'check_in': atten_time,
            })
            _logger.info(f"Auto Per Day: Check-in created for {employee.name} at {atten_time}")
            return ('check_in', new_att)
        else:
            # Subsequent punch -> update check-out (last punch wins)
            today_att.write({'check_out': atten_time})
            _logger.info(f"Auto Per Day: Check-out updated for {employee.name} at {atten_time}")
            return ('check_out', today_att)

    def _process_traditional_per_day_attendance(self, employee, atten_time, punch_type, hr_attendance):
        """Traditional Per Day: uses device punch type but only one check-in
        and one check-out per employee per day.
        Returns (odoo_action, hr_attendance_record) or (None, None) if no action taken."""
        hr_att_sudo = hr_attendance.sudo()

        day_start_utc, day_end_utc, local_tz = self._get_day_boundaries_utc(atten_time)

        # Auto-close any open attendance from previous days
        self._auto_close_stale_per_day(employee, day_start_utc, hr_att_sudo)

        # Find today's attendance
        today_att = hr_att_sudo.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', day_start_utc),
            ('check_in', '<=', day_end_utc),
        ], order='check_in asc', limit=1)

        if punch_type == 0:  # check-in from device
            if not today_att:
                new_att = hr_att_sudo.create({
                    'employee_id': employee.id,
                    'check_in': atten_time,
                })
                _logger.info(f"Traditional Per Day: Check-in created for {employee.name}")
                return ('check_in', new_att)
            else:
                _logger.info(
                    f"Traditional Per Day: Check-in already exists for {employee.name} today - skipping")
        elif punch_type == 1:  # check-out from device
            if today_att and not today_att.check_out:
                today_att.write({'check_out': atten_time})
                _logger.info(f"Traditional Per Day: Check-out added for {employee.name}")
                return ('check_out', today_att)
            elif today_att and today_att.check_out:
                _logger.info(
                    f"Traditional Per Day: Check-out already recorded for {employee.name} today - skipping")
            else:
                _logger.warning(
                    f"Traditional Per Day: No check-in today for {employee.name} - cannot add check-out")
        return (None, None)

    _DOWNLOAD_FLAG_KEY = 'attendance.device.download.running'

    def _set_download_flag(self, running):
        """Set or clear the cron-download in-progress flag.

        Uses a separate cursor committed immediately so the flag is visible
        to any concurrent HTTP request (e.g. button click status check).
        """
        db = self.env.cr.dbname
        uid = self.env.uid
        value = datetime.datetime.now().isoformat() if running else ''
        with odoo_registry(db).cursor() as cr:
            env2 = api.Environment(cr, uid, self.env.context)
            env2['ir.config_parameter'].set_param(self._DOWNLOAD_FLAG_KEY, value)
            cr.commit()

    @api.model
    def _is_download_running(self):
        """Return True if a cron download is currently in progress (and not stale)."""
        val = self.env['ir.config_parameter'].sudo().get_param(
            self._DOWNLOAD_FLAG_KEY, '')
        if not val:
            return False
        try:
            ts = datetime.datetime.fromisoformat(val)
            if (datetime.datetime.now() - ts).total_seconds() > 1800:
                # Stale flag — server likely restarted mid-download; clear it
                self.env['ir.config_parameter'].sudo().set_param(
                    self._DOWNLOAD_FLAG_KEY, '')
                return False
        except Exception:
            return False
        return True

    @api.model
    def cron_download(self):
        """Cron: two-phase download for correct multi-device handling.

        Phase 1 — download raw punches from ALL devices into zk.machine.attendance
                   without touching hr.attendance yet.
        Phase 2 — process all newly downloaded records sorted globally by
                   (employee, punching_time) so punches from different devices
                   are interleaved correctly before check-in/check-out decisions.
        """
        machines = self.env['biometric.device.details'].sudo().search([])
        if not machines:
            return

        self._set_download_flag(True)
        try:
            download_start = fields.Datetime.now()

            # Phase 1: store raw punches from every device, no hr.attendance changes
            for machine in machines:
                try:
                    machine.action_download_attendance(skip_processing=True)
                except Exception as e:
                    _logger.error(f"Cron download failed for device {machine.name}: {str(e)}")
                    self.env['biometric.device.log'].sudo().create({
                        'device_id': machine.id,
                        'log_type': 'download',
                        'status': 'failed',
                        'error_message': str(e),
                        'details': f'Cron download failed for device {machine.name}',
                    })

            # Phase 2: process all new records globally sorted
            self._process_pending_globally(download_start)
        finally:
            self._set_download_flag(False)

    @api.model
    def _process_pending_globally(self, create_after):
        """Process all unprocessed zk.machine.attendance records created on or
        after create_after, ordered by (employee_id, punching_time).

        This ensures that punches from multiple devices for the same employee
        are processed in true chronological order, fixing check-in/check-out
        pairing in multi-device setups for ALL attendance modes."""
        pending = self.env['zk.machine.attendance'].sudo().search([
            ('create_date', '>=', create_after),
            ('processed', '=', False),
        ], order='employee_id asc, punching_time asc')

        if not pending:
            _logger.info("Global processing: no new unprocessed records found.")
            return

        _logger.info(f"Global processing: {len(pending)} records across all devices.")
        hr_attendance = self.env['hr.attendance']

        for zk_rec in pending:
            try:
                with self.env.cr.savepoint():
                    employee = zk_rec.employee_id
                    device = zk_rec.device_id
                    if not employee or not device:
                        zk_rec.write({'processed': True})
                        continue

                    atten_time = fields.Datetime.to_string(zk_rec.punching_time)
                    punch_type_str = zk_rec.punch_type or '0'
                    punch_type = int(punch_type_str) if punch_type_str.isdigit() else 0
                    attendance_mode = device.attendance_mode or 'traditional'

                    # Stale attendance check (open > 24 hours)
                    device_tz_str = device._get_device_timezone()
                    try:
                        local_tz = pytz.timezone(device_tz_str)
                    except pytz.UnknownTimeZoneError:
                        local_tz = pytz.UTC

                    atten_dt = zk_rec.punching_time
                    atten_aware = pytz.UTC.localize(atten_dt) if atten_dt.tzinfo is None else atten_dt

                    stale = hr_attendance.sudo().search([
                        ('employee_id', '=', employee.id),
                        ('check_out', '=', False),
                    ])
                    for old_att in stale:
                        old_ci = old_att.check_in
                        if old_ci.tzinfo is None:
                            old_ci = pytz.UTC.localize(old_ci)
                        if (atten_aware - old_ci).total_seconds() / 3600.0 > 24:
                            eod = local_tz.localize(
                                datetime.datetime.combine(old_att.check_in.date(),
                                                         datetime.time(23, 59, 59))
                            ).astimezone(pytz.UTC).replace(tzinfo=None)
                            old_att.sudo().write({'check_out': eod})
                            _logger.warning(
                                f"Global processing: auto-closed stale attendance for "
                                f"{employee.name} (check-in: {old_att.check_in})")

                    # Mode processing
                    if attendance_mode == 'auto':
                        odoo_action, att_record = device._process_auto_attendance(
                            employee, atten_time, hr_attendance)
                    elif attendance_mode == 'auto_per_day':
                        odoo_action, att_record = device._process_auto_per_day_attendance(
                            employee, atten_time, hr_attendance)
                    elif attendance_mode == 'traditional_per_day':
                        odoo_action, att_record = device._process_traditional_per_day_attendance(
                            employee, atten_time, punch_type, hr_attendance)
                    else:
                        odoo_action, att_record = device._process_traditional_attendance(
                            employee, atten_time, punch_type, hr_attendance)

                    if odoo_action and att_record:
                        zk_rec.write({
                            'hr_attendance_id': att_record.id,
                            'processed': True,
                            'odoo_punch_type': odoo_action,
                        })
                    else:
                        zk_rec.write({'processed': True})

            except Exception as e:
                _logger.error(
                    f"Global processing: failed for {zk_rec.employee_id.name} "
                    f"at {zk_rec.punching_time}: {e}")
                # Reset aborted transaction so the next record starts clean.
                try:
                    self.env.cr.rollback()
                except Exception:
                    pass

    @api.model
    def cron_refresh_device_info(self):
        """Cron method for refreshing device information"""
        devices = self.search([])
        for device in devices:
            try:
                device.action_refresh_device_info()
            except Exception as e:
                _logger.error(f"Failed to refresh device info for {device.name}: {str(e)}")

    def action_download_attendance(self, skip_processing=False):
        """Download attendance records from the device with per-device logging.

        Button click (skip_processing=False):
            Downloads ALL devices raw → processes all globally sorted.
            Guarantees correct check-in/check-out in multi-device setups.

        Cron / internal call (skip_processing=True):
            Only stores raw punches for THIS device to zk.machine.attendance.
            Caller (cron_download) will run _process_pending_globally after
            all devices are downloaded."""

        if not skip_processing:
            # ── Button path: download ALL devices + global sort + process ──
            download_start = fields.Datetime.now()
            all_devices = self.env['biometric.device.details'].sudo().search([])
            for device in all_devices:
                try:
                    device.action_download_attendance(skip_processing=True)
                except Exception as e:
                    _logger.error(f"Download failed for device {device.name}: {e}")
            self._process_pending_globally(download_start)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('Attendance downloaded from all devices and processed successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        # ── Internal/cron path: raw download for THIS device only ──
        _logger.info("++++++++++++Download Attendance Executed++++++++++++++++++++++")
        zk_attendance = self.env['zk.machine.attendance']
        hr_attendance = self.env['hr.attendance']
        device_log = self.env['biometric.device.log'].sudo()

        for info in self:
            start_time = _time.time()
            records_found = 0
            records_new = 0
            records_duplicate = 0
            records_failed = 0
            employees_not_found = 0
            log_details = []

            machine_ip = info.device_ip
            zk_port = info.port_number
            device_password = info._get_device_password()
            attendance_mode = info.attendance_mode or 'traditional'
            duplicate_threshold = info.duplicate_threshold or 2
            
            try:
                zk = ZK(machine_ip, port=zk_port, timeout=15,
                        password=device_password,
                        force_udp=False, ommit_ping=True)
            except NameError:
                device_log.create({
                    'device_id': info.id,
                    'log_type': 'download',
                    'status': 'failed',
                    'error_message': 'pyzk module not found. Install with: pip3 install pyzk',
                })
                raise UserError(
                    _("Pyzk module not Found. Please install it with 'pip3 install pyzk'."))

            conn = info.device_connect(zk)
            if not conn:
                device_log.create({
                    'device_id': info.id,
                    'log_type': 'download',
                    'status': 'failed',
                    'duration': _time.time() - start_time,
                    'error_message': f'Unable to connect to device {info.name} ({machine_ip}:{zk_port})',
                    'details': 'Connection refused. Check: IP address, port, network, device power.',
                })
                raise UserError(_('Unable to connect, please check parameters'))

            try:
                conn.disable_device()

                # Resolve device timezone for timestamp conversion (do NOT change device clock during download)
                device_tz_str = info._get_device_timezone()
                info.write({'effective_timezone': device_tz_str})
                try:
                    local_tz = pytz.timezone(device_tz_str)
                except pytz.UnknownTimeZoneError:
                    local_tz = pytz.UTC

                user = conn.get_users()
                attendance = conn.get_attendance()

                if not attendance:
                    device_log.create({
                        'device_id': info.id,
                        'log_type': 'download',
                        'status': 'warning',
                        'records_found': 0,
                        'records_new': 0,
                        'duration': _time.time() - start_time,
                        'details': 'Connected successfully but no attendance records found on device.',
                    })
                    conn.disconnect()
                    info.last_download_time = fields.Datetime.now()
                    return True

                records_found = len(attendance)
                # Build user lookup dict for faster matching
                user_map = {u.user_id: u for u in user} if user else {}

                for each in sorted(attendance, key=lambda x: x.timestamp):
                    try:
                        with self.env.cr.savepoint():
                            atten_time = each.timestamp
                            local_dt = local_tz.localize(atten_time, is_dst=None)
                            utc_dt = local_dt.astimezone(pytz.utc)
                            atten_time_dt = utc_dt
                            atten_time_str = fields.Datetime.to_string(utc_dt)

                            uid_match = user_map.get(each.user_id)
                            if not uid_match:
                                employees_not_found += 1
                                device_log.create({
                                    'device_id': info.id,
                                    'log_type': 'download',
                                    'status': 'warning',
                                    'error_message': f'Unrecognized User ID in attendance log: {each.user_id}',
                                    'details': f'Record skipped. Timestamp: {atten_time_str}. User ID {each.user_id} does not exist on the device.',
                                })
                                continue

                            get_user_id = self.env['hr.employee'].sudo().with_company(info.company_id).search(
                                [('device_id_num', '=', each.user_id),
                                 ('company_id', '=', info.company_id.id)], limit=1)

                            if get_user_id:
                                # Check exact duplicate
                                duplicate_atten_ids = zk_attendance.search(
                                    [('device_id_num', '=', each.user_id),
                                     ('punching_time', '=', atten_time_str)], limit=1)

                                if duplicate_atten_ids:
                                    records_duplicate += 1
                                    continue

                                # Check time-window duplicate
                                if info._is_duplicate_punch(get_user_id.id, atten_time_dt, duplicate_threshold):
                                    records_duplicate += 1
                                    continue

                                zk_record = zk_attendance.create({
                                    'employee_id': get_user_id.id,
                                    'device_id': info.id,
                                    'device_id_num': each.user_id,
                                    'attendance_type': ZkMachineAttendance._sanitize_attendance_type(each.status),
                                    'punch_type': ZkMachineAttendance._sanitize_punch_type(each.punch),
                                    'punching_time': atten_time_str,
                                    'address_id': info.address_id.id
                                })

                                if not skip_processing:
                                    # Handle stale attendance (open > 24 hours)
                                    att_var = hr_attendance.sudo().search([
                                        ('employee_id', '=', get_user_id.id),
                                        ('check_out', '=', False)
                                    ])

                                    if att_var:
                                        for old_att in att_var:
                                            old_check_in = old_att.check_in
                                            if old_check_in.tzinfo is None:
                                                old_check_in = pytz.UTC.localize(old_check_in)
                                            time_diff = atten_time_dt - old_check_in
                                            hours_open = time_diff.total_seconds() / 3600.0

                                            if hours_open > 24:
                                                check_in_date = old_att.check_in.date()
                                                auto_checkout = datetime.datetime.combine(
                                                    check_in_date,
                                                    datetime.datetime.strptime("23:59:59", "%H:%M:%S").time()
                                                )
                                                auto_checkout_aware = local_tz.localize(auto_checkout).astimezone(pytz.UTC)
                                                auto_checkout_naive = auto_checkout_aware.replace(tzinfo=None)
                                                old_att.sudo().write({'check_out': auto_checkout_naive})
                                                _logger.warning(
                                                    f"Auto-closed stale attendance for {get_user_id.name}"
                                                )

                                    if attendance_mode == 'auto':
                                        odoo_action, att_record = info._process_auto_attendance(
                                            get_user_id, atten_time_str, hr_attendance)
                                    elif attendance_mode == 'auto_per_day':
                                        odoo_action, att_record = info._process_auto_per_day_attendance(
                                            get_user_id, atten_time_str, hr_attendance)
                                    elif attendance_mode == 'traditional_per_day':
                                        odoo_action, att_record = info._process_traditional_per_day_attendance(
                                            get_user_id, atten_time_str, each.punch, hr_attendance)
                                    else:
                                        odoo_action, att_record = info._process_traditional_attendance(
                                            get_user_id, atten_time_str, each.punch, hr_attendance)

                                    if odoo_action and att_record:
                                        zk_record.write({
                                            'hr_attendance_id': att_record.id,
                                            'processed': True,
                                            'odoo_punch_type': odoo_action,
                                        })

                                records_new += 1
                            else:
                                device_log.create({
                                    'device_id': info.id,
                                    'log_type': 'download',
                                    'status': 'warning',
                                    'error_message': f'Unknown Device User: {uid_match.name} (ID: {each.user_id})',
                                    'details': f'An attendance record was found for an unmapped device user. A new hr.employee record was auto-created to store this attendance.',
                                })
                                # Create new employee from device user under the device's company
                                employee = self.env['hr.employee'].sudo().with_company(info.company_id).create({
                                    'device_id_num': each.user_id,
                                    'name': uid_match.name,
                                    'company_id': info.company_id.id,
                                })
                                zk_record = zk_attendance.create({
                                    'employee_id': employee.id,
                                    'device_id': info.id,
                                    'device_id_num': each.user_id,
                                    'attendance_type': ZkMachineAttendance._sanitize_attendance_type(each.status),
                                    'punch_type': ZkMachineAttendance._sanitize_punch_type(each.punch),
                                    'punching_time': atten_time_str,
                                    'address_id': info.address_id.id
                                })
                                new_attendance = hr_attendance.create({
                                    'employee_id': employee.id,
                                    'check_in': atten_time_str
                                })
                                zk_record.write({
                                    'hr_attendance_id': new_attendance.id,
                                    'processed': True
                                })
                                records_new += 1
                                log_details.append(f"New employee created: {uid_match.name} (Device ID: {each.user_id})")

                    except Exception as rec_error:
                        records_failed += 1
                        log_details.append(f"Failed record: User={each.user_id}, Time={each.timestamp}, Error={str(rec_error)}")
                        _logger.error(f"Error processing record from {info.name}: {str(rec_error)}")
                        # Reset the cursor so subsequent savepoints start on a clean transaction.
                        # Without this, any exception inside a savepoint leaves the outer
                        # transaction in an aborted state, causing ALL following DB calls to fail
                        # with "current transaction is aborted, commands ignored until end of
                        # transaction block".
                        try:
                            self.env.cr.rollback()
                        except Exception:
                            pass

                elapsed = _time.time() - start_time
                info.last_download_time = fields.Datetime.now()

                # Determine log status
                if records_failed > 0 and records_new == 0:
                    log_status = 'failed'
                elif records_failed > 0:
                    log_status = 'warning'
                else:
                    log_status = 'success'

                details_text = (
                    f"Device: {info.name} ({machine_ip}:{zk_port})\n"
                    f"Mode: {attendance_mode}\n"
                    f"Users on device: {len(user) if user else 0}\n"
                    f"Duplicate threshold: {duplicate_threshold} min"
                )
                if log_details:
                    details_text += "\n\nNotes:\n" + "\n".join(log_details)

                device_log.create({
                    'device_id': info.id,
                    'log_type': 'download',
                    'status': log_status,
                    'records_found': records_found,
                    'records_new': records_new,
                    'records_duplicate': records_duplicate,
                    'records_failed': records_failed,
                    'employees_not_found': employees_not_found,
                    'duration': elapsed,
                    'details': details_text,
                    'error_message': "\n".join(log_details) if records_failed > 0 else False,
                })

                _logger.info(
                    f"Download complete for {info.name}: "
                    f"found={records_found}, new={records_new}, "
                    f"dup={records_duplicate}, failed={records_failed}, "
                    f"unknown_emp={employees_not_found}, time={elapsed:.1f}s"
                )

            except Exception as e:
                elapsed = _time.time() - start_time
                device_log.create({
                    'device_id': info.id,
                    'log_type': 'download',
                    'status': 'failed',
                    'records_found': records_found,
                    'records_new': records_new,
                    'records_duplicate': records_duplicate,
                    'records_failed': records_failed,
                    'employees_not_found': employees_not_found,
                    'duration': elapsed,
                    'error_message': str(e),
                    'details': f"Exception during download from {info.name}",
                })
                _logger.error(f"Download failed for device {info.name}: {str(e)}")
                raise
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass

        return True

    def action_download_attendance_background(self):
        """Trigger attendance download via the scheduled cron (non-blocking UI).

        If a download is already running, shows a warning instead of queuing
        another job, so users are not confused when the UI returns quickly but
        the background process is still processing large datasets.
        """
        if self._is_download_running():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Download In Progress'),
                    'message': _(
                        'Your attendance data is currently being downloaded and processed '
                        'in the background. Please wait for it to complete before '
                        'starting a new download.'
                    ),
                    'type': 'warning',
                    'sticky': True,
                },
            }

        existing_cron = self.env.ref(
            'dotbd_hr_zk_attendance_suite.ir_cron_biometric_download',
            raise_if_not_found=False)
        if existing_cron:
            existing_cron.sudo().write({'nextcall': fields.Datetime.now()})
        else:
            self.env['ir.cron'].sudo().create({
                'name': _('ZK Attendance – One-shot Download'),
                'model_id': self.env['ir.model'].search(
                    [('model', '=', self._name)], limit=1).id,
                'state': 'code',
                'code': 'model.search([]).action_download_attendance()',
                'interval_number': 1,
                'interval_type': 'minutes',
                'nextcall': fields.Datetime.now(),
                'active': True,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Downloading in Background'),
                'message': _(
                    'Attendance download has been queued. '
                    'It will run via the scheduled job. '
                    'Depending on device data volume and server/database speed, '
                    'this may take a few minutes.'
                ),
                'sticky': True,
                'type': 'info',
            },
        }

    # ==================== ADMS COMMAND METHODS ====================

    def action_adms_enroll_fingerprint(self):
        """Trigger fingerprint enrollment on ADMS-connected device.
        Queues an ENROLL_FP command for the device to pick up."""
        self.ensure_one()
        if self.connection_mode not in ('adms', 'hybrid'):
            raise UserError(_('Fingerprint enrollment via ADMS is only available '
                             'in Cloud (ADMS) or Hybrid connection mode.'))
        # Open wizard to select employee and finger
        return {
            'type': 'ir.actions.act_window',
            'name': _('Enroll Fingerprint'),
            'res_model': 'adms.device.command',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_device_id': self.id,
                'default_command_type': 'enroll_fp',
            },
        }

    def action_adms_reboot(self):
        """Queue a REBOOT command for ADMS device."""
        self.ensure_one()
        if self.connection_mode not in ('adms', 'hybrid'):
            raise UserError(_('ADMS commands are only available in Cloud (ADMS) or Hybrid mode.'))
        self.env['adms.device.command'].create({
            'device_id': self.id,
            'command_type': 'reboot',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Reboot command queued. Device will reboot on next heartbeat.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_adms_sync_users(self):
        """Queue user sync commands for all mapped employees."""
        self.ensure_one()
        if self.connection_mode not in ('adms', 'hybrid'):
            raise UserError(_('ADMS commands are only available in Cloud (ADMS) or Hybrid mode.'))
        employees = self.env['hr.employee'].search([
            ('device_id_num', '!=', False),
            ('device_id_num', '!=', ''),
        ])
        count = 0
        for emp in employees:
            self.env['adms.device.command'].create({
                'device_id': self.id,
                'command_type': 'sync_user',
                'employee_id': emp.id,
            })
            count += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _(f'{count} user sync commands queued for {self.name}.'),
                'type': 'info',
                'sticky': False,
            }
        }

    def action_view_adms_commands(self):
        """View ADMS command queue for this device."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('ADMS Commands'),
            'res_model': 'adms.device.command',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
            'context': {'default_device_id': self.id},
        }

    def action_view_fp_templates(self):
        """View fingerprint templates for this device."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fingerprint Templates'),
            'res_model': 'biometric.fp.template',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
        }
