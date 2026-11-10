# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.fields import Domain
from odoo.tools.misc import format_datetime


class StockAlertQuantityHistory(models.TransientModel):
    _name = 'stock.alert.quantity.history'
    _description = 'Stock Alert Quantity History'

    inventory_datetime = fields.Datetime('Inventory at Date',
        help="Choose a date to get the inventory at that date",
        default=fields.Datetime.now)

    def open_at_date(self):
        tree_view_id = self.env.ref('burgtec_warehouse_customization.view_stock_forecast_alert_report_list').id
        # form_view_id = self.env.ref('stock.product_form_view_procurement_button').id
        domain = Domain('is_storable', '=', True)
        product_id = self.env.context.get('product_id', False)
        product_tmpl_id = self.env.context.get('product_tmpl_id', False)
        # if product_id:
        #     domain &= Domain('id', '=', product_id)
        # elif product_tmpl_id:
        #     domain = Domain('product_tmpl_id', '=', product_tmpl_id)
        # We pass `to_date` in the context so that `qty_available` will be computed across
        # moves until date.
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'list')],
            'view_mode': 'list',
            'name': _('Stock Forecast Alert Report'),
            'res_model': 'stock.forecast.alert.report',
            # 'domain': domain,
            'context': dict(self.env.context, to_date=self.inventory_datetime),
            'display_name': format_datetime(self.env, self.inventory_datetime)
        }
        return action
