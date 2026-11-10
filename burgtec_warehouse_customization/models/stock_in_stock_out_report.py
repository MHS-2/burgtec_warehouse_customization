# -*- coding: utf-8 -*-
import logging
from markupsafe import Markup
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockInStockOutReport(models.Model):
    _name = 'stock.in.stock.out.report'
    _description = 'StockInStockOutReport'

    name = fields.Char()
    date_from = fields.Date()
    date_to = fields.Date()
    product_id = fields.Many2one('product.product')
    dashboard_html = fields.Html()
    stock_summary_line_ids = fields.One2many('stock.summary.line','stock_in_stock_out_report_id')

    def fill_dashboard_html(self,res):
        lines = res
        # opening_value = sum(lines.mapped('stock_opening_value'))
        # received_value = sum(lines.mapped('received_value'))
        # picked_sold_value = sum(lines.mapped('picked_sold_value'))
        # closing_value = sum(lines.mapped('stock_closing_value'))
        current_qty_available_value = sum(lines.mapped('available_stock_value'))
        total_qty_purchased = sum(lines.mapped('purchased_qty'))
        total_qty_sold = sum(lines.mapped('total_to_sell_qty'))
        table_code = Markup("""
        <div class="row mt-4 mb-4">
            <div class="col">
                <div class="card border-0">
                    <div class="row card-body text-center align-items-center">
                        <div class="col-3">
                            <i class="fa-3x fa fa-arrow-down text-danger mt-1" aria-hidden="true"></i>
                        </div>
                        <div class="col-9 text-start mt-2" style="padding-left:0;">
                            <p class="mb-0">Purchased Qty</p>
                            <h3 class="fw-bold">{purchased_qty}</h3>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col">
                <div class="card border-0">
                    <div class="row card-body text-center align-items-center">
                        <div class="col-3">
                            <i class="fa-3x fa fa-arrow-up text-success mt-1" aria-hidden="true"></i>
                        </div>
                        <div class="col-9 text-start mt-2" style="padding-left:0;">
                            <p class="mb-0">Qty Used</p>
                            <h3 class="fw-bold">{total_qty_sold}</h3>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col">
                <div class="card border-0">
                    <div class="row card-body text-center align-items-center">
                        <div class="col-3">
                            <i class="fa-3x fa fa-cube text-primary mt-1" aria-hidden="true"></i>
                        </div>
                        <div class="col-9 text-start mt-2" style="padding-left:0;">
                            <p class="mb-0">Current On Hand Value</p>
                            <h3 class="fw-bold mt-0">$ {current_qty_available_value}</h3>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """).format(purchased_qty=round(total_qty_purchased,2), total_qty_sold=round(total_qty_sold,2), current_qty_available_value=round(current_qty_available_value,2))

        self.dashboard_html = table_code
    
    def fetch_report_data(self):
        res = False
        self.stock_summary_line_ids = [(5,0,0)]
        report_vals_list = []
        vals = {}
        sale_data = []
        date_from = self.date_from
        date_to = self.date_to
        if not date_from:
            raise ValidationError(_('Kindly select date from!'))
        if not date_to:
            raise ValidationError(_('Kindly select date to!'))
        
        date_from_month = date_from.month 
        date_to_month = date_to.month

        purchase_orders = self.env['purchase.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
            ('state','=','purchase'),
        ])

        sale_orders = self.env['sale.order'].sudo().search([
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
            ('state','=','sale'),
        ])

        if not purchase_orders and not sale_orders:
            raise ValidationError(_("No records found for Sales and Purchase in the given date range. !"))

        order_lines = sale_orders.mapped('order_line')
        purchase_order_lines = purchase_orders.mapped('order_line')
        component_lines = order_lines.mapped('component_line_ids')
        child_component_lines = component_lines.filtered(lambda c:not c.is_parent and not c.display_type)
        child_components = child_component_lines.mapped('product_id')

        for component in child_components:
            sold_picked_qty = 0
            remaining_qty_to_pick = 0
            specific_purchase_lines = purchase_order_lines.filtered(lambda pol:pol.product_id.id == component.id)
            bills = specific_purchase_lines.mapped('order_id.invoice_ids')
            specific_lines = child_component_lines.filtered(lambda cl:cl.product_id.id == component.id)
            specific_sale_orders = specific_lines.mapped('order_line_id.order_id')
            total_qty = sum(specific_lines.mapped('product_qty'))
            total_qty_purchased = sum(specific_purchase_lines.mapped('product_qty'))
            total_qty_received = sum(specific_purchase_lines.mapped('qty_received'))
            total_qty_billed = sum(specific_purchase_lines.mapped('qty_invoiced'))
            # qty_yet_to_receive = total_qty_purchased - total_qty_received

            bills_landed_cost = bills.mapped('landed_costs_ids')
            landed_cost_lines = bills_landed_cost.mapped('valuation_adjustment_lines')

            prod_landed_cost_lines = landed_cost_lines.filtered(lambda pl: pl.product_id.id == component.id)

            total_product_lc_per_unit = sum(prod_landed_cost_lines.mapped('additional_landed_cost_per_unit'))

            for so in specific_sale_orders:
                receipts = so.picking_ids.filtered(lambda p:p.state != 'cancel')
                done_receipts = receipts.filtered(lambda dp:dp.state == 'done')
                not_done_receipts = receipts - done_receipts

                done_moves = done_receipts.mapped('move_ids')
                not_done_moves = not_done_receipts.mapped('move_ids')
                specific_done_moves = done_moves.filtered(lambda sm:sm.product_id.id == component.id)
                specific_not_done_moves =  not_done_moves.filtered(lambda sm:sm.product_id.id == component.id)
                sold_picked_qty += sum(specific_done_moves.mapped('quantity'))
                remaining_qty_to_pick += sum(specific_not_done_moves.mapped('product_uom_qty'))

            vals = {
                'stock_in_stock_out_report_id': self.id,
                'purchased_qty': total_qty_purchased,
                'received_qty': total_qty_received,
                'total_qty_billed': total_qty_billed,
                'product_id': component.id,
                'total_to_sell_qty': total_qty,
                'picked_sold_qty': sold_picked_qty,
                'to_be_sell_qty': remaining_qty_to_pick,
                'total_landed_cost': total_product_lc_per_unit,
            }
            report_vals_list.append(vals)
            vals = {}
            
        if report_vals_list:
            res = self.env['stock.summary.line'].sudo().create(report_vals_list)  

        if res:
            self.fill_dashboard_html(res=res)  

    # Openning value does not make sense for now.
        # <div class="col">
        #     <div class="card border-0">
        #         <div class="row card-body text-center align-items-center">
        #             <div class="col-3">
        #                 <i class="fa-3x fa fa-cube text-info mt-1" aria-hidden="true"></i>
        #             </div>
        #             <div class="col-9 text-start mt-2" style="padding-left:0;">
        #                 <p class="mb-0">Opening Value</p>
        #                 <h3 class="fw-bold">$ {opening_value}</h3>
        #             </div>
        #         </div>
        #     </div>
        # </div>

    # Picked Sold Value Not Needed As these are components.
        #     <div class="col">
        #     <div class="card border-0">
        #         <div class="row card-body text-center align-items-center">
        #             <div class="col-3">
        #                 <i class="fa-3x fa fa-arrow-up text-danger mt-1" aria-hidden="true"></i>
        #             </div>
        #             <div class="col-9 text-start mt-2" style="padding-left:0;">
        #                 <p class="mb-0">Picked/Sold Value</p>
        #                 <h3 class="fw-bold">$ {picked_sold_value}</h3>
        #             </div>
        #         </div>
        #     </div>
        # </div>

    # def fetch_report_data(self):
    #     res = False
    #     self.stock_summary_line_ids = [(5,0,0)]
    #     report_vals_list = []
    #     vals = {}
    #     date_from = self.date_from
    #     date_to = self.date_to
    #     if not date_from:
    #         raise ValidationError(_('Kindly select date from!'))
    #     if not date_to:
    #         raise ValidationError(_('Kindly select date to!'))
    #     date_from_month = date_from.month 
    #     date_to_month = date_to.month
    #     account_obj = self.env['account.move']
    #     stock_move_line_obj = self.env['stock.move.line']
    #     # landed_cost_obj = self.env['stock.landed.cost']
    #     # posted bills for the data
    #     all_bills = account_obj.sudo().search([
    #         ('move_type','=','in_invoice'),
    #         ('state','in',['draft','posted']),
    #         ('date','>=',self.date_from),('date','<=',self.date_to)
    #     ])

    #     # posted invoices for the data
    #     all_invoices = account_obj.sudo().search([
    #         ('move_type','=','out_invoice'),
    #         ('state','in',['draft','posted']),
    #         ('date','>=',self.date_from),('date','<=',self.date_to)
    #     ])

    #     if not all_bills:
    #         raise ValidationError(_('No Bills Found in the given date range!'))

    #     # valuation_adjustment_lines

    #     # Make data from the bills.

    #     bill_lines = all_bills.mapped('invoice_line_ids').filtered(lambda b: not b.is_landed_costs_line)
    #     invoice_lines = all_invoices.mapped('invoice_line_ids').filtered(lambda i: not i.is_landed_costs_line)

    #     # Creating Data Product wise.
    #     bills_product_list = bill_lines.mapped('product_id')
    #     # invoice_product_list = invoice_lines.mapped('product_id')

    #     for product in bills_product_list:
    #         stock_open_qty = 0
    #         stock_open_value = 0
    #         stock_close_qty = 0
    #         stock_close_value = 0
    #         # Bills are created for components directly.
    #         prod_bill_lines = bill_lines.filtered(lambda pb:pb.product_id.id == product.id)
    #         # Invoices have parent products only.
    #         draft_inv_order_lines = invoice_lines.filtered(lambda i:i.move_id.state == 'draft').mapped('sale_line_ids')
    #         posted_inv_order_lines = invoice_lines.filtered(lambda i:i.move_id.state == 'posted').mapped('sale_line_ids')

    #         draft_source_component_lines = draft_inv_order_lines.component_line_ids.filtered(lambda c: not c.is_parent and c.product_id.id == product.id)
    #         source_component_lines = posted_inv_order_lines.component_line_ids.filtered(lambda c: not c.is_parent and c.product_id.id == product.id)

    #         # Stock Opening Logic
    #         prod_move_in_history = stock_move_line_obj.sudo().search([
    #             ('product_id', '=', product.id),
    #             ('state', '=', 'done'),           
    #             '|',
    #             ('picking_id.picking_type_code', '=', 'incoming'),
    #             ('reference', 'ilike', 'Physical'),
    #         ])

    #         # Stock Closing Logic
    #         prod_move_out_history = stock_move_line_obj.sudo().search([
    #             ('product_id', '=', product.id),
    #             ('state', '=', 'done'),           
    #             ('picking_id.picking_type_code', '=', 'outgoing'),
    #         ])

    #         prod_move_in_history = prod_move_in_history.filtered(lambda h:h.date.month == date_from_month)

    #         prod_move_out_history = prod_move_out_history.filtered(lambda h:h.date.month == date_to_month)

    #         if prod_move_in_history:
    #             for move_line in prod_move_in_history:
    #                 # stock_open_value+= move_line.quantity * move_line.move_id.purchase_line_id.price_unit
    #                 stock_open_qty+=move_line.quantity
            
    #         if prod_move_out_history:
    #             for move_line in prod_move_out_history:
    #                 stock_close_value+= move_line.quantity * move_line.move_id.sale_line_id.price_unit
    #                 stock_close_qty+=move_line.quantity


    #         bills = prod_bill_lines.mapped('move_id')
    #         # moves = prod_invoice_lines.mapped('move_id')
    #         uom = prod_bill_lines.mapped('product_uom_id')[0]
    #         bom = source_component_lines.mapped('component_id')
    #         bills_landed_cost = bills.mapped('landed_costs_ids')
    #         landed_cost_lines = bills_landed_cost.mapped('valuation_adjustment_lines')

    #         prod_landed_cost_lines = landed_cost_lines.filtered(lambda pl: pl.product_id.id == product.id)

    #         total_product_lc_per_unit = 0.0

    #         for lc_lines in prod_landed_cost_lines:
    #             line_lc = lc_lines.additional_landed_cost / lc_lines.quantity
    #             total_product_lc_per_unit+= line_lc

    #         # Recevied Qty
    #         rec_qty = sum(prod_bill_lines.mapped('quantity'))
    #         rec_value = sum(prod_bill_lines.mapped('price_subtotal'))

    #         # picked/sold Qty

    #         sold_qty = sum(source_component_lines.mapped('product_qty'))

    #         to_be_sell_qty = sum(draft_source_component_lines.mapped('product_qty'))

    #         total_to_sell_qty = sold_qty + to_be_sell_qty
    #         # as components do not have sales price we just picking its cost and multiplying by qty . Requires update later!
    #         # sold_value = product.standard_price * sold_qty

    #         vals['stock_in_stock_out_report_id'] = self.id
    #         vals['product_id'] = product.id
    #         vals['uom_id'] = uom.id
    #         vals['stock_opening_qty'] = stock_open_qty
    #         # vals['stock_opening_value'] = stock_open_value
    #         vals['received_qty'] = rec_qty
    #         vals['received_value'] = rec_value
    #         vals['total_to_sell_qty'] = total_to_sell_qty
    #         vals['to_be_sell_qty'] = to_be_sell_qty
    #         vals['picked_sold_qty'] = sold_qty
    #         # vals['picked_sold_value'] = sold_value
    #         vals['stock_closing_qty'] = stock_close_qty
    #         vals['stock_closing_value'] = stock_close_value
    #         vals['total_landed_cost'] = total_product_lc_per_unit
    #         report_vals_list.append(vals)
    #         vals = {}
        
    #     if report_vals_list:
    #         res = self.env['stock.summary.line'].sudo().create(report_vals_list)
        
    #     if res:
    #         self.fill_dashboard_html(res=res)


