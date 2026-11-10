from odoo import models, fields, api, _

class StockDelayReport(models.Model):
    _name= 'stock.delay.report' 
    _description = 'Stock Delay Report'

    name = fields.Char()
    stock_delay_report_line_ids = fields.One2many('stock.delay.report.lines','stock_delay_report_id')

    def fetch_delay_report(self):
        self.stock_delay_report_line_ids = [(5,0,0)]
        list_of_vals = []
        delay_vals = {}
        order_line= False
        product = False
        qty_to_deliver = 0.0
        qty_to_receive = 0.0
        on_hand_qty = 0.0
        forecasted_qty = 0.0
        component_lines = False
        planned_pick_date = False
        date_planned = False
        sales_orders = self.env['sale.order'].sudo().search([
            ('is_pre_validate','=',True),
            ('planned_pick_date','!=',False),
            ('state','!=','cancel'),
            ('name','=','S00027')
        ])
        purchase_order_lines = False
        if sales_orders:
            for order in sales_orders:
                planned_pick_date = order.planned_pick_date
                order_line = order.order_line
                for line in order_line:
                    component_lines = line.component_line_ids.filtered(lambda cl: not cl.display_type and not cl.is_parent)
                    for component in component_lines:
                        product = component.product_id
                        qty_to_deliver = component.product_qty
                        on_hand_qty = product.qty_available
                        forecasted_qty = product.custom_virtual_available
                        if qty_to_deliver > on_hand_qty:
                            if forecasted_qty != 0.0:
                                purchase_order_lines = self.env['purchase.order.line'].sudo().search([
                                    ('product_id','=',product.id),
                                    ('order_id.is_pre_validate','=',True)
                                ])
                                purchase_order_lines = purchase_order_lines.filtered(lambda pol:pol.product_qty - pol.qty_received != 0)
                                if purchase_order_lines:
                                    for pol in purchase_order_lines:
                                        qty_to_receive = pol.product_qty - pol.qty_received
                                        date_planned = pol.date_planned.date()
                                        if  date_planned > planned_pick_date:
                                            delay_vals = {
                                                'stock_delay_report_id': self.id,
                                                'product_id': product.id,
                                                'qty_to_deliver': component.product_qty,
                                                'qty_to_receive': qty_to_receive,
                                                'purchase_order_id': pol.order_id.id,
                                                'sale_order_id': component.order_line_id.order_id.id,
                                                'product_delivery_date': planned_pick_date,
                                                'product_arrival_date': date_planned,
                                            }
                                            list_of_vals.append(delay_vals)
                                            delay_vals = {}
            self.env['stock.delay.report.lines'].sudo().create(list_of_vals)


class StockDelayReport(models.Model):
    _name= 'stock.delay.report.lines' 
    _description = 'Stock Delay Report'

    stock_delay_report_id = fields.Many2one('stock.delay.report')
    product_id = fields.Many2one('product.product')
    qty_to_deliver = fields.Float()
    qty_to_receive = fields.Float()
    purchase_order_id = fields.Many2one('purchase.order')
    sale_order_id = fields.Many2one('sale.order')
    product_delivery_date = fields.Date()
    product_arrival_date = fields.Date()
    qty_available = fields.Float(related='product_id.qty_available')

    # receipt_id = fields.Many2one('stock.picking', domain=[('picking_type_code','=','incoming')])
    # delivery_id = fields.Many2one('stock.picking', domain=[('picking_type_code','=','outgoing')])
    # receipt_stock_move_id = fields.Many2one('stock.move',domain=[('picking_id.picking_type_code','=','incoming')])
    # delivery_stock_move_id = fields.Many2one('stock.move',domain=[('picking_id.picking_type_code','=','outgoing')])

