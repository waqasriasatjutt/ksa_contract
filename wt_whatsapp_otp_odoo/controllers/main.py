# -*- coding: utf-8 -*-
import json
import urllib.request

from odoo import fields, http
from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome


# ── OTP API routes ────────────────────────────────────────────────────────────

class WtWhatsappOtpController(http.Controller):

    @http.route('/wa/send-otp', type='json', auth='public', website=True)
    def wa_send_otp(self, phone=None, **kw):
        """Generate OTP and send it via WhatsApp Cloud API."""
        if not phone:
            return {'success': False, 'error': 'Phone number required.'}

        phone = phone.strip().replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            phone = '+' + phone

        params = request.env['ir.config_parameter'].sudo()

        if not params.get_param('wt_whatsapp_otp.enabled'):
            return {'success': False, 'error': 'OTP verification is not enabled.'}

        token = params.get_param('wt_whatsapp_otp.token', '')
        phone_id = params.get_param('wt_whatsapp_otp.phone_id', '')
        if not token or not phone_id:
            return {'success': False, 'error': 'WhatsApp API is not configured.'}

        code = request.env['wt.phone.otp'].sudo().generate_otp(phone)

        template = params.get_param('wt_whatsapp_otp.otp_template', 'phone_otp')
        payload = json.dumps({
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'template',
            'template': {
                'name': template,
                'language': {'code': 'en_US'},
                'components': [{
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': code}],
                }],
            },
        }).encode('utf-8')

        req = urllib.request.Request(
            f'https://graph.facebook.com/v18.0/{phone_id}/messages',
            data=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # OTP stored locally; WhatsApp delivery failure is non-fatal

        return {'success': True}

    @http.route('/wa/verify-otp', type='json', auth='public', website=True)
    def wa_verify_otp(self, phone=None, code=None, **kw):
        """Peek-check OTP without consuming it (pre-submit inline validation)."""
        if not phone or not code:
            return {'valid': False}

        phone = phone.strip().replace(' ', '').replace('-', '')
        if not phone.startswith('+'):
            phone = '+' + phone

        valid = request.env['wt.phone.otp'].sudo().peek_otp(phone, str(code).strip())
        return {'valid': valid}


# ── Signup override: inject OTP gate ─────────────────────────────────────────

class WtAuthSignup(AuthSignupHome):

    def get_auth_signup_qcontext(self):
        qcontext = super().get_auth_signup_qcontext()
        p = request.env['ir.config_parameter'].sudo()
        otp_enabled = bool(p.get_param('wt_whatsapp_otp.enabled'))
        qcontext['wt_otp_enabled'] = otp_enabled
        qcontext['wt_phone'] = request.params.get('phone', '')

        if request.httprequest.method == 'POST' and 'error' not in qcontext:

            # ── Auto-link existing partner by email (no duplicate contacts) ──
            if not qcontext.get('token'):
                email = request.params.get('login', '').strip().lower()
                if email:
                    partner = request.env['res.partner'].sudo().search(
                        [('email', '=', email), ('user_ids', '=', False)], limit=1
                    )
                    if partner:
                        try:
                            partner._signup_prepare()
                            qcontext['token'] = partner.signup_token
                        except Exception:
                            pass

            # ── OTP validation ────────────────────────────────────────────
            if otp_enabled:
                phone = request.params.get('phone', '').strip()
                otp_code = request.params.get('otp_code', '').strip()
                if not phone:
                    qcontext['error'] = (
                        'Phone number is required for WhatsApp verification.'
                    )
                elif not otp_code:
                    qcontext['error'] = (
                        'Please verify your phone number via WhatsApp OTP before signing up.'
                    )
                else:
                    clean = phone.replace(' ', '').replace('-', '')
                    if not clean.startswith('+'):
                        clean = '+' + clean
                    if not request.env['wt.phone.otp'].sudo().verify_otp(clean, otp_code):
                        qcontext['error'] = (
                            'Invalid or expired OTP. Please request a new code.'
                        )

        return qcontext

    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False)
    def web_auth_signup(self, *args, **kw):
        response = super().web_auth_signup(*args, **kw)

        # Save verified phone to the newly created partner
        p = request.env['ir.config_parameter'].sudo()
        if (request.httprequest.method == 'POST'
                and bool(p.get_param('wt_whatsapp_otp.enabled'))):
            phone = request.params.get('phone', '').strip()
            uid = request.session.uid
            if phone and uid and uid != request.env.ref('base.public_user').id:
                try:
                    clean = phone.replace(' ', '').replace('-', '')
                    if not clean.startswith('+'):
                        clean = '+' + clean
                    user = request.env['res.users'].sudo().browse(uid)
                    if user.exists() and not user.partner_id.phone:
                        user.partner_id.sudo().write({'phone': clean, 'mobile': clean})
                except Exception:
                    pass

        return response
