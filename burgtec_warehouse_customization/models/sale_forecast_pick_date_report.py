from odoo import fields, models, api, Command, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

class SaleForecastPickDateReport(models.Model):
    _name = 'sale.forecast.pick.date.report'
    _description = "SaleForecastPickDateReport"
    _order = 'planned_pick_date'
    _rec_name = ''

    component_id = fields.Many2one('product.product')
    # on_hand_qty = fields.Float()
    on_hand_qty = fields.Char()
    incoming_qty = fields.Float()
    demand_qty = fields.Float()
    order_id = fields.Many2one('sale.order')
    order_line_id = fields.Many2one('sale.order.line')
    planned_pick_date = fields.Date()


    def _compute_display_name(self):
        for record in self:
            record.display_name = "Sale Forecast Pick Date Report"
        # return super()._compute_display_name()
