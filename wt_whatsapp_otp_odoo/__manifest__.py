# -*- coding: utf-8 -*-
{
    'name': 'WT WhatsApp OTP — Signup Verification',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'sequence': 130,
    'summary': 'Verify customer phone numbers via WhatsApp OTP during Odoo signup',
    'description': """
WT WhatsApp OTP — Signup Verification
======================================
Adds WhatsApp-based phone number verification to the standard Odoo signup page.

Features:
- Injects phone + OTP fields into the standard /web/signup page
- Sends a 6-digit OTP via WhatsApp Cloud API (Meta) on request
- Verifies OTP before account is created
- Saves verified phone to partner on successful signup
- Auto-links new account to existing portal partner by email (no duplicates)
- OTP expiry configurable (default 10 minutes)
- Cron cleanup of expired OTP records
- Works with ANY Odoo module — completely standalone

Configuration:
  Settings → General Settings → WhatsApp OTP section
    - Enable WhatsApp OTP on Signup
    - WhatsApp API Token (Meta Cloud API Bearer token)
    - WhatsApp Phone Number ID
    - OTP Template Name (Meta-approved template, default: phone_otp)
    - OTP Expiry Minutes
    """,
    'author': 'Waqas Riasat',
    'maintainer': 'Way4Tech',
    'website': 'https://way4tech.com',
    'support': 'info@way4tech.com',
    'license': 'OPL-1',
    'price': 20.0,
    'currency': 'USD',
    'images': ['static/description/banner.png'],

    'depends': [
        'base_setup',
        'auth_signup',
        'portal',
        'website',
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/config_data.xml',
        'data/cron.xml',
        'views/config_views.xml',
        'views/signup_templates.xml',
    ],

    'application': False,
    'installable': True,
    'auto_install': False,
}
