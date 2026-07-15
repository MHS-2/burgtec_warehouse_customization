{
    'name': "burgtec_warehouse_customization",
    'summary': "",
    'description': """
    """,
    'author': "",
    'website': "",
    'category': '',
    'version': '0.1',
    'depends': ['base','sale_management','mrp','sale','purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_ext.xml',
        'views/product_view_ext.xml',
        'views/sale_order_line_ext.xml',
        'views/sale_order_bom_component_view.xml',
        'views/purchase_order_view_ext.xml',
        'wizard/bom_component_wizard.xml',

    ],
    'assets': {
        'web.assets_backend': [
            'burgtec_warehouse_customization/static/src/css/style.css',
            'burgtec_warehouse_customization/static/src/js/disable_list_view_sort.js',
        ]
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

