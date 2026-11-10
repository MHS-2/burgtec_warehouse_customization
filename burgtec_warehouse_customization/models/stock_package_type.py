# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    def _get_default_cbm_uom(self):
        return self.env['product.template']._get_volume_uom_name_from_ir_config_parameter()

    cbm = fields.Float(compute="compute_cbm",store=True)
    cbm_uom_name = fields.Char(string='CBM unit of measure label', compute='_compute_cbm_uom_name', default=_get_default_cbm_uom)

    @api.depends('packaging_length','width','height')
    def compute_cbm(self):
        for record in self:
            record.cbm = (record.packaging_length * record.width * record.height) / 1000000000 # Conversion mm3 to m3.
    
    def _compute_cbm_uom_name(self):
        for package_type in self:
            package_type.cbm_uom_name = self.env['product.template']._get_volume_uom_name_from_ir_config_parameter()
