{
    'name': 'Burgtec Sync',
    'summary': "This module is used to send a webhook call to the Burgtec Odoo Controller upon the new variant creation and updation.",
    'author': "Byte Legions",
    'category': 'Customizations',
    'version': '19.0.1.0.0',
    'depends': ['product'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/product_view_ext.xml',
             ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
