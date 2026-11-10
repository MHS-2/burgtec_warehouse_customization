# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductInventoryLegacyData(models.Model):
    """One row per legacy (IT Hub) stock batch.

    The existing model already holds the sheet columns (price, CBM, exchange, duty, freight,
    landed cost, quantity, bin). This extension adds what is needed to use a batch as data:
    who supplied it, where it sits in Odoo and which import it came from.
    """
    _inherit = 'product.inventory.legacy.data'
    _order = 'product_id, id'

    item_extras_cost = fields.Monetary(
        string="Landed Extras per Unit", currency_field='currency_id',
        compute='_compute_item_extras_cost', store=True,
        help="Exchange + duty + freight per unit: the landed cost without the supplier price.")
    partner_id = fields.Many2one('res.partner', string="Supplier", index=True, ondelete='set null')
    supplier_name = fields.Char(string="Supplier (as imported)")
    supplier_code = fields.Char(string="Supplier Code (as imported)")
    location_id = fields.Many2one('stock.location', string="Odoo Location", index=True, ondelete='set null')
    sheet_row = fields.Integer(string="Import Row")
    import_batch = fields.Char(string="Import Batch", index=True)

    # NULLs are distinct in PostgreSQL, so rows created by hand (no batch) are not affected.
    _import_row_uniq = models.Constraint(
        'unique(import_batch, sheet_row)',
        "This import row has already been loaded.",
    )

    @api.depends('item_exchange_cost', 'item_duty_cost', 'item_freight_cost')
    def _compute_item_extras_cost(self):
        for row in self:
            row.item_extras_cost = row.item_exchange_cost + row.item_duty_cost + row.item_freight_cost
