# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _,  tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockForecastAlertReport(models.Model):
    _name = 'stock.forecast.alert.report'
    _description = 'StockForecastAlertReport'
    _auto = False
    _order = 'id desc'

    product_id = fields.Many2one('product.product')
    product_tmpl_id = fields.Many2one('product.template')
    
    qty_available = fields.Float(related='product_id.qty_available')

    incoming_qty = fields.Float(related='product_id.incoming_qty')
    outgoing_qty = fields.Float(related='product_id.outgoing_qty')

    custom_incoming_qty = fields.Float(related='product_id.custom_incoming')
    custom_outgoing_qty = fields.Float(related='product_id.custom_outgoing')

    forecasted_qty = fields.Float(related='product_id.virtual_available')
    custom_forecasted = fields.Float(related='product_id.custom_virtual_available')

    status = fields.Selection([
        ('healthy','Healthy'),
        ('low','Low'),
        ('negative','Negative')
    ],compute="_compute_status", search='_search_status')

    bom_ids = fields.One2many(related='product_id.bom_ids')

    variant_bom_ids = fields.One2many(related='product_id.variant_bom_ids')

    related_sale_order_ids = fields.Many2many('sale.order',compute='compute_related_sos')

    def compute_related_sos(self):
        for record in self:
            related_boms = False
            related_orders = False
            confirmed_orders = False
            dt_object = False
            bom_component_lines = record.env['sale.order.bom.component.line'].sudo()
            related_boms = bom_component_lines.search(['&',('product_id','=',record.product_id.id),('is_parent','=',False)]).mapped('component_id')
            related_orders = related_boms.mapped('order_id')
            if record.env.context.get('to_date'):
                dt_object = fields.Datetime.to_datetime(record.env.context.get('to_date'))
            if dt_object:
                related_orders = related_orders.filtered(lambda o:o.create_date <= dt_object)
            if related_orders:
                confirmed_orders = related_orders.filtered(lambda o:o.state == 'sale')
                if confirmed_orders:
                    record.related_sale_order_ids = confirmed_orders
                else:
                    record.related_sale_order_ids = False
            else:
                record.related_sale_order_ids = False


    def _compute_status(self):
        for record in self:
            forecast = record.custom_forecasted
            minimum = record.product_id.minimum_qty

            if forecast < 0:
                record.status = 'negative'
            elif forecast < minimum:
                record.status = 'low'
            else:
                record.status = 'healthy'
    
    def _search_status(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            raise UserError(_("Unsupported operator: %s", operator))

        if isinstance(value, str):
            values = {value}
        elif value is False or value is None:
            values = set()
        else:
            values = set(value)   # works for list, tuple, set, OrderedSet

        matching = self.search([]).filtered(lambda r: r.status in values)
        return [('id', 'in' if operator in ('=', 'in') else 'not in', matching.ids)]
    
    def action_product_forecast_report(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.stock_forecasted_product_product_action")
        return action
    
    def fetch_related_orders(self):
        related_orders = self.related_sale_order_ids
        bom = False
        component_lines = False
        total_qty = 0.0
        order_data = []
        vals = {}
        if not related_orders:
            return order_data
        if related_orders:
            for order in related_orders:
                bom = order.bom_component_id
                component_lines = bom.component_line_ids.filtered(lambda c:not c.is_parent and c.product_id.id == self.product_id.id)
                total_qty = sum(component_lines.mapped('product_qty'))
                vals = {
                    'order_id': order.id,
                    'name':order.name,
                    'date_order':order.date_order,
                    'scheduled_date':order.validity_date,
                    'customer': order.partner_id.name,
                    'quantity': total_qty,
                }
                order_data.append(vals)
                vals = {}
            return order_data
    
    @api.model
    def retrieve_dashboard(self, records, result):
        StockForcast = self.env['stock.forecast.alert.report']
        list_records = False
        low_or_negative = 0
        lowest_forecast_value = 0
        highest_forecast_value = 0
        incoming_qty = 0
        outgoing_qty = 0
        product_ids = records
        if not product_ids:
            list_records = StockForcast.sudo().search([],limit=80)
            low_or_negative = list_records.filtered(lambda l:l.status == 'low' or l.status == 'negative')
            lowest_forecast_value = min(list_records.mapped('custom_forecasted'))
            highest_forecast_value = max(list_records.mapped('custom_forecasted'))
            lowest_forecast_product = list_records.filtered(lambda lfc:lfc.custom_forecasted == lowest_forecast_value)[0]
            highest_forecast_product = list_records.filtered(lambda lfc:lfc.custom_forecasted == highest_forecast_value)[0]
            incoming_qty = sum(list_records.mapped('custom_incoming_qty'))
            outgoing_qty = sum(list_records.mapped('custom_outgoing_qty'))
            result = {
                'limit': len(list_records),
                'low_or_negative' : len(low_or_negative),
                'lowest_forecast_value' : lowest_forecast_value,
                'highest_forecast_value' : highest_forecast_value,
                'lowest_forecast_product_name': lowest_forecast_product.product_id.name if lowest_forecast_product else "-",
                'highest_forecast_product_name': highest_forecast_product.product_id.name if highest_forecast_product else "-",
                'incoming_qty' : incoming_qty,
                'outgoing_qty' : outgoing_qty,
            }
            return result
        # list_records = StockForcast.sudo().browse(product_ids)
        # low_or_negative = list_records.filtered(lambda l:l.status == 'low' or l.status == 'negative')
        # lowest_forecast_value = min(list_records.mapped('forecasted_qty'))
        # highest_forecast_value = max(list_records.mapped('forecasted_qty'))
        # lowest_forecast_product = list_records.filtered(lambda lfc:lfc.forecasted_qty == lowest_forecast_value)[0]
        # highest_forecast_product = list_records.filtered(lambda lfc:lfc.forecasted_qty == highest_forecast_value)[0]
        # incoming_qty = sum(list_records.mapped('incoming_qty'))
        # outgoing_qty = sum(list_records.mapped('outgoing_qty'))
        # len(list_records[offset:limit])
        
        # Records with low or negative status
        list_records = result
        low_or_negative = [
            record for record in list_records
            if record.get('status') in ('low', 'negative')
        ]

        # Lowest and highest forecast values
        lowest_forecast_value = min(
            (record['forecasted_qty'] for record in list_records),
            default=0
        )
        highest_forecast_value = max(
            (record['forecasted_qty'] for record in list_records),
            default=0
        )

        # Products with the lowest and highest forecast values
        lowest_forecast_product = next(
            (record for record in list_records
            if record['forecasted_qty'] == lowest_forecast_value),
            None
        )

        highest_forecast_product = next(
            (record for record in list_records
            if record['forecasted_qty'] == highest_forecast_value),
            None
        )

        # Total incoming and outgoing quantities
        incoming_qty = sum(
            record.get('incoming_qty', 0) for record in list_records
        )

        outgoing_qty = sum(
            record.get('outgoing_qty', 0) for record in list_records
        )
        result = {
            'limit': len(list_records),
            'low_or_negative' : len(low_or_negative),
            'lowest_forecast_value' : lowest_forecast_value,
            'highest_forecast_value' : highest_forecast_value,
            # 'lowest_forecast_product_name': lowest_forecast_product.product_id.name if lowest_forecast_product else "-",
            # 'highest_forecast_product_name': highest_forecast_product.product_id.name if highest_forecast_product else "-",
            'incoming_qty' : incoming_qty,
            'outgoing_qty' : outgoing_qty,
        }
        return result

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
        CREATE OR REPLACE VIEW stock_forecast_alert_report AS (
        SELECT
        min(pp.id) AS id,
        pp.id as product_id,
        pp.product_tmpl_id as product_tmpl_id
        FROM product_product AS pp
        WHERE pp.custom_variant_type = 'component'
        GROUP BY pp.id
        );
        """
        self.env.cr.execute(query)
