from odoo import fields, models

class ProductTemplateExt(models.Model):
    _inherit = "product.template"


    custom_product_type = fields.Selection([('product','Product'),('component','Component')],string="Custom Product Type")


class ProductProductExt(models.Model):
    _inherit = "product.product"


    custom_variant_type = fields.Selection([('product','Product'),('component','Component')],string="Custom Variant Type")
