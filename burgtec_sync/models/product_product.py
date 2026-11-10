import logging
import requests
from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class ProductProductExt(models.Model):
    _inherit = 'product.product'

    burgtec_product_id = fields.Integer(string="Burgtec Variant ID", copy=False, readonly=True)
    burgtec_product_url = fields.Char(string="Burgtec Variant Link", copy=False, readonly=True)

    def action_open_burgtec_product(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.burgtec_product_url,
            "target": "new",
        }



    def _burgtec_get_params(self):
        icp = self.env['ir.config_parameter'].sudo()
        url = (icp.get_param('burgtec.sync_url') or '').strip().rstrip('/')
        db = (icp.get_param('burgtec.sync_db') or '').strip()
        token = (icp.get_param('burgtec.sync_token') or '').strip()
        return url, db, token

    def _call_burgtec_odoo_18_controller(self, code, exists=True):
        try:
            url, db, token = self._burgtec_get_params()
            if not (url and token):
                _logger.info("Burgtec sync skipped: URL or token not set in Settings.")
                return

            response = requests.post(f"{url}/warehouse/product_sync",params={'token': token, 'db': db},
                json={'default_code': code},
                timeout=30,
            )
            if response.status_code != 200:
                _logger.warning("Burgtec sync for %s returned HTTP %s",
                                code, response.status_code)
        except Exception as e:
            _logger.warning("Burgtec sync failed for %s: %s", code, e)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('created_from_api'):
            return records
        try:
            for rec in records:
                if rec.default_code and rec.custom_variant_type == 'product':
                    rec._call_burgtec_odoo_18_controller(rec.default_code)
        except Exception as e:
            _logger.warning("Burgtec sync (create) error: %s", e)
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('created_from_api'):
            return res
        if 'default_code' in vals or 'custom_variant_type' in vals:
            try:
                for rec in self:
                    if rec.default_code and rec.custom_variant_type == 'product':
                        rec._call_burgtec_odoo_18_controller(rec.default_code)
            except Exception as e:
                _logger.warning("Burgtec sync (write) error: %s", e)
        return res