class StockSummaryLine(models.Model):
    _name = 'stock.summary.line'
    _description = 'StockSummaryLine'

    stock_in_stock_out_report_id = fields.Many2one('stock.in.stock.out.report', ondelete='cascade')

    product_id = fields.Many2one('product.product')
    currency_id = fields.Many2one('res.currency',related='product_id.currency_id')
    uom_id = fields.Many2one(related='product_id.uom_id')

    stock_opening_qty = fields.Float()
    stock_opening_value = fields.Monetary(currency_field="currency_id")

    purchased_qty = fields.Float()
    received_qty = fields.Float()
    total_qty_billed = fields.Float()
    received_value = fields.Monetary(currency_field="currency_id")

    total_to_sell_qty = fields.Float()
    to_be_sell_qty = fields.Float()

    picked_sold_qty = fields.Float()
    picked_sold_value = fields.Monetary(currency_field="currency_id") 

    stock_closing_qty = fields.Float()
    stock_closing_value = fields.Monetary(currency_field="currency_id")

    qty_available = fields.Float(related='product_id.qty_available')
    available_stock_value = fields.Monetary(currency_field="currency_id",compute="_compute_available_stock_value")

    total_landed_cost = fields.Monetary(currency_field="currency_id")

    def _compute_available_stock_value(self):
        for record in self:
            record.available_stock_value = record.qty_available * record.product_id.standard_price




