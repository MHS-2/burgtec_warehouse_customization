# -*- coding: utf-8 -*-
from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.burgtec_legacy_stock.models.lc_stock_inventory_report import LEGACY_ID_OFFSET


@tagged('post_install', '-at_install')
class TestLegacyStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        vals = {'type': 'consu', 'is_storable': True, 'custom_product_type': 'component'}
        Product = cls.env['product.product']
        cls.product = Product.create(dict(vals, name='Legacy Test Product', default_code='LEG-T1'))
        cls.untouched = Product.create(dict(vals, name='Legacy Untouched Product', default_code='LEG-T2'))
        cls.partner = cls.env['res.partner'].create({'name': 'Legacy Test Supplier'})
        cls.location = cls.env['stock.location'].create({
            'name': 'LEGBIN1', 'usage': 'internal',
            'location_id': cls.env.ref('stock.warehouse0').lot_stock_id.id})
        Legacy = cls.env['product.inventory.legacy.data']
        # extras per unit 2 + 1 + 1 = 4, 10 units
        cls.row1 = Legacy.create({
            'product_id': cls.product.id, 'partner_id': cls.partner.id, 'location_id': cls.location.id,
            'item_price_ex': 10.0, 'item_cbm': 0.01, 'item_exchange_cost': 2.0, 'item_duty_cost': 1.0,
            'item_freight_cost': 1.0, 'item_landed_cost': 14.0, 'stock_location': 10,
            'bin_location': 'LEGBIN1', 'stock_landed_total': 140.0,
            'import_batch': 'TEST', 'sheet_row': 2})
        # extras 0 (bought locally), 30 units
        cls.row2 = Legacy.create({
            'product_id': cls.product.id, 'item_price_ex': 5.0, 'item_landed_cost': 5.0,
            'stock_location': 30, 'bin_location': 'LEGBIN2', 'stock_landed_total': 150.0,
            'import_batch': 'TEST', 'sheet_row': 3})
        cls.Report = cls.env['lc.stock.inventory.report']

    def _legacy_rows(self):
        return self.Report.search([('legacy_id', 'in', (self.row1 + self.row2).ids)])

    # -- legacy data -------------------------------------------------------
    def test_extras_per_unit(self):
        self.assertEqual(self.row1.item_extras_cost, 4.0)
        self.assertEqual(self.row2.item_extras_cost, 0.0)

    def test_same_import_row_cannot_be_loaded_twice(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['product.inventory.legacy.data'].create({
                'product_id': self.untouched.id, 'stock_location': 1, 'import_batch': 'TEST', 'sheet_row': 2})

    def test_rows_without_batch_are_not_restricted(self):
        for _i in range(2):
            self.env['product.inventory.legacy.data'].create({'product_id': self.untouched.id, 'stock_location': 1})

    def test_product_cannot_be_deleted_while_it_has_legacy_data(self):
        with self.assertRaises(Exception), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.product.unlink()

    # -- report ------------------------------------------------------------
    def test_report_contains_legacy_rows(self):
        rows = self._legacy_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(set(rows.mapped('source')), {'legacy'})
        self.assertEqual(set(rows.mapped('id')), {LEGACY_ID_OFFSET + self.row1.id, LEGACY_ID_OFFSET + self.row2.id})

    def test_report_legacy_values(self):
        row = self._legacy_rows().filtered(lambda r: r.legacy_id == self.row1)
        self.assertEqual(row.product_id, self.product)
        self.assertEqual(row.partner_id, self.partner)
        self.assertEqual(row.quantity, 10)
        self.assertEqual(row.product_cost, 10.0)
        self.assertEqual(row.product_exchange_cost, 2.0)
        self.assertEqual(row.product_duty_cost, 1.0)
        self.assertEqual(row.product_freight_cost, 1.0)
        self.assertEqual(row.total_product_cost, 14.0)
        self.assertEqual(row.location_dest_id, self.location)
        self.assertEqual(row.currency_id, self.row1.currency_id)
        self.assertFalse(row.picking_ids)
        self.assertFalse(row.purchase_order_id)

    def test_report_is_searchable_on_the_extended_fields(self):
        self.assertIn(self.row1.id, self.Report.search([('partner_id', '=', self.partner.id)]).legacy_id.ids)
        self.assertNotIn(self.row2.id, self.Report.search([('partner_id', '=', self.partner.id)]).legacy_id.ids)
        # a condition on one side must not leak rows of the other side
        others = self.Report.search([('partner_id', '!=', self.partner.id), ('source', '=', 'legacy')])
        self.assertNotIn(self.row1.id, others.legacy_id.ids)
        self.assertIn(self.row2.id, others.legacy_id.ids)
        self.assertIn(self.row1.id, self.Report.search([('product_cost', '=', 10.0)]).legacy_id.ids)

    def test_bill_rows_are_unchanged(self):
        """Every bill row must give exactly what the original related/computed fields gave."""
        bills = self.Report.search([('source', '=', 'purchase')], limit=40)
        for row in bills:
            order = row.purchase_line_id.order_id
            self.assertEqual(row.partner_id, order.partner_id)
            self.assertEqual(row.currency_id, order.currency_id)
            self.assertEqual(row.product_cost, row.purchase_line_id.price_unit)
            self.assertAlmostEqual(row.total_product_cost,
                                   row.product_cost + row.product_exchange_cost + row.product_duty_cost
                                   + row.product_freight_cost, places=2)
        # reading everything on a mixed set must not fail
        (bills | self._legacy_rows()).read([
            'partner_id', 'partner_code', 'currency_id', 'product_cost', 'product_cbm', 'product_exchange_cost',
            'product_duty_cost', 'product_freight_cost', 'total_product_cost', 'location_dest_id', 'picking_ids'])

    def test_bill_rows_come_first(self):
        rows = self.Report.search([])
        sources = rows.mapped('source')
        self.assertEqual(sources, sorted(sources, reverse=True))   # 'purchase' before 'legacy'

    # -- product landed cost figures ---------------------------------------
    def test_product_landed_statistics_include_legacy(self):
        product = self.product
        self.assertAlmostEqual(product.average_landed_cost, 2.0)    # (4 + 0) / 2 batches
        self.assertAlmostEqual(product.maximum_landed_cost, 4.0)
        self.assertAlmostEqual(product.minimum_landed_cost, 0.0)
        self.assertAlmostEqual(product.latest_landed_cost, 1.0)     # (4*10 + 0*30) / 40 units

    def test_statistics_follow_legacy_changes(self):
        self.row2.item_freight_cost = 8.0
        self.assertAlmostEqual(self.product.maximum_landed_cost, 8.0)
        self.assertAlmostEqual(self.product.average_landed_cost, 6.0)
        self.assertAlmostEqual(self.product.latest_landed_cost, (4 * 10 + 8 * 30) / 40)
        self.row2.unlink()
        self.assertAlmostEqual(self.product.average_landed_cost, 4.0)

    def test_product_without_legacy_is_unchanged(self):
        self.assertEqual(self.untouched.average_landed_cost, 0)
        self.assertEqual(self.untouched.maximum_landed_cost, 0)
        self.assertEqual(self.untouched.minimum_landed_cost, 0)
        self.assertEqual(self.untouched.latest_landed_cost, 0)

    def test_statistics_blend_with_real_landed_costs(self):
        """A product that already has real landed costs: legacy batches are added, 'latest' stays real."""
        lines = self.env['stock.valuation.adjustment.lines'].search(
            [('additional_landed_cost_per_unit', '>', 0)], limit=1)
        if not lines:
            self.skipTest("no real landed cost in this database")
        product = lines.product_id
        # Stored figures of a copied database can be stale: start from a fresh original calculation.
        product.compute_average_landed_cost()
        product.compute_landed_costs()
        before = {name: product[name] for name in
                  ('average_landed_cost', 'maximum_landed_cost', 'minimum_landed_cost', 'latest_landed_cost')}
        adjustments = product.stock_valuation_adjustment_line_ids
        n_real = len(adjustments.cost_id)
        real_total = sum(adjustments.mapped('additional_landed_cost_per_unit'))
        self.env['product.inventory.legacy.data'].create({
            'product_id': product.id, 'item_price_ex': 1.0, 'item_freight_cost': 100.0,
            'item_landed_cost': 101.0, 'stock_location': 5})
        self.assertAlmostEqual(product.average_landed_cost, (real_total + 100.0) / (n_real + 1), places=2)
        self.assertAlmostEqual(product.maximum_landed_cost, max(before['maximum_landed_cost'], 100.0), places=2)
        self.assertAlmostEqual(product.minimum_landed_cost, min(before['minimum_landed_cost'], 100.0), places=2)
        self.assertAlmostEqual(product.latest_landed_cost, before['latest_landed_cost'], places=2)
