# -*- coding: utf-8 -*-
from collections import defaultdict
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SalesForecastByPickDate(models.TransientModel):
    _name = 'sales.forecast.by.pick.date'
    _description = 'Sales Forecast By Pick Date'

    date_from = fields.Date()
    date_to = fields.Date()
    company_id = fields.Many2one('res.company')

    def fetch_report(self):
        sales_order = self.env['sale.order'].sudo()
        purchase_order = self.env['purchase.order'].sudo()
        date_from = self.date_from
        date_to = self.date_to
        line_vals = []
        if not date_from or not date_to:
            raise UserError(_('Date fields can not be empty!!!'))
        
        sale_quotes = sales_order.search([
            ('planned_pick_date', '>=', date_from),
            ('planned_pick_date', '<=', date_to),
            ('state','!=','cancel'),
        ])

        purchase = purchase_order.search([
            ('date_planned', '>=', date_from),
            ('date_planned', '<=', date_to),
            ('state','!=','cancel'),
            ('is_pre_validate','=',True),
        ])

        purchase_order_lines = purchase.order_line.filtered(lambda ol: not ol.display_type and ol.product_qty - ol.qty_received != 0)
        incoming_dict = defaultdict(float)
        if purchase_order_lines:
            for ol in purchase_order_lines:
                incoming_dict[ol.product_id.id] += ol.product_qty - ol.qty_received



        order_lines = sale_quotes.mapped('order_line')
        component_lines = order_lines.mapped('component_line_ids')
        child_component_lines = component_lines.filtered(lambda c:not c.is_parent and not c.display_type)
        child_components = child_component_lines.mapped('product_id')


        for line in child_component_lines:
            # specific_lines = child_component_lines.filtered(lambda sl:sl.product_id.id == component.id)
            # specific_order_lines = specific_lines.mapped('order_line_id')
            # specific_order = specific_order_lines.mapped('order_id')
            # total_demand_qty = sum(specific_lines.mapped('product_qty'))
            bom_component = line.component_id
            order = bom_component.order_id
            product = line.product_id
            vals = {
                'component_id':product.id,
                'on_hand_qty': str(product.qty_available),
                'incoming_qty': incoming_dict[product.id] if incoming_dict[product.id] else 0.0,
                'demand_qty': line.product_qty,
                'order_id': order.id,
                'order_line_id':line.order_line_id.id,
                'planned_pick_date': order.planned_pick_date,
            }
            line_vals.append(vals)
            vals = {}
        
        sale_report = self.env['sale.forecast.pick.date.report']
        old_records = self.env['sale.forecast.pick.date.report'].search([])
        if old_records:
            old_records.unlink()
        sale_report.create(line_vals)
        return self.env.ref(
            'burgtec_warehouse_customization.action_sale_forecast_pick_date_report'
        ).read()[0]
        # return {
        #     'type': 'ir.actions.act_window',
        #     'name': _("Sale Forecast Pick Date Report"),
        #     'res_model': 'sale.forecast.pick.date.report',
        #     'view_id': self.env.ref('burgtec_warehouse_customization.view_sale_forecast_pick_date_report_list').id,
        #     'view_mode': 'list',
        # }






        