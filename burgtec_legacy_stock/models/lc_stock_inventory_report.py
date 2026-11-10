# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools import SQL

# Legacy rows get ids above this offset so they can never collide with the bill line ids.
LEGACY_ID_OFFSET = 1_000_000_000


class LcStockInventoryReport(models.Model):
    """Adds the legacy stock batches to the report without touching the original.

    The original model keeps creating its own database view (vendor bill rows). The table query
    below reads that view and appends the legacy rows, so no SQL of the original is copied and
    nothing is renamed or dropped: uninstalling this module simply brings the plain view back.
    """
    _inherit = 'lc.stock.inventory.report'
    # Bill rows first, as before (newest first), then the legacy batches.
    _order = 'source desc, id desc'

    source = fields.Selection([('purchase', "Purchase"), ('legacy', "Legacy")], readonly=True)
    legacy_id = fields.Many2one('product.inventory.legacy.data', string="Legacy Record", readonly=True)

    # These three were related fields through the purchase order line, so they were empty for
    # anything that is not a bill. Same label and type as before, now also answered by a batch.
    partner_id = fields.Many2one('res.partner', string="Vendor", related=None,
                                 compute='_compute_partner_id', search='_search_partner_id')
    currency_id = fields.Many2one('res.currency', string="Currency", related=None,
                                  compute='_compute_currency_id', search='_search_currency_id')
    product_cost = fields.Float(string="Unit Price", digits='Product Price', related=None,
                                compute='_compute_product_cost', search='_search_product_cost')

    @property
    def _table_query(self):
        return SQL(
            """
            SELECT bill.id AS id,
                   bill.invoice_id AS invoice_id,
                   bill.purchase_line_id AS purchase_line_id,
                   bill.product_id AS product_id,
                   bill.quantity AS quantity,
                   NULL::integer AS legacy_id,
                   'purchase'::varchar AS source
              FROM lc_stock_inventory_report AS bill
             UNION ALL
            SELECT %(offset)s + legacy.id,
                   NULL::integer,
                   NULL::integer,
                   legacy.product_id,
                   legacy.stock_location::numeric,
                   legacy.id,
                   'legacy'::varchar
              FROM product_inventory_legacy_data AS legacy
            """,
            offset=LEGACY_ID_OFFSET,
        )

    # ------------------------------------------------------------------
    # Fields that now answer for both sources
    # ------------------------------------------------------------------
    def _compute_partner_id(self):
        for record in self:
            record.partner_id = (record.legacy_id.partner_id if record.legacy_id
                                 else record.purchase_line_id.order_id.partner_id)

    def _compute_currency_id(self):
        for record in self:
            if record.legacy_id:
                record.currency_id = record.legacy_id.currency_id or self.env.company.currency_id
            else:
                record.currency_id = record.purchase_line_id.order_id.currency_id

    def _compute_product_cost(self):
        for record in self:
            record.product_cost = (record.legacy_id.item_price_ex if record.legacy_id
                                   else record.purchase_line_id.price_unit)

    def _search_by_source(self, legacy_path, purchase_path, operator, value):
        """One domain that applies the condition to the right side of each row (also for != / not in)."""
        return [
            '|',
            '&', ('source', '=', 'legacy'), (legacy_path, operator, value),
            '&', ('source', '=', 'purchase'), (purchase_path, operator, value),
        ]

    def _search_partner_id(self, operator, value):
        return self._search_by_source('legacy_id.partner_id', 'purchase_line_id.order_id.partner_id',
                                      operator, value)

    def _search_currency_id(self, operator, value):
        return self._search_by_source('legacy_id.currency_id', 'purchase_line_id.order_id.currency_id',
                                      operator, value)

    def _search_product_cost(self, operator, value):
        return self._search_by_source('legacy_id.item_price_ex', 'purchase_line_id.price_unit',
                                      operator, value)

    # ------------------------------------------------------------------
    # Computed columns of the original: the original code runs for bill rows, legacy rows are
    # answered from the batch. (Rows of both kinds can be in one recordset.)
    # ------------------------------------------------------------------
    def compute_landed_costs(self):
        legacy = self.filtered('legacy_id')
        super(LcStockInventoryReport, self - legacy).compute_landed_costs()
        for record in legacy:
            batch = record.legacy_id
            record.product_exchange_cost = batch.item_exchange_cost
            record.product_duty_cost = batch.item_duty_cost
            record.product_freight_cost = batch.item_freight_cost

    def compute_total_product_cost(self):
        legacy = self.filtered('legacy_id')
        super(LcStockInventoryReport, self - legacy).compute_total_product_cost()
        for record in legacy:
            # The landed cost already used by the business, as imported.
            record.total_product_cost = record.legacy_id.item_landed_cost

    def compute_pickings(self):
        legacy = self.filtered('legacy_id')
        super(LcStockInventoryReport, self - legacy).compute_pickings()
        for record in legacy:
            record.picking_ids = False

    def compute_location_dest_id(self):
        legacy = self.filtered('legacy_id')
        super(LcStockInventoryReport, self - legacy).compute_location_dest_id()
        for record in legacy:
            record.location_dest_id = record.legacy_id.location_id
