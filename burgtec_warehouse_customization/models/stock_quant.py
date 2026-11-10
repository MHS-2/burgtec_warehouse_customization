# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    product_weight = fields.Float(related="product_id.weight",store=True)
    weight_uom_name = fields.Char(related="product_id.weight_uom_name", store=True)
    
