from odoo import fields, models, api

class ProductTemplateExt(models.Model):
    _inherit = "product.template"


    custom_product_type = fields.Selection([('product','Product'),('component','Component')],string="Custom Product Type")


class ProductProductExt(models.Model):
    _inherit = "product.product"


    custom_variant_type = fields.Selection([('product','Product'),('component','Component')],string="Custom Variant Type",compute="compute_custom_variant_type",store=True)

    @api.depends('product_tmpl_id.custom_product_type')
    def compute_custom_variant_type(self):
        for record in self:
            record.custom_variant_type = record.product_tmpl_id.custom_product_type

