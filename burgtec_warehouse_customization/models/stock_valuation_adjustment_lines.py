# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockValuationAdjustmentLines(models.Model):
    _inherit = 'stock.valuation.adjustment.lines'

    additional_landed_cost_per_unit = fields.Monetary(compute="compute_additional_landed_cost_per_unit", currency_field="currency_id",store=True)

    @api.depends('additional_landed_cost', 'quantity')
    def compute_additional_landed_cost_per_unit(self):
        for record in self:
            record.additional_landed_cost_per_unit = record.additional_landed_cost / record.quantity

