{
    "name": "Quotation Creation From Excel Import",
    "version": "19.0.2.0.0",
    "summary": """Create Quotations from Importing Excel File of Purchase Order""",
    "author": "Byte Legions",
    "license": "LGPL-3",
    'category': 'Customizations',
    "depends": ["burgtec_warehouse_customization"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/quotation_creation_from_excel_import_views.xml",
        "views/sale_order_views.xml",
    ],
    'installable': True,
    'application': True,
}
