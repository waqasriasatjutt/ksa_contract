# -*- coding: utf-8 -*-
import random
import string
from datetime import timedelta

from odoo import api, fields, models


class WtPhoneOtp(models.Model):
    _name = 'wt.phone.otp'
    _description = 'WhatsApp Phone OTP Verification'
    _rec_name = 'phone'
    _order = 'create_date desc'

    phone = fields.Char(string='Phone Number', required=True, index=True)
    code = fields.Char(string='OTP Code', required=True)
    expires_at = fields.Datetime(string='Expires At', required=True)
    used = fields.Boolean(string='Used', default=False)

    @api.model
    def generate_otp(self, phone, expiry_minutes=None):
        """Invalidate prior OTPs for this phone, create a fresh one, return code."""
        if expiry_minutes is None:
            try:
                expiry_minutes = int(
                    self.env['ir.config_parameter'].sudo().get_param(
                        'wt_whatsapp_otp.expiry_minutes', '10'
                    )
                )
            except (ValueError, TypeError):
                expiry_minutes = 10

        self.sudo().search([('phone', '=', phone), ('used', '=', False)]).write(
            {'used': True}
        )
        code = ''.join(random.choices(string.digits, k=6))
        self.sudo().create({
            'phone': phone,
            'code': code,
            'expires_at': fields.Datetime.now() + timedelta(minutes=expiry_minutes),
        })
        return code

    @api.model
    def verify_otp(self, phone, code):
        """Return True if OTP matches, is valid, and mark it as used."""
        otp = self.sudo().search([
            ('phone', '=', phone),
            ('code', '=', code),
            ('used', '=', False),
            ('expires_at', '>=', fields.Datetime.now()),
        ], limit=1)
        if otp:
            otp.write({'used': True})
            return True
        return False

    @api.model
    def peek_otp(self, phone, code):
        """Return True if OTP is valid WITHOUT consuming it (pre-submit check)."""
        otp = self.sudo().search([
            ('phone', '=', phone),
            ('code', '=', code),
            ('used', '=', False),
            ('expires_at', '>=', fields.Datetime.now()),
        ], limit=1)
        return bool(otp)

    @api.model
    def cron_cleanup_expired_otps(self):
        """Remove OTP records older than 1 hour."""
        cutoff = fields.Datetime.now() - timedelta(hours=1)
        self.sudo().search([('expires_at', '<', cutoff)]).unlink()
