# -*- coding: utf-8 -*-
################################################################################
#
#    Dot BD Solutions Limited
#    Copyright (C) 2025-TODAY Dot BD Solutions Limited.
#    Author: Rafiur Rahman Rafit
#
#    ADMS Push Protocol Controller
#    Receives attendance data and commands from ZKTeco devices
#    using the ADMS (Automatic Data Master Server) push protocol.
#
################################################################################

import logging
from datetime import datetime

import pytz
from odoo import http, fields, SUPERUSER_ID, api
from odoo.http import request
from odoo.addons.dotbd_hr_zk_attendance_suite.models.zk_machine_attendance import ZkMachineAttendance

_logger = logging.getLogger(__name__)


class ADMSController(http.Controller):
    """HTTP Controller for ZKTeco ADMS Push Protocol.

    The device connects to Odoo and pushes attendance data.
    Protocol endpoints:
        /iclock/cdata       GET  = handshake, POST = push data (attendance/users/biometrics)
        /iclock/getrequest  GET  = device polls for pending commands
        /iclock/devicecmd   POST = device reports command execution result
    """

    # ─────────────────────────── helpers ───────────────────────────

    def _senv(self):
        """Return a SUPERUSER environment safe for use in auth='none' routes.

        In auth='none' routes, request.env.uid is None. Neither .sudo() on
        individual models nor request.env(user=SUPERUSER_ID) fully propagates
        uid=1 into mail.thread hooks and compute triggers — they call
        self.env.user internally and get res.users() → 'Expected singleton'.

        The only reliable fix: construct a fresh api.Environment with the same
        cursor but uid=1 explicitly. This is identical to what Odoo uses for
        cron jobs, post-install hooks, and other server-side contexts.
        """
        return api.Environment(request.env.cr, SUPERUSER_ID, request.env.context)

    def _find_device_by_serial(self, serial_number):
        """Find device record by serial number. Returns recordset or empty."""
        env = self._senv()
        if not serial_number:
            return env['biometric.device.details']
        return env['biometric.device.details'].search([
            ('device_serial', '=', serial_number),
            ('connection_mode', 'in', ['adms', 'hybrid']),
        ], limit=1)

    def _register_heartbeat(self, device):
        """Update the device's last heartbeat timestamp."""
        if device:
            device.write({
                'adms_last_heartbeat': fields.Datetime.now(),
                'last_online_time': fields.Datetime.now(),
            })

    def _get_device_timezone_for_adms(self, device):
        """Get the timezone for ADMS: used in BOTH ServerLocalTime (sent to device)
        and ATTLOG timestamp interpretation (received from device).

        These MUST be the same timezone — whatever we send in ServerLocalTime,
        the device will record timestamps in that timezone, so we must interpret
        them with the same timezone when converting to UTC for Odoo storage.

        Rule: custom_timezone (user-set, default Asia/Kolkata) → company timezone → Asia/Kolkata
        NOTE: effective_timezone is intentionally excluded here — it is set by PyZK
        (direct connection mode) and may differ from what ADMS is actually using.
        Using effective_timezone in ADMS would break timezone conversion.
        """
        if device.custom_timezone:
            return device.custom_timezone
        return (device.company_id.partner_id.tz or 'Asia/Kolkata')

    # ─────────────────────────── /iclock/cdata ───────────────────────────

    @http.route('/iclock/cdata', type='http', auth='none',
                csrf=False, methods=['GET', 'POST'], save_session=False)
    def cdata(self, **kwargs):
        """Main ADMS endpoint.
        GET  = device handshake (sends SN, gets config)
        POST = device pushes data (ATTLOG, OPERLOG, BIODATA)
        """
        serial = kwargs.get('SN', '')

        if request.httprequest.method == 'GET':
            return self._handle_handshake(serial, kwargs)

        # POST — device is pushing data
        table = kwargs.get('table', '')
        body = request.httprequest.data
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')

        _logger.info("ADMS POST from SN=%s table=%s (%d bytes)", serial, table, len(body))

        if table == 'ATTLOG':
            return self._process_attendance(serial, body)
        elif table == 'OPERLOG':
            return self._process_operation_log(serial, body)
        elif table in ('BIODATA', 'BIOTEMPLATE'):
            return self._process_biometric_template(serial, body)

        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

    def _handle_handshake(self, serial, kwargs):
        """Device sends GET /iclock/cdata?SN=xxx on first connect.
        We respond with server configuration options."""
        _logger.info("ADMS handshake from SN=%s params=%s", serial, dict(kwargs))

        device = self._find_device_by_serial(serial)

        if not device:
            # Auto-register: create a new device record for unknown serial
            _logger.info("ADMS: New device detected SN=%s — auto-registering", serial)
            env = self._senv()
            device = env['biometric.device.details'].create({
                'name': f'ADMS Device ({serial})',
                'device_serial': serial,
                'connection_mode': 'adms',
                'device_ip': request.httprequest.remote_addr or '0.0.0.0',
                'port_number': 4370,
            })
            device.message_post(
                body=f"Device auto-registered via ADMS push (SN: {serial}, "
                     f"IP: {request.httprequest.remote_addr})",
                message_type='notification',
            )

        self._register_heartbeat(device)

        # Compute correct local time for the device's timezone
        tz_str = self._get_device_timezone_for_adms(device)
        try:
            local_tz = pytz.timezone(tz_str)
        except pytz.UnknownTimeZoneError:
            local_tz = pytz.timezone('Asia/Kolkata')
        device_local_time = datetime.now(pytz.utc).astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')

        # Response: tell device what tables to push, heartbeat interval, and correct time
        config_lines = [
            'GET OPTION FROM: {}'.format(serial),
            'ErrorDelay=30',
            'Delay=10',
            'TransTimes=00:00;14:05',
            'TransInterval=1',
            'TransFlag=TransData AttLog\tOpLog\tBioData',
            'Realtime=1',
            'ServerVer=2.4.1',
            'ServerLocalTime={}'.format(device_local_time),
        ]
        response_body = '\r\n'.join(config_lines) + '\r\n'

        return request.make_response(
            response_body,
            headers=[('Content-Type', 'text/plain')]
        )

    # ─────────────────────────── Attendance Push ───────────────────────────

    def _process_attendance(self, serial, body):
        """Parse ATTLOG data pushed by device and create attendance records.

        ATTLOG format (tab-delimited, one record per line):
        USER_ID\\tTIMESTAMP\\tSTATUS\\tVERIFY\\t\\t\\t
        Example: 1\\t2026-02-26 09:00:00\\t0\\t1\\t\\t\\t

        STATUS: 0=Check-in, 1=Check-out, 2=Break-out, 3=Break-in, 4=OT-in, 5=OT-out
        VERIFY: 0=Password, 1=Fingerprint, 2=Card, 9=Face, etc.
        """
        device = self._find_device_by_serial(serial)
        if not device:
            _logger.warning("ADMS ATTLOG: Unknown device SN=%s", serial)
            return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

        self._register_heartbeat(device)

        # Determine device timezone for converting local time → UTC
        # Odoo stores ALL datetimes as UTC, and displays in user's timezone.
        # Device sends local time (e.g. 14:14 BDT) → must convert to UTC (08:14).
        tz_str = self._get_device_timezone_for_adms(device)
        _logger.info(
            "ADMS ATTLOG SN=%s: Using timezone '%s' (custom_tz=%s, effective_tz=%s)",
            serial, tz_str, device.custom_timezone, device.effective_timezone)
        try:
            local_tz = pytz.timezone(tz_str)
        except pytz.UnknownTimeZoneError:
            local_tz = pytz.UTC

        lines = body.strip().split('\n')
        records_processed = 0
        records_duplicate = 0
        records_failed = 0
        new_employees_created = []
        log_msgs = []

        # Use SUPERUSER environment for all operations to avoid "Expected singleton: res.users()"
        # in auth='none' routes where request.env.uid is None/False (Odoo 19).
        env = self._senv()
        zk_attendance = env['zk.machine.attendance']
        hr_attendance = env['hr.attendance']
        hr_employee = env['hr.employee']

        attendance_mode = device.attendance_mode or 'traditional'
        duplicate_threshold = device.duplicate_threshold or 2

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                # flush=False: prevent _FlushingSavepoint from calling cr.flush()
                # on exit, which would use default_env (request.env, uid=None) and
                # crash on hr.attendance._compute_is_manager accessing env.user.
                # We flush manually inside the block using our superuser env instead.
                with env.cr.savepoint(flush=False):
                    # Format: USER_ID\tTIMESTAMP\tSTATUS\tVERIFY
                    # Example: 1	2023-10-25 09:00:00	0	1
                    parts = line.split('\t')
                    if len(parts) < 3:
                        _logger.warning("ADMS ATTLOG: Invalid line format: %s", line)
                        records_failed += 1
                        continue

                    user_id = parts[0].strip()
                    timestamp_str = parts[1].strip()
                    zk_status = int(parts[2].strip())
                    verify = int(parts[3].strip()) if len(parts) > 3 and parts[3].strip() else 0

                    # Parse timestamp
                    try:
                        atten_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        _logger.warning("ADMS ATTLOG: Invalid timestamp: %s", timestamp_str)
                        records_failed += 1
                        continue

                    # Convert device local time to UTC (naive — Odoo 19 requires no tzinfo)
                    # Device sends local time (e.g. 14:14 BDT) → convert to UTC (08:14)
                    local_dt = local_tz.localize(atten_time, is_dst=None)
                    utc_dt = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                    atten_time_str = fields.Datetime.to_string(utc_dt)

                    # Find employee by device_id_num scoped to the device's company
                    employee = hr_employee.with_company(device.company_id).search([
                        ('device_id_num', '=', user_id),
                        ('company_id', '=', device.company_id.id),
                    ], limit=1)

                    if not employee:
                        # Auto-create a new employee for this unknown device user ID
                        _logger.info(
                            "ADMS ATTLOG: No employee found for Device ID '%s'. "
                            "Auto-creating new employee.", user_id)
                        employee = hr_employee.with_company(device.company_id).create({
                            'name': f'Device User {user_id}',
                            'device_id_num': user_id,
                            'company_id': device.company_id.id,
                            'active': True,
                        })
                        new_employees_created.append(user_id)
                        _logger.info(
                            "ADMS ATTLOG: Auto-created employee '%s' (ID=%s) for Device ID '%s'",
                            employee.name, employee.id, user_id)

                    # Check exact duplicate
                    existing = zk_attendance.search([
                        ('device_id_num', '=', user_id),
                        ('punching_time', '=', atten_time_str),
                    ], limit=1)
                    if existing:
                        records_duplicate += 1
                        continue

                    # Check time-window duplicate
                    if device._is_duplicate_punch(employee.id, utc_dt, duplicate_threshold):
                        records_duplicate += 1
                        continue

                    # Sanitize punch type: 0=Check-in, 1=Check-out
                    # ZKTeco STATUS map: 0/3/4=Check-in, 1/2/5=Check-out
                    punch_type = 0 if zk_status in (0, 3, 4) else 1

                    # Create raw attendance record
                    zk_att = zk_attendance.create({
                        'employee_id': employee.id,
                        'device_id': device.id,
                        'device_id_num': user_id,
                        'attendance_type': ZkMachineAttendance._sanitize_attendance_type(zk_status),
                        'punch_type': ZkMachineAttendance._sanitize_punch_type(punch_type),
                        'punching_time': atten_time_str,
                        'address_id': device.address_id.id if device.address_id else False,
                        'source': 'adms',
                    })

                    # Process attendance (check-in / check-out in hr.attendance)
                    if attendance_mode == 'auto':
                        odoo_action, att_record = device._process_auto_attendance(
                            employee, atten_time_str, hr_attendance)
                    elif attendance_mode == 'auto_per_day':
                        odoo_action, att_record = device._process_auto_per_day_attendance(
                            employee, atten_time_str, hr_attendance)
                    elif attendance_mode == 'traditional_per_day':
                        odoo_action, att_record = device._process_traditional_per_day_attendance(
                            employee, atten_time_str, punch_type, hr_attendance)
                    else:
                        odoo_action, att_record = device._process_traditional_attendance(
                            employee, atten_time_str, punch_type, hr_attendance)

                    # Link zk record to the processed hr.attendance record
                    if odoo_action and att_record:
                        zk_att.write({
                            'hr_attendance_id': att_record.id,
                            'processed': True,
                            'odoo_punch_type': odoo_action,
                        })

                    # Flush pending ORM ops (e.g. hr.attendance._compute_is_manager)
                    # using our superuser env so env.user is always the admin user.
                    env.flush_all()
                    records_processed += 1

            except Exception as e:
                _logger.error("ADMS ATTLOG: Error processing line '%s': %s", line, e)
                records_failed += 1
                log_msgs.append(f"Failed record '{line[:30]}...': {e}")

        # Update push count
        if records_processed > 0:
            device.write({
                'adms_push_count': device.adms_push_count + records_processed,
                'last_download_time': fields.Datetime.now(),
            })

        # Generate a device log summary
        if records_processed > 0 or records_failed > 0 or records_duplicate > 0 or new_employees_created:
            log_status = 'success'
            if records_failed > 0:
                log_status = 'warning' if records_processed > 0 else 'failed'

            details_text = f"ADMS sync via Webhook.\nDuplicates: {records_duplicate}"
            if new_employees_created:
                details_text += (
                    f"\n\nAuto-created {len(new_employees_created)} new employee(s) "
                    f"for Device IDs: {', '.join(new_employees_created)}\n"
                    "Please update their names in HR → Employees."
                )
            if log_msgs:
                details_text += "\n\nError Notes:\n" + "\n".join(log_msgs)

            env['biometric.device.log'].create({
                'device_id': device.id,
                'log_type': 'live_capture',
                'status': log_status,
                'records_found': records_processed + records_failed + records_duplicate,
                'records_new': records_processed,
                'records_duplicate': records_duplicate,
                'records_failed': records_failed,
                'error_message': "\n".join(log_msgs) if log_msgs else False,
                'details': details_text,
            })

        _logger.info(
            "ADMS ATTLOG SN=%s: %d processed, %d duplicates, %d failed, %d new employees",
            serial, records_processed, records_duplicate, records_failed, len(new_employees_created))

        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

    # ─────────────────────────── Operation Log ───────────────────────────

    def _process_operation_log(self, serial, body):
        """Process OPERLOG data — device operation events (optional logging)."""
        device = self._find_device_by_serial(serial)
        if device:
            self._register_heartbeat(device)

        _logger.debug("ADMS OPERLOG from SN=%s: %s", serial, body[:200] if body else '')
        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

    # ─────────────────────────── Biometric Templates ───────────────────────────

    def _process_biometric_template(self, serial, body):
        """Process BIODATA — fingerprint/face templates pushed from device.

        Called when device completes fingerprint enrollment or syncs templates.
        Format: PIN=1\\tFID=0\\tTMP=<base64>\\tSZ=1024\\tValid=1
        """
        device = self._find_device_by_serial(serial)
        if not device:
            _logger.warning("ADMS BIODATA: Unknown device SN=%s", serial)
            return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

        self._register_heartbeat(device)

        env = self._senv()
        lines = body.strip().split('\n')
        fp_template_model = env['biometric.fp.template']
        hr_employee = env['hr.employee']

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                # Parse key=value pairs separated by tabs
                params = {}
                for part in line.split('\t'):
                    if '=' in part:
                        key, _, value = part.partition('=')
                        params[key.strip().upper()] = value.strip()

                pin = params.get('PIN', '')
                fid = int(params.get('FID', '0'))
                tmp_data = params.get('TMP', '')
                tmp_size = int(params.get('SZ', '0'))

                if not pin or not tmp_data:
                    continue

                # Find employee
                employee = hr_employee.search([
                    ('device_id_num', '=', pin)
                ], limit=1)

                if not employee:
                    _logger.info("ADMS BIODATA: No employee for PIN=%s", pin)
                    continue

                # Check if template already exists for this finger
                existing = fp_template_model.search([
                    ('employee_id', '=', employee.id),
                    ('finger_index', '=', fid),
                ], limit=1)

                template_vals = {
                    'employee_id': employee.id,
                    'device_id': device.id,
                    'finger_index': fid,
                    'template_data': tmp_data,
                    'template_size': tmp_size,
                    'capture_time': fields.Datetime.now(),
                }

                if existing:
                    existing.write(template_vals)
                    _logger.info("ADMS BIODATA: Updated template for %s finger %d",
                                 employee.name, fid)
                else:
                    fp_template_model.create(template_vals)
                    _logger.info("ADMS BIODATA: Saved new template for %s finger %d",
                                 employee.name, fid)

                # Mark enrollment command as done
                pending_cmd = env['adms.device.command'].search([
                    ('device_id', '=', device.id),
                    ('command_type', '=', 'enroll_fp'),
                    ('employee_id', '=', employee.id),
                    ('status', 'in', ['pending', 'sent']),
                ], limit=1)
                if pending_cmd:
                    pending_cmd.write({
                        'status': 'done',
                        'done_time': fields.Datetime.now(),
                        'result': f'Template received: finger {fid}, size {tmp_size}',
                    })

            except Exception as e:
                _logger.error("ADMS BIODATA: Error: %s", e)

        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

    # ─────────────────────────── Command Polling ───────────────────────────

    @http.route('/iclock/getrequest', type='http', auth='none',
                csrf=False, methods=['GET'], save_session=False)
    def getrequest(self, **kwargs):
        """Device polls for pending commands.
        Returns one command at a time in format: C:{id}:{command_body}
        or 'OK' if no pending commands.
        """
        serial = kwargs.get('SN', '')
        device = self._find_device_by_serial(serial)

        if not device:
            return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

        self._register_heartbeat(device)

        # Get next pending command
        command = self._senv()['adms.device.command'].search([
            ('device_id', '=', device.id),
            ('status', '=', 'pending'),
        ], order='create_date asc', limit=1)

        if command:
            command.write({
                'status': 'sent',
                'sent_time': fields.Datetime.now(),
            })
            cmd_str = command.format_for_device()
            _logger.info("ADMS getrequest SN=%s: sending command %s", serial, cmd_str)
            return request.make_response(
                cmd_str + '\r\n',
                headers=[('Content-Type', 'text/plain')]
            )

        # No pending commands — respond with OK only (protocol-compliant)
        # Time sync is already sent in the /iclock/cdata handshake response.
        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])

    # ─────────────────────────── Command Response ───────────────────────────

    @http.route('/iclock/devicecmd', type='http', auth='none',
                csrf=False, methods=['POST'], save_session=False)
    def devicecmd(self, **kwargs):
        """Device reports back the result of a command execution.
        Body format: ID=xxx&Return=0 (0=success)
        """
        serial = kwargs.get('SN', '')
        device = self._find_device_by_serial(serial)

        if device:
            self._register_heartbeat(device)

        body = request.httprequest.data
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')

        _logger.info("ADMS devicecmd SN=%s: %s", serial, body)

        # Parse command ID and result from response
        try:
            params = {}
            for part in body.strip().replace('&', '\n').split('\n'):
                if '=' in part:
                    key, _, value = part.partition('=')
                    params[key.strip()] = value.strip()

            cmd_id = int(params.get('ID', 0))
            return_code = int(params.get('Return', -1))

            if device and cmd_id:
                command = self._senv()['adms.device.command'].search([
                    ('device_id', '=', device.id),
                    ('command_id', '=', cmd_id),
                    ('status', '=', 'sent'),
                ], limit=1)
                if command:
                    command.write({
                        'status': 'done' if return_code == 0 else 'failed',
                        'done_time': fields.Datetime.now(),
                        'result': f'Return={return_code}',
                    })
        except Exception as e:
            _logger.error("ADMS devicecmd parse error: %s", e)

        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])
