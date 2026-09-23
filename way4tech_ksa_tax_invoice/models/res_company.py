# -*- coding: utf-8 -*-
import base64
import functools
import hashlib
import io
import math

from odoo import api, fields, models

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


class ResCompany(models.Model):
    _inherit = 'res.company'

    x_name_ar = fields.Char(string='Arabic Name')
    x_aramco_logo = fields.Binary(string='Saudi Aramco Vendor Logo')
    x_aramco_vendor_code = fields.Char(string='Saudi Aramco Vendor Code')

    # Part 2a (2026-08): a single pre-cropped header image (logo + English +
    # Arabic names combined into one image, matching the company's official
    # letterhead). When set, the Tax Invoice uses ONLY this image as the header,
    # replacing the dynamic three-part layout. Optional + additive — a company
    # without it keeps the current dynamic header unchanged. Recommended size
    # ~1000×200 px landscape (~5:1), rendered at full page width.
    x_invoice_header_image = fields.Binary(string='Invoice Header Image')

    # Item 3 (2026-08): footer counterpart of the header image. When set, it
    # replaces the dynamic footer (P.O. Box / email / vendor logo) on the Tax
    # Invoice with one pre-cropped image; empty = the dynamic footer unchanged.
    # Recommended ~1000×130 px landscape (~7.5:1), full page width.
    x_invoice_footer_image = fields.Binary(string='Invoice Footer Image')

    # Item 2b (2026-08): ONE IBAN shared by every company on the Tax Invoice.
    # Backed by a single global ir.config_parameter (NOT a per-company column),
    # so it is identical on every company and editable from any company's form —
    # changing it anywhere updates it everywhere. Account Number, Bank, Branch
    # and Swift stay per-company (read from the company's own bank record).
    x_shared_iban = fields.Char(
        string='Shared IBAN (all companies)',
        compute='_compute_x_shared_iban', inverse='_inverse_x_shared_iban',
        help='Single IBAN printed on every company\'s Tax Invoice. Stored once '
             'globally, so it is the same on all companies; Account Number, '
             'Bank, Branch and Swift remain per-company.')

    # ── Letterhead image geometry (2026-09-17) ──────────────────────────────
    # The header/footer images are whatever each company uploads, so nothing
    # below assumes a size: every decision is taken from the image's own aspect
    # ratio at render time. The aspect ratio is always kept (never stretched).
    PAGE_WIDTH_MM = {'A4': 210.0, 'A5': 148.0, 'A3': 297.0, 'Letter': 215.9, 'Legal': 215.9}
    INVOICE_HEADER_MAX_MM = 42
    INVOICE_FOOTER_MAX_MM = 30
    INVOICE_FOOTER_MIN_BAND_MM = 14

    @staticmethod
    @functools.lru_cache(maxsize=64)
    def _way4tech_trim_image(digest, data):
        """(base64, width/height) of the image with its blank border removed.

        Whatever a company uploads is used as-is, only the plain white (or
        transparent) margin around the artwork is cut off at render time, so
        the printed band is as tall as the artwork and no taller. The upload
        itself is never touched. A tiny padding is kept so anti-aliased edges
        are not clipped. Anything that cannot be read is returned unchanged.
        """
        try:
            im = Image.open(io.BytesIO(base64.b64decode(data)))
            fmt = im.format or 'PNG'
            if im.mode in ('RGBA', 'LA', 'P'):
                rgba = im.convert('RGBA')
                flat = Image.new('RGB', rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.split()[-1])
                im = flat
            gray = im.convert('L')
            bbox = gray.point(lambda v: 255 if v < 240 else 0).getbbox()
            if not bbox:
                return data, (im.width / float(im.height)) if im.height else None
            pad_x, pad_y = max(int(im.width * 0.01), 2), max(int(im.height * 0.03), 2)
            box = (max(bbox[0] - pad_x, 0), max(bbox[1] - pad_y, 0),
                   min(bbox[2] + pad_x, im.width), min(bbox[3] + pad_y, im.height))
            if box != (0, 0, im.width, im.height):
                im = im.crop(box)
                out = io.BytesIO()
                if fmt == 'JPEG':
                    im.convert('RGB').save(out, format='JPEG', quality=92)
                else:
                    im.save(out, format='PNG')
                data = base64.b64encode(out.getvalue())
            return data, (im.width / float(im.height)) if im.height else None
        except Exception:
            return data, None

    def _way4tech_invoice_image(self, field):
        """(base64, ratio) of the trimmed letterhead image in `field`;
        (False, None) when empty."""
        self.ensure_one()
        data = self[field]
        if not data or Image is None:
            return data, None
        if isinstance(data, str):
            data = data.encode()
        return self._way4tech_trim_image(hashlib.sha1(data).hexdigest(), data)

    def _way4tech_invoice_image_ratio(self, field):
        """width / height of the (trimmed) image in `field`, or None."""
        return self._way4tech_invoice_image(field)[1]

    @api.model
    def _way4tech_paper_usable_width_mm(self, paperformat):
        """Printable width of the page: paper width minus the side margins and
        the report body's own side padding (~4 mm each side)."""
        if paperformat.format == 'custom' and paperformat.page_width:
            width = paperformat.page_width
        else:
            width = self.PAGE_WIDTH_MM.get(paperformat.format, 210.0)
            if paperformat.orientation == 'Landscape':
                width = {'A4': 297.0, 'A5': 210.0, 'A3': 420.0, 'Letter': 279.4, 'Legal': 355.6}.get(paperformat.format, width)
        return max(width - (paperformat.margin_left or 0) - (paperformat.margin_right or 0) - 8.0, 50.0)

    def _way4tech_invoice_image_style(self, field, max_height_mm, usable_width_mm):
        """Inline CSS for a letterhead image: the full usable width when the
        image's shape allows it within `max_height_mm`, otherwise capped at
        that height and centred. Either way width and height stay in the
        image's own proportion. `max-width` alone never enlarges an image, so
        an upload narrower than the page used to print at its pixel size."""
        self.ensure_one()
        ratio = self._way4tech_invoice_image_ratio(field)
        if not ratio:
            return 'display:block; max-width:100%; height:auto; margin:0 auto;'
        if usable_width_mm / ratio <= max_height_mm:
            return 'display:block; width:100%; height:auto; margin:0 auto;'
        return 'display:block; height:%smm; width:auto; max-width:100%%; margin:0 auto;' % max_height_mm

    def _way4tech_invoice_footer_margin_mm(self, paperformat):
        """Bottom page margin (mm) for the Tax Invoice: exactly what the
        company's footer image needs at its printed size (a small gap above
        it, the image, the page-number line below), so the band is never
        taller than the artwork. Companies without a footer image keep the
        paper format's own margin for the dynamic footer."""
        self.ensure_one()
        base = paperformat.margin_bottom or 0
        ratio = self._way4tech_invoice_image_ratio('x_invoice_footer_image')
        if not ratio:
            return base
        usable = self._way4tech_paper_usable_width_mm(paperformat)
        height = min(usable / ratio, self.INVOICE_FOOTER_MAX_MM)
        return max(self.INVOICE_FOOTER_MIN_BAND_MM, int(math.ceil(height + 2.0 + 5.0)))

    # ── Letterhead alignment (2026-09-23) ──────────────────────────────────
    # This layout draws the letterhead INSIDE the document body (so it can
    # repeat per page), not in wkhtmltopdf's header band. A paper format with
    # a header band reserved for a classic layout (Odoo's A4 keeps 52 mm, the
    # Saudi A4 65 mm) therefore prints that space empty and pushes the
    # letterhead a third of the way down the page, and 0 mm side margins let it
    # run past the printable width. Companies on this layout need a format
    # shaped for it; the module ships one (report/paperformat.xml).
    LETTERHEAD_MAX_MARGIN_TOP_MM = 20.0
    LETTERHEAD_MIN_SIDE_MARGIN_MM = 5.0

    def _way4tech_letterhead_layout(self):
        return self.env.ref('way4tech_ksa_tax_invoice.external_layout_atco',
                            raise_if_not_found=False)

    def _way4tech_letterhead_paperformat(self):
        return self.env.ref('way4tech_ksa_tax_invoice.paperformat_ksa_tax_invoice',
                            raise_if_not_found=False)

    def _way4tech_effective_paperformat(self):
        """The paper format this company's reports actually print with."""
        self.ensure_one()
        return self.paperformat_id or self.env.ref('base.paperformat_euro',
                                                   raise_if_not_found=False)

    def _way4tech_letterhead_usable_width_mm(self):
        """Printable width (mm) of this company's page, for sizing the
        letterhead images. Falls back to A4 when nothing is configured."""
        self.ensure_one()
        pf = self._way4tech_effective_paperformat()
        if not pf:
            return 188.0
        return self._way4tech_paper_usable_width_mm(pf)

    def _way4tech_letterhead_paperformat_is_wrong(self):
        """True when this company prints the letterhead with a paper format
        that cannot place it correctly: a reserved top band it never uses, or
        no side margin so the letterhead overruns the printable width. A format
        already shaped for a body letterhead (this module's, or any sensible
        custom one) is left exactly as it is."""
        self.ensure_one()
        target = self._way4tech_letterhead_paperformat()
        pf = self._way4tech_effective_paperformat()
        if not target or not pf or pf == target:
            return False
        return ((pf.margin_top or 0.0) > self.LETTERHEAD_MAX_MARGIN_TOP_MM
                or (pf.margin_left or 0.0) < self.LETTERHEAD_MIN_SIDE_MARGIN_MM
                or (pf.margin_right or 0.0) < self.LETTERHEAD_MIN_SIDE_MARGIN_MM)

    def _way4tech_align_letterhead(self):
        """Point companies that use this letterhead layout at a paper format
        that can print it. Only a format that is demonstrably wrong for it is
        replaced; a company already set up correctly is never touched.
        Returns the companies that were changed."""
        layout = self._way4tech_letterhead_layout()
        target = self._way4tech_letterhead_paperformat()
        if not layout or not target:
            return self.browse()
        changed = self.browse()
        for company in self:
            if company.external_report_layout_id != layout:
                continue
            if company._way4tech_letterhead_paperformat_is_wrong():
                company.paperformat_id = target.id
                changed |= company
        return changed

    @api.model_create_multi
    def create(self, vals_list):
        """A new company prints its letterhead correctly without anyone having
        to configure it: it starts on this layout and its paper format, unless
        the values being created already say otherwise."""
        companies = super().create(vals_list)
        layout = companies._way4tech_letterhead_layout()
        target = companies._way4tech_letterhead_paperformat()
        for company, vals in zip(companies, vals_list):
            to_set = {}
            if layout and not vals.get('external_report_layout_id') and not company.external_report_layout_id:
                to_set['external_report_layout_id'] = layout.id
            if target and not vals.get('paperformat_id'):
                to_set['paperformat_id'] = target.id
            if to_set:
                # A paper format asked for in these values is kept as asked:
                # setting the layout here must not trigger the corrector.
                company.with_context(
                    way4tech_skip_letterhead_align=True).write(to_set)
            elif vals.get('paperformat_id'):
                # Created with an explicit format: honour it, never re-align.
                continue
        return companies

    def _compute_x_shared_iban(self):
        val = self.env['ir.config_parameter'].sudo().get_param(
            'way4tech_ksa_tax_invoice.shared_iban', '')
        for c in self:
            c.x_shared_iban = val

    def _inverse_x_shared_iban(self):
        for c in self:
            self.env['ir.config_parameter'].sudo().set_param(
                'way4tech_ksa_tax_invoice.shared_iban', c.x_shared_iban or '')

    def write(self, vals):
        """Mirror x_name_ar to the company's partner record so the tax invoice
        template (which reads bp.x_name_ar / cp.x_name_ar) stays in sync
        without the operator having to fill both places."""
        res = super().write(vals)
        if 'x_name_ar' in vals:
            for c in self:
                if c.partner_id and c.partner_id.x_name_ar != vals['x_name_ar']:
                    c.partner_id.sudo().write({'x_name_ar': vals['x_name_ar']})
        # Keep the letterhead printable: a company on this layout is re-aligned
        # when it is switched onto the layout, and when something writes a paper
        # format that cannot print a body letterhead. The Saudi localization
        # does exactly that - account.chart.template._get_sa_res_company sets
        # paperformat_l10n_sa_a4 (65 mm top band, no side margins) on every
        # company that loads the KSA chart of accounts, which is how the
        # letterheads ended up a third of the way down the page. A format that
        # can print the letterhead is always left alone, whoever set it.
        if not self.env.context.get('way4tech_skip_letterhead_align') and (
                'external_report_layout_id' in vals or 'paperformat_id' in vals):
            self._way4tech_align_letterhead()
        return res

    @api.model
    def _sync_ksa_arabic_to_partner(self):
        """Backfill: copy company.x_name_ar to company.partner_id.x_name_ar
        for every KSA company whose partner is missing the Arabic name. Run
        once on install/upgrade."""
        for c in self.search([]):
            if not c.partner_id or not c.x_name_ar:
                continue
            if not c.partner_id.x_name_ar:
                c.partner_id.sudo().write({'x_name_ar': c.x_name_ar})

    @api.model
    def _apply_ksa_atco_setup(self):
        view = self.env.ref(
            'way4tech_ksa_tax_invoice.external_layout_atco',
            raise_if_not_found=False,
        )
        paperformat = self.env.ref(
            'way4tech_ksa_tax_invoice.paperformat_ksa_tax_invoice',
            raise_if_not_found=False,
        )
        if not view or not paperformat:
            return
        for c in self.search([]):
            country_code = c.partner_id.country_id.code or ''
            vat = c.partner_id.vat or ''
            if country_code != 'SA' and not vat.startswith('3'):
                continue
            vals = {}
            if not c.external_report_layout_id:
                vals['external_report_layout_id'] = view.id
            if not c.paperformat_id:
                vals['paperformat_id'] = paperformat.id
            if vals:
                c.write(vals)

    @api.model
    def _apply_ksa_date_format(self):
        """Force English (en_US) date_format to DD/MM/YYYY across the system.

        This changes how every date renders in the Odoo backend UI (forms, list
        views, filters) AND in reports — invoice form, sale order, purchase
        order, journal entries, all of it. KSA business norm is DD/MM/YYYY.
        """
        lang = self.env['res.lang'].search([('code', '=', 'en_US')], limit=1)
        if lang and lang.date_format != '%d/%m/%Y':
            lang.sudo().write({'date_format': '%d/%m/%Y'})
