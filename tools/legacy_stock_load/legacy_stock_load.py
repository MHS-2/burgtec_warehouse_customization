# -*- coding: utf-8 -*-
"""Legacy (IT Hub) stock load for the Burgtec warehouse. Run inside the Odoo shell:

    odoo shell -d <db> --no-http < legacy_stock_load.py

Parameters are read from /tmp/legacy_params.json:
    {"xlsx": "/tmp/legacy.xlsx", "batch": "LEGACY-2026-11-09", "out_dir": "/tmp/legacy_out", "mode": "check"|"apply"}

mode "check"  : reads everything, writes the exception lists and prints the plan. Changes nothing.
mode "apply"  : 1. creates one location per sheet bin under BG/WH/Stock
                2. sets ALL current internal stock to zero (inventory adjustments, history kept)
                3. sets each product's cost to the quantity-weighted supplier price of its sheet rows
                   (Odoo cost is kept where the sheet price is 0)
                4. creates the legacy data rows (one per sheet row, exactly as in the sheet)
                5. books the sheet stock per bin with inventory adjustments
Rules agreed with the business:
  * Odoo cost = supplier price ("Item Price Ex"); landed extras stay separate in the legacy rows.
  * sheet price 0 -> keep the cost Odoo already has; if Odoo has none either, the cost stays 0.
  * product codes that exist several times: the single ACTIVE product, else the active one whose
    name equals the sheet name, else the row is NOT loaded and is listed for a decision.
"""
import csv
import json
import os
import time
from collections import defaultdict

import openpyxl

P = json.load(open('/tmp/legacy_params.json'))
XLSX, BATCH, OUT, MODE = P['xlsx'], P['batch'], P['out_dir'], P['mode']
assert MODE in ('check', 'apply'), 'mode must be check or apply'
# product codes whose cost must be 0 when the sheet price is 0 (decided by the business)
FORCE_ZERO = set(P.get('force_zero_cost', []))
os.makedirs(OUT, exist_ok=True)
company = env.company


def say(*args):
    print('[%s]' % time.strftime('%H:%M:%S'), *args, flush=True)


