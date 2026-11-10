# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductInventoryLegacyData(models.Model):
    _name = 'product.inventory.legacy.data'
    _description = 'ProductInventoryLegacyData'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.product', required=True)
    currency_id = fields.Many2one(related="product_id.currency_id")

    item_price_ex = fields.Monetary(currency_field="currency_id")
    item_cbm = fields.Float(digits=(16,10),)
    item_exchange_cost = fields.Monetary(currency_field="currency_id")
    item_duty_cost = fields.Monetary(currency_field="currency_id")
    item_freight_cost = fields.Monetary(currency_field="currency_id")
    item_landed_cost = fields.Monetary(currency_field="currency_id")
    stock_location = fields.Integer(string="Stock @ Location")
    bin_location = fields.Char()
    stock_landed_total = fields.Monetary(string="Stock @ Landed Total", currency_field="currency_id")


