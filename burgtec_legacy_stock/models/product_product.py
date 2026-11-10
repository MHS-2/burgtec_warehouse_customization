# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductProduct(models.Model):
    """Lets the landed cost figures of a product take its legacy batches into account.

    The original calculation runs first and is left as it is. Where a product has legacy
    batches, each batch then counts like one landed cost record: its extras per unit
    (exchange + duty + freight). Legacy stock is older than anything recorded in Odoo, so
    the "latest" figure keeps coming from the latest real landed cost when there is one.
    """
    _inherit = 'product.product'

    legacy_data_ids = fields.One2many('product.inventory.legacy.data', 'product_id',
                                      string="Legacy Inventory Data")

    @api.depends('legacy_data_ids.item_extras_cost')
    def compute_average_landed_cost(self):
        super().compute_average_landed_cost()
        for product in self.filtered('legacy_data_ids'):
            extras = product.legacy_data_ids.mapped('item_extras_cost')
            adjustments = product.stock_valuation_adjustment_line_ids
            # Same terms as the original (total per unit over the landed cost records), taken from
            # the lines and not from the rounded stored average, so no precision is lost.
            real_total = sum(adjustments.mapped('additional_landed_cost_per_unit'))
            landed_costs = len(adjustments.cost_id)
            product.average_landed_cost = (real_total + sum(extras)) / (landed_costs + len(extras))

    @api.depends('legacy_data_ids.item_extras_cost', 'legacy_data_ids.stock_location')
    def compute_landed_costs(self):
        super().compute_landed_costs()
        for product in self.filtered('legacy_data_ids'):
            batches = product.legacy_data_ids
            extras = batches.mapped('item_extras_cost')
            if product.stock_valuation_adjustment_line_ids.cost_id:
                product.maximum_landed_cost = max(product.maximum_landed_cost, max(extras))
                product.minimum_landed_cost = min(product.minimum_landed_cost, min(extras))
                continue
            product.maximum_landed_cost = max(extras)
            product.minimum_landed_cost = min(extras)
            quantity = sum(batches.mapped('stock_location'))
            if quantity:
                product.latest_landed_cost = sum(
                    batch.item_extras_cost * batch.stock_location for batch in batches) / quantity
            else:
                product.latest_landed_cost = sum(extras) / len(extras)
