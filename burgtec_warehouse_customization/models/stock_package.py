# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockPackage(models.Model):
    _inherit = 'stock.package'

    def _get_default_weight_uom(self):
        return self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()
    
    def _get_default_cbm_uom(self):
        return self.env['product.template']._get_volume_uom_name_from_ir_config_parameter()

    unit_cbm = fields.Float(compute="compute_unit_cbm", digits=(16, 5), help="Divides Selected Package Type's CBM by Total quanities from Products.", store=True)
    unit_weight = fields.Float(compute="compute_unit_weight", digits=(16, 5), help="Divides Selected Package Type's Weight by Total quanities from Products.", store=True)
    weight_uom_name = fields.Char(string='Weight unit of measure label', compute='_compute_weight_uom_name', default=_get_default_weight_uom)
    cbm_uom_name = fields.Char(string='CBM unit of measure label', compute='_compute_cbm_uom_name', default=_get_default_cbm_uom)

    # Related fields
    cbm = fields.Float(related="package_type_id.cbm",store=True)
    base_weight = fields.Float(related="package_type_id.base_weight",store=True)

    total_weight = fields.Float(compute="compute_total_weight",digits=(16, 5),store=True)



    @api.depends('quant_ids','package_type_id','package_type_id.cbm')
    def compute_unit_cbm(self):
        for record in self:
            quants = record.quant_ids
            package_type = record.package_type_id
            total_qtys = 0.0
            if not quants:
                record.unit_cbm = 0
                continue
            if quants:
                total_qtys = sum(quants.mapped('quantity'))
                if not package_type:
                    record.unit_cbm = 0
                    continue
                if total_qtys > 0:
                    record.unit_cbm = package_type.cbm / total_qtys
                else:
                    record.unit_cbm = 0
    
    @api.depends('package_type_id','total_weight',)
    def compute_unit_weight(self):
        for record in self:
            quants = record.quant_ids
            package_type = record.package_type_id
            total_qtys = 0.0
            if not quants:
                record.unit_weight = 0
                continue
            if quants:
                total_qtys = sum(quants.mapped('quantity'))
                if not package_type:
                    record.unit_weight = 0
                    continue
                if total_qtys > 0:
                    record.unit_weight = record.total_weight / total_qtys
                else:
                    record.unit_weight = 0
    
    def _compute_weight_uom_name(self):
        for package in self:
            package.weight_uom_name = self.env['product.template']._get_weight_uom_name_from_ir_config_parameter()
    
    def _compute_cbm_uom_name(self):
        for package in self:
            package.cbm_uom_name = self.env['product.template']._get_volume_uom_name_from_ir_config_parameter()
        
    @api.depends('quant_ids','base_weight','quant_ids.product_weight')
    def compute_total_weight(self):
        for record in self:
            quants = record.quant_ids
            if not quants:
                record.total_weight = 0
                continue
            if quants:
                record.total_weight = record.base_weight + sum(quants.mapped('product_weight'))
