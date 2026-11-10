# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class LcStockInventoryReport(models.Model):
    _name = 'lc.stock.inventory.report'
    _description = 'Landed Cost Stock Inventory Report'
    _auto = False
    _order = 'id desc'

    purchase_line_id = fields.Many2one('purchase.order.line')
    purchase_order_id = fields.Many2one(related='purchase_line_id.order_id')
    partner_id = fields.Many2one(related='purchase_order_id.partner_id')
    partner_code = fields.Char(related='partner_id.supplier_code')
    # stock_picking_id = fields.Many2one('stock.picking', string="Receipt")
    # stock_location_id = fields.Many2one(related="stock_picking_id.location_dest_id")

    currency_id = fields.Many2one(related="purchase_order_id.currency_id")

    product_id = fields.Many2one('product.product')
    product_reference = fields.Char(related="product_id.default_code")
    product_cost = fields.Float(related="purchase_line_id.price_unit")
    product_cbm = fields.Float(related="product_id.product_cbm")
    qty_available = fields.Float(related="product_id.qty_available")

    invoice_id = fields.Many2one('account.move')
    invoice_date = fields.Date(related="invoice_id.invoice_date")
    quantity = fields.Float()

    picking_ids = fields.Many2many('stock.picking',compute="compute_pickings")

    location_dest_id = fields.Many2one('stock.location', compute="compute_location_dest_id")
    


    # landed costs
    product_exchange_cost = fields.Monetary(compute="compute_landed_costs", currency_field="currency_id")
    product_duty_cost = fields.Monetary(compute="compute_landed_costs",currency_field="currency_id")
    product_freight_cost = fields.Monetary(compute="compute_landed_costs",currency_field="currency_id")

    total_product_cost = fields.Monetary(compute="compute_total_product_cost",currency_field="currency_id")


    def compute_total_product_cost(self):
        for record in self:
            # record.total_product_cost = record.product_cost 
            record.total_product_cost = record.product_cost + record.product_exchange_cost + record.product_duty_cost + record.product_freight_cost
    
    def compute_landed_costs(self):
        for record in self:
            record.product_freight_cost = 0
            record.product_exchange_cost = 0
            record.product_duty_cost = 0

            landed_costs = record.invoice_id.landed_costs_ids

            if not landed_costs:
                continue

            adjustments = landed_costs.valuation_adjustment_lines.filtered(lambda l: l.product_id == record.product_id)

            for adj in adjustments:
                cost_name = adj.cost_line_id.name or ''

                if 'Freight' in cost_name:
                    record.product_freight_cost += adj.additional_landed_cost

                if 'Exchange' in cost_name:
                    record.product_exchange_cost += adj.additional_landed_cost

                if 'Duty' in cost_name:
                    record.product_duty_cost += adj.additional_landed_cost
    
    def compute_pickings(self):
        for record in self:
            purchase_order_line = record.purchase_line_id
            moves = False
            if not purchase_order_line:
                record.picking_ids = False
            if purchase_order_line:
                moves = purchase_order_line.move_ids
                if not moves:
                  record.picking_ids = False
                if moves:  
                    for move in moves:
                        record.picking_ids = [(4,move.picking_id.id,0)]
    
    def compute_location_dest_id(self):
        for record in self:
            pickings = record.picking_ids
            if not pickings:
                record.location_dest_id = False
                continue
            if pickings:
                pickings = pickings.sorted('id')
                record.location_dest_id = pickings[-1].location_dest_id.id

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
        CREATE OR REPLACE VIEW lc_stock_inventory_report AS (
        SELECT
        min(aml.id) AS id,
        aml.move_id as invoice_id,
        aml.purchase_line_id AS purchase_line_id,
        aml.product_id AS product_id,
        aml.quantity AS quantity
        FROM account_move_line AS aml
        WHERE aml.purchase_line_id is not null 
        GROUP BY aml.id
        );
        """
        self.env.cr.execute(query)
    
    

