# -*- coding: utf-8 -*-
from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _build_wkhtmltopdf_args(self, *args, **kwargs):
        """Force wkhtmltopdf to read the report HTML as UTF-8.

        Without an explicit --encoding, wkhtmltopdf/Qt falls back to the
        process locale. This container's locale is 'C' (LANG unset), so it
        decodes the UTF-8 Arabic bytes as Latin-1 -> mojibake ("Ø§Ù„..."),
        while ASCII (English/numbers) stays fine. All Odoo report HTML is
        UTF-8, so forcing utf-8 is safe for every report on the instance.
        """
        command_args = super()._build_wkhtmltopdf_args(*args, **kwargs)
        if '--encoding' not in command_args:
            command_args = list(command_args) + ['--encoding', 'utf-8']
        return command_args
