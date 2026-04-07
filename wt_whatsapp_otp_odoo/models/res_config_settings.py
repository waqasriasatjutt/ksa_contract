# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Enable / Disable ──────────────────────────────────────────────────
    wt_otp_enabled = fields.Boolean(
        string='WhatsApp OTP on Signup',
        config_parameter='wt_whatsapp_otp.enabled',
        help='When enabled, customers must verify their phone number via WhatsApp '
             'OTP before creating an account.',
    )

    # ── WhatsApp Cloud API credentials ────────────────────────────────────
    wt_whatsapp_token = fields.Char(
        string='WhatsApp API Token',
        config_parameter='wt_whatsapp_otp.token',
        help='Bearer token from Meta WhatsApp Cloud API.',
    )
    wt_whatsapp_phone_id = fields.Char(
        string='WhatsApp Phone Number ID',
        config_parameter='wt_whatsapp_otp.phone_id',
        help='Phone Number ID from Meta Business Manager.',
    )

    # ── Template ──────────────────────────────────────────────────────────
    wt_otp_template = fields.Char(
        string='OTP Template Name',
        config_parameter='wt_whatsapp_otp.otp_template',
        default='phone_otp',
        help='Name of the Meta-approved WhatsApp message template. '
             'The template must have one body variable: {{1}} for the OTP code.',
    )

    # ── Expiry ────────────────────────────────────────────────────────────
    wt_otp_expiry_minutes = fields.Integer(
        string='OTP Expiry (minutes)',
        config_parameter='wt_whatsapp_otp.expiry_minutes',
        default=10,
        help='How many minutes before a generated OTP expires.',
    )