def write_csv(name, header, data):
    with open(os.path.join(OUT, name), 'w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(data)


Product = env['product.product'].with_context(active_test=False)
Partner = env['res.partner']
Location = env['stock.location']
Quant = env['stock.quant']
Legacy = env['product.inventory.legacy.data']

say('mode:', MODE, '| batch:', BATCH, '| company:', company.name)
if Legacy.search_count([('import_batch', '=', BATCH)]):
    raise SystemExit('Batch %s is already loaded. Stopping.' % BATCH)

# ---------------------------------------------------------------- 1. read the sheet
sheet = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
rows = []
for number, raw in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
    if not any(v not in (None, '') for v in raw):
        continue
    rows.append({
        'row': number, 'ref': str(raw[0]).strip(), 'supcode': str(raw[1]).strip() if raw[1] not in (None, '') else '',
        'name': str(raw[2] or '').strip(), 'supplier': str(raw[3] or '').strip(),
        'price': float(raw[4] or 0), 'cbm': float(raw[5] or 0), 'exch': float(raw[6] or 0),
        'duty': float(raw[7] or 0), 'frt': float(raw[8] or 0), 'landed': float(raw[9] or 0),
        'qty': int(round(float(raw[10] or 0))), 'bin': str(raw[11] or '').strip(), 'total': float(raw[12] or 0),
    })
say('sheet rows:', len(rows), '| units:', sum(r['qty'] for r in rows))
assert all(r['qty'] > 0 and r['bin'] for r in rows), 'every row needs a quantity above 0 and a bin'
assert len({r['bin'] for r in rows}) == len(rows), 'bins must be unique per row'

# ---------------------------------------------------------------- 2. products
candidates = defaultdict(lambda: env['product.product'])
for product in Product.search([('default_code', 'in', sorted({r['ref'] for r in rows}))]):
    candidates[product.default_code] |= product


def resolve(row):
    found = candidates.get(row['ref'])
    if not found:
        return None, 'code not found'
    active = found.filtered('active')
    if len(active) == 1:
        return active, ''
    if not active:
        return None, 'only archived products have this code'
    named = active.filtered(lambda p: (p.name or '').strip().casefold() == row['name'].casefold())
    if len(named) == 1:
        return named, ''
    return None, '%d active products share this code and the name does not decide' % len(active)


unresolved, loadable = [], []
for row in rows:
    product, reason = resolve(row)
    if product:
        row['product'] = product
        loadable.append(row)
    else:
        unresolved.append((row, reason))
say('products resolved for', len(loadable), 'rows;', len(unresolved), 'rows cannot be matched')

# ---------------------------------------------------------------- 3. suppliers
partner_cache, missing_suppliers = {}, defaultdict(int)
for row in loadable:
    name = row['supplier']
    if name not in partner_cache:
        found = Partner.search([('name', '=', name)])
        partner_cache[name] = found if len(found) == 1 else Partner
    row['partner'] = partner_cache[name]
    if not row['partner']:
        missing_suppliers[name] += 1

# ---------------------------------------------------------------- 4. costs
before_cost = {}
for row in loadable:
    product = row['product']
    if product.id not in before_cost:
        before_cost[product.id] = product.with_company(company).standard_price
    row['odoo_cost'] = before_cost[product.id]
    if row['price'] > 0:
        row['eff_cost'] = row['price']
    elif row['ref'] in FORCE_ZERO:
        row['eff_cost'] = 0.0      # catch-all / labour items whose Odoo cost is not a stock cost
    else:
        row['eff_cost'] = row['odoo_cost']

stock_rows = [r for r in loadable if r['product'].is_storable]
non_storable = [r for r in loadable if not r['product'].is_storable]
by_product = defaultdict(list)
for row in stock_rows:
    by_product[row['product'].id].append(row)
avg_cost = {pid: sum(r['qty'] * r['eff_cost'] for r in group) / sum(r['qty'] for r in group)
            for pid, group in by_product.items()}
zero_price = [r for r in loadable if r['price'] == 0]
zero_both = [r for r in zero_price if r['odoo_cost'] == 0]

# ---------------------------------------------------------------- 5. exception lists
write_csv('unresolved_products.csv', ['sheet_row', 'code', 'sheet_name', 'qty', 'reason', 'candidates (id|active|name|on_hand)'],
          [(r['row'], r['ref'], r['name'], r['qty'], why,
            ' ; '.join('%s|%s|%s|%s' % (c.id, c.active, c.name, c.qty_available) for c in candidates.get(r['ref'], [])))
           for r, why in unresolved])
write_csv('non_storable_rows.csv', ['sheet_row', 'code', 'qty', 'product_id', 'product_name'],
          [(r['row'], r['ref'], r['qty'], r['product'].id, r['product'].name) for r in non_storable])
write_csv('missing_suppliers.csv', ['supplier_in_sheet', 'rows'], sorted(missing_suppliers.items()))
write_csv('zero_cost_rows.csv', ['sheet_row', 'code', 'qty', 'sheet_price', 'odoo_cost_kept', 'cost_used'],
          [(r['row'], r['ref'], r['qty'], r['price'], r['odoo_cost'], r['eff_cost']) for r in zero_price])
write_csv('costs_before.csv', ['product_id', 'default_code', 'standard_price'],
          [(pid, Product.browse(pid).default_code, cost) for pid, cost in sorted(before_cost.items())])

expected_value = sum(r['qty'] * r['eff_cost'] for r in stock_rows)
existing_quants = Quant.search([('location_id.usage', '=', 'internal'), ('quantity', '!=', 0)])
say('PLAN -----------------------------------------------------------')
say('rows loaded into legacy table      :', len(loadable), '(units %d)' % sum(r['qty'] for r in loadable))
say('rows NOT loaded (cannot match)     :', len(unresolved), '(units %d)' % sum(r['qty'] for r, _ in unresolved))
say('rows of non-storable products      :', len(non_storable), '(legacy row yes, stock no; units %d)' % sum(r['qty'] for r in non_storable))
say('stock rows to book                 :', len(stock_rows), '| products', len(by_product), '| units', sum(r['qty'] for r in stock_rows))
say('value at cost used                 : %.2f' % expected_value)
say('rows with sheet price 0            :', len(zero_price), '| Odoo cost kept for', len(zero_price) - len(zero_both), '| no cost anywhere (0):', len(zero_both))
say('suppliers not found                :', dict(missing_suppliers))
say('existing stock to remove           :', len(existing_quants), 'records,', round(sum(existing_quants.mapped('quantity'))), 'units')
parent = Location.search([('complete_name', '=', 'BG/WH/Stock')], limit=1)
assert parent, 'location BG/WH/Stock not found'
present = {l.name: l for l in Location.search([('location_id', '=', parent.id)])}
to_create = sorted({r['bin'] for r in loadable} - set(present))
say('locations to create under', parent.complete_name, ':', len(to_create), '| already existing with that name:', len({r['bin'] for r in loadable} & set(present)))

if MODE == 'check':
    say('CHECK ONLY - nothing was changed. Lists written to', OUT)
    raise SystemExit(0)

# ================================================================ APPLY
env.cr.execute("select count(*) from account_move")
moves_before = env.cr.fetchone()[0]
json.dump({'account_moves_before': moves_before, 'existing_quants': len(existing_quants),
           'existing_units': sum(existing_quants.mapped('quantity')), 'expected_units': sum(r['qty'] for r in stock_rows),
           'expected_value': expected_value, 'loaded_rows': len(loadable), 'locations_to_create': len(to_create)},
          open(os.path.join(OUT, 'baseline.json'), 'w'))

# 1. locations
say('1/5 creating locations ...')
for start in range(0, len(to_create), 500):
    Location.create([{'name': b, 'location_id': parent.id, 'usage': 'internal', 'company_id': company.id}
                     for b in to_create[start:start + 500]])
env.cr.commit()
location_by_bin = {l.name: l for l in Location.search([('location_id', '=', parent.id)])}

# 2. remove all current stock
say('2/5 removing current stock:', len(existing_quants), 'records ...')
adjust = Quant.with_context(inventory_mode=True, inventory_name='Legacy stock load %s: clear old stock' % BATCH)
for start in range(0, len(existing_quants), 200):
    chunk = adjust.browse(existing_quants.ids[start:start + 200])
    chunk.write({'inventory_quantity': 0, 'inventory_quantity_set': True})
    chunk.action_apply_inventory()
    env.cr.commit()
left = Quant.search_count([('location_id.usage', '=', 'internal'), ('quantity', '!=', 0)])
say('    internal stock records left after clearing:', left)
assert left == 0, 'old stock was not fully removed'

# 3. product costs
say('3/5 setting product costs ...')
for pid, cost in avg_cost.items():
    Product.browse(pid).with_company(company).standard_price = cost
env.cr.commit()

# 4. legacy rows
say('4/5 creating legacy rows ...')
legacy_vals = [{
    'product_id': r['product'].id, 'partner_id': r['partner'].id or False, 'supplier_name': r['supplier'],
    'supplier_code': r['supcode'], 'item_price_ex': r['price'], 'item_cbm': r['cbm'],
    'item_exchange_cost': r['exch'], 'item_duty_cost': r['duty'], 'item_freight_cost': r['frt'],
    'item_landed_cost': r['landed'], 'stock_location': r['qty'], 'bin_location': r['bin'],
    'location_id': location_by_bin[r['bin']].id, 'stock_landed_total': r['total'],
    'sheet_row': r['row'], 'import_batch': BATCH,
} for r in loadable]
for start in range(0, len(legacy_vals), 500):
    Legacy.create(legacy_vals[start:start + 500])
    env.cr.commit()
    say('    legacy rows created:', min(start + 500, len(legacy_vals)))

# 5. book the stock
say('5/5 booking stock per bin ...')
book = Quant.with_context(inventory_mode=True, inventory_name='Legacy stock load %s' % BATCH)
product_ids = list(by_product)
done_units = 0
for start in range(0, len(product_ids), 40):
    vals = []
    for pid in product_ids[start:start + 40]:
        for r in by_product[pid]:
            vals.append({'product_id': pid, 'location_id': location_by_bin[r['bin']].id, 'inventory_quantity': r['qty']})
    chunk_units = sum(v['inventory_quantity'] for v in vals)   # before create(): it consumes the dicts
    quants = book.create(vals)
    quants.action_apply_inventory()
    env.cr.commit()
    done_units += chunk_units
    say('    products done: %d / %d (units %d)' % (min(start + 40, len(product_ids)), len(product_ids), done_units))

say('APPLY FINISHED. Run the verification script next.')
