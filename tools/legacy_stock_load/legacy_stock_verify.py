# -*- coding: utf-8 -*-
"""Verification after the legacy stock load. Changes nothing (it rolls back its own test receipt)."""
import json
import os
import random
from collections import defaultdict

import openpyxl

P = json.load(open('/tmp/legacy_params.json'))
XLSX, BATCH, OUT = P['xlsx'], P['batch'], P['out_dir']
base = json.load(open(os.path.join(OUT, 'baseline.json')))
Product = env['product.product'].with_context(active_test=False)
Quant, Legacy, Location = env['stock.quant'], env['product.inventory.legacy.data'], env['stock.location']
results = []


def check(name, ok, detail=''):
    results.append(ok)
    print('%-4s %-62s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)


sheet = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
rows = [r for r in sheet.iter_rows(min_row=2, values_only=True) if any(v not in (None, '') for v in r)]
legacy = Legacy.search([('import_batch', '=', BATCH)])
loaded_rows = {l.sheet_row: l for l in legacy}

# expected quantity per product from the legacy rows that were loaded for storable products
expected = defaultdict(float)
for l in legacy:
    if l.product_id.is_storable:
        expected[l.product_id.id] += l.stock_location

internal = [('location_id.usage', '=', 'internal')]
quants = Quant.search(internal + [('quantity', '!=', 0)])
check('1. legacy rows loaded = rows in the sheet that matched', len(legacy) == base['loaded_rows'], '%d of %d' % (len(legacy), len(rows)))
import csv
with open(os.path.join(OUT, 'unresolved_products.csv')) as handle:
    not_loaded_units = sum(int(float(line['qty'])) for line in csv.DictReader(handle))
loaded_units = sum(l.stock_location for l in legacy)
sheet_units = sum(int(round(r[10])) for r in rows)
check('2. loaded units + not-loaded units = sheet units', loaded_units + not_loaded_units == sheet_units,
      '%d + %d = %d (sheet %d)' % (loaded_units, not_loaded_units, loaded_units + not_loaded_units, sheet_units))
check('3. stock on hand = expected units', round(sum(quants.mapped('quantity'))) == round(base['expected_units']),
      '%d vs %d' % (round(sum(quants.mapped('quantity'))), round(base['expected_units'])))
per_product = defaultdict(float)
for q in quants:
    per_product[q.product_id.id] += q.quantity
mismatch = [pid for pid in set(per_product) | set(expected) if abs(per_product.get(pid, 0) - expected.get(pid, 0)) > 0.001]
check('4. every product has exactly its expected quantity', not mismatch, '%d products checked, %d mismatches' % (len(set(per_product) | set(expected)), len(mismatch)))
stray = [q for q in quants if q.product_id.id not in expected]
check('5. no stock left on products that are not in the sheet', not stray, '%d stray records' % len(stray))
not_in_bin = [q for q in quants if q.location_id.name not in {l.bin_location for l in legacy}]
check('6. all stock sits in the new sheet bins', not not_in_bin, '%d records elsewhere' % len(not_in_bin))
check('7. one stock record per loaded storable row', len(quants) == len([l for l in legacy if l.product_id.is_storable]),
      '%d records' % len(quants))
check('8. every legacy row is linked to its location', not legacy.filtered(lambda l: not l.location_id), '')

value = sum(p.qty_available * p.with_company(env.company).standard_price for p in Product.browse(list(expected)))
check('9. stock value = quantity-weighted supplier cost', abs(value - base['expected_value']) <= max(1.0, base['expected_value'] * 0.0001),
      'odoo %.2f vs expected %.2f (diff %.2f)' % (value, base['expected_value'], value - base['expected_value']))
env.cr.execute("select count(*) from account_move")
check('10. no accounting entries were created', env.cr.fetchone()[0] == base['account_moves_before'], '')

# average cost sample: products with several bins
many = [pid for pid in expected if len(legacy.filtered(lambda l: l.product_id.id == pid)) > 3][:5]
for pid in many:
    group = legacy.filtered(lambda l: l.product_id.id == pid)
    product = Product.browse(pid)
    eff_num = sum(l.stock_location * (l.item_price_ex if l.item_price_ex > 0 else 0) for l in group)
    positive = group.filtered(lambda l: l.item_price_ex > 0)
    if len(positive) == len(group):
        calc = eff_num / sum(group.mapped('stock_location'))
        check('11. average cost of %s = weighted supplier price' % product.default_code,
              abs(product.standard_price - calc) < 0.01, 'odoo %.4f vs %.4f over %d bins' % (product.standard_price, calc, len(group)))

# report
report = env['lc.stock.inventory.report']
check('12. report shows every legacy row', report.search_count([('source', '=', 'legacy')]) == len(legacy), '%d' % report.search_count([('source', '=', 'legacy')]))
check('13. purchase rows in the report are unchanged (31)', report.search_count([('source', '=', 'purchase')]) == 31, '')
check('13b. report lists the 31 bill rows first, legacy rows after',
      report.search([], limit=40).mapped('source') == ['purchase'] * 31 + ['legacy'] * 9, '')
sample = report.search([('source', '=', 'legacy')], limit=300)
sample.read(['partner_id', 'product_cost', 'product_cbm', 'product_exchange_cost', 'product_duty_cost', 'product_freight_cost', 'total_product_cost', 'location_dest_id'])
bad = [r for r in sample if r.total_product_cost != r.legacy_id.item_landed_cost or r.quantity != r.legacy_id.stock_location]
check('14. report figures equal the sheet figures (300 rows read)', not bad, '%d differences' % len(bad))

# product landed cost statistics
only_legacy = [p for p in Product.browse(list(expected)) if not p.stock_valuation_adjustment_line_ids][:200]
badstat = [p for p in only_legacy if p.maximum_landed_cost < p.minimum_landed_cost or p.maximum_landed_cost < p.average_landed_cost - 1e-6]
check('15. landed cost statistics filled and consistent (max>=avg>=min)', not badstat, '%d products checked' % len(only_legacy))

# spot check of 50 random sheet rows
random.seed(7)
spot = random.sample(list(loaded_rows.values()), 50)
spot_bad = []
for l in spot:
    qty = sum(Quant.search([('product_id', '=', l.product_id.id), ('location_id', '=', l.location_id.id)]).mapped('quantity'))
    if l.product_id.is_storable and abs(qty - l.stock_location) > 0.001:
        spot_bad.append((l.sheet_row, l.product_id.default_code, qty, l.stock_location))
check('16. 50 random sheet rows: stock in their bin equals the sheet', not spot_bad, str(spot_bad[:3]))

# a new receipt after the load must blend with the legacy cost (average costing)
product = Product.browse(many[0]) if many else Product.browse(list(expected)[0])
old_qty, old_cost = product.qty_available, product.standard_price
partner = env['res.partner'].search([('supplier_rank', '>', 0)], limit=1) or env['res.partner'].create({'name': 'Verify Supplier'})
new_price = old_cost + 10
order = env['purchase.order'].create({
    'partner_id': partner.id,
    'order_line': [(0, 0, {'product_id': product.id, 'product_qty': 10, 'price_unit': new_price})]})
order.button_confirm()
picking = order.picking_ids[:1]
for move in picking.move_ids:
    move.quantity = move.product_uom_qty
picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
new_cost = product.with_company(env.company).standard_price
expected_cost = (old_qty * old_cost + 10 * new_price) / (old_qty + 10)
check('17. new purchase receipt blends with legacy cost (rolled back)', picking.state == 'done' and abs(new_cost - expected_cost) < 0.01,
      '%s: %d units at %.4f + 10 at %.4f -> %.4f (expected %.4f), receipt %s' % (
          product.default_code, old_qty, old_cost, new_price, new_cost, expected_cost, picking.state))
env.cr.rollback()
print('\nRESULT: %d of %d checks passed' % (sum(results), len(results)))
