from odoo import fields, models, api
from odoo.addons.web.controllers import domain


class ManualLandedCostLine(models.Model):
    _name = 'manual.landed.cost.line'
    _description = 'Manual Landed Cost Line'

    product_id = fields.Many2one('product.product', 'Product')

    landed_cost_product_id = fields.Many2one('product.product', 'Landed Cost Product', required=True,
                                             domain="[('landed_cost_ok','=',True)]")
    currency_id = fields.Many2one(related='product_id.currency_id', store=True)

    product_manual_landed_cost = fields.Monetary(string='Cost', currency_field='currency_id',
                                                 compute="compute_product_manual_landed_cost", store=True,
                                                 readonly=False)

    @api.depends('landed_cost_product_id')
    def compute_product_manual_landed_cost(self):
        for record in self:
            if not record.landed_cost_product_id:
                record.product_manual_landed_cost = 0
                continue
            if record.landed_cost_product_id:
                record.product_manual_landed_cost = record.landed_cost_product_id.standard_price
