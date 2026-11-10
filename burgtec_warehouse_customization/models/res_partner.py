# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    supplier_code = fields.Char()

    # Manual Unit Cost Fields Now Added Here. Product will get its field's filled by the vendor now.
    standard_freight_cost_per_cbm = fields.Monetary(string='Standard Freight Cost per CBM',currency_field="currency_id")
    standard_exchange_rate = fields.Float(string='Standard Exchange Rate')
    standard_duty_or_tax = fields.Float(string='Standard Duty/Tax')

    is_landed_cost_vendor = fields.Boolean(default=False)
    product_ids = fields.Many2many('product.product')

