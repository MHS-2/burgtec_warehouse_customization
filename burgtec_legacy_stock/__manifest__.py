# -*- coding: utf-8 -*-
{
    'name': 'Burgtec Legacy Stock',
    'summary': 'Legacy (IT Hub) stock batches in the Stock Inventory With Landed Costs report '
               'and in the product landed cost figures',
    'description': """
Additive extension of burgtec_warehouse_customization. It changes none of that module's files.

* Legacy stock batches (product.inventory.legacy.data) get the fields needed to describe a batch:
  supplier, Odoo location, import batch and the landed extras per unit.
* The "Stock Inventory With Landed Costs Report" shows legacy batches next to the vendor bill
  rows (new Source column). Bill rows are unchanged.
* The product's average / minimum / maximum / latest landed cost take the legacy batches into
  account. Legacy batches count as older than any landed cost recorded in Odoo.

Uninstalling the module restores the previous behaviour exactly.
    """,
    'author': 'Burgtec',
    'category': 'Customizations',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['burgtec_warehouse_customization'],
    'data': [
        'views/product_inventory_legacy_data_views.xml',
        'views/lc_stock_inventory_report_views.xml',
    ],
    'installable': True,
    'application': False,
}
