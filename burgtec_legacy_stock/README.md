# Burgtec Legacy Stock

Additive extension of `burgtec_warehouse_customization`. **It changes none of that module's files**,
and uninstalling it brings back the previous behaviour exactly.

## What it adds
| Area | What changes |
|---|---|
| `product.inventory.legacy.data` | Adds supplier, Odoo location, import batch, import row and `item_extras_cost` (exchange + duty + freight per unit). A batch row can be loaded only once (`import_batch` + `sheet_row` unique). |
| Stock Inventory With Landed Costs Report | Legacy batches appear next to the vendor bill rows. New **Source** column and a search view (Purchase / Legacy, group by source or product). Bill rows come first, as before. |
| Product landed cost figures | Average / min / max / latest landed cost take the legacy batches into account. Each batch counts like one landed cost record (its extras per unit). "Latest" stays the latest real landed cost when there is one; otherwise it is the quantity-weighted extras of the batches. |

## How it is built (and why it is safe)
* **Report:** the original keeps creating its database view of bill rows. This module sets
  `_table_query` to *that view plus the legacy rows*. No SQL of the original is copied, no view is renamed
  or dropped, so updating either module cannot break the other.
* **`partner_id`, `currency_id`, `product_cost`** were related fields through the purchase order line (empty for anything
  that is not a bill). They keep their label, type and searchability and now also answer for a legacy batch.
* **Computed columns** (landed costs, total, receipts, location): the original method runs for bill rows,
  legacy rows are answered from the batch.
* **Product figures:** the original calculation runs first (`super()`), then the legacy batches are blended in.
* **Report ids:** legacy rows use `id = 1 000 000 000 + legacy id`, so they never collide with bill line ids.

## Loading the legacy stock
The module only describes batches. Putting the stock into Odoo is a separate, one-off job that uses
Odoo's own inventory adjustments: `tools/legacy_stock_load/legacy_stock_load.py` (plan with `mode: check`,
load with `mode: apply`) and `legacy_stock_verify.py` (21 checks).

## Tests
`odoo -d <db> -i burgtec_legacy_stock --test-enable --test-tags /burgtec_legacy_stock --stop-after-init`
