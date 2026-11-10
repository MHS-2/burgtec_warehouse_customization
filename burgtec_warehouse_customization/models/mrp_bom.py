# -*- coding: utf-8 -*-
import logging
from email.policy import default

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    product_tmpl_id = fields.Many2one(
            'product.template', 'Product',
            check_company=True, index=True,
            domain="[('type', '=', 'consu'), ('custom_product_type','=','product')]", required=True)
    
    product_id = fields.Many2one(
            'product.product', 'Product Variant',
            check_company=True, index=True,
            domain="['&', ('product_tmpl_id', '=', product_tmpl_id), ('type', '=', 'consu'), ('custom_variant_type','=','product')]",
            help="If a product variant is defined the BOM is available only for this product.")

    custom_component_ids = fields.One2many('sale.order.bom.component.line','mrp_bom_id')

    def custom_explode(self, product, quantity, picking_type=False, never_attribute_values=False, sale_line_id = False):
            """
                Explodes the BoM and creates two lists with all the information you need: bom_done and line_done
                Quantity describes the number of times you need the BoM: so the quantity divided by the number created by the BoM
                and converted into its UoM
            """
            product_ids = set()
            product_boms = {}
            def update_product_boms():
                products = self.env['product.product'].browse(product_ids)
                product_boms.update(self._bom_find(products, picking_type=picking_type or self.picking_type_id,
                    company_id=self.company_id.id, bom_type='phantom'))
                # Set missing keys to default value
                for product in products:
                    product_boms.setdefault(product, self.env['mrp.bom'])
    
            boms_done = [(self, {'qty': quantity, 'product': product, 'original_qty': quantity, 'parent_line': False})]
            lines_done = []
    
            bom_lines = []
            custom_components = []
            if sale_line_id:
                custom_components = self.custom_component_ids.filtered(lambda l:l.order_line_id.id == sale_line_id)
                # When New Product is added , it must create lines from og bom lines instead.
                if not custom_components:
                    custom_components = self.bom_line_ids
            for bom_line in custom_components:
                product_id = bom_line.product_id
                bom_lines.append((bom_line, product, quantity, False))
                product_ids.add(product_id.id)
            update_product_boms()
            product_ids.clear()
            while bom_lines:
                current_line, current_product, current_qty, parent_line = bom_lines[0]
                bom_lines = bom_lines[1:]
    
                # if current_line._skip_bom_line(current_product, never_attribute_values):
                #     continue
    
                # line_quantity = current_qty * current_line.product_qty 
                # # BOm Component Qty so it is already being multiplied in our custom logic no need to do it.
                line_quantity = current_line.product_qty

                if current_line.product_id not in product_boms:
                    update_product_boms()
                    product_ids.clear()
                bom = product_boms.get(current_line.product_id)
                if bom:
                    converted_line_quantity = current_line.product_uom_id._compute_quantity(
                        line_quantity / bom.product_qty, bom.product_uom_id, round=False
                    )
                    bom_lines = [(line, current_line.product_id, converted_line_quantity, current_line) for line in bom.bom_line_ids] + bom_lines
                    for bom_line in bom.bom_line_ids:
                        if bom_line.product_id not in product_boms:
                            product_ids.add(bom_line.product_id.id)
                    boms_done.append((bom, {'qty': converted_line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': current_line}))
                else:
                    # We round up here because the user expects that if he has to consume a little more, the whole UOM unit
                    # should be consumed.
                    line_quantity = current_line.product_uom_id.round(line_quantity, rounding_method='UP')
                    lines_done.append((current_line, {'qty': line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': parent_line}))
    
            return boms_done, lines_done


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    component_notes = fields.Char(string='Component Notes')
    modification_required = fields.Boolean(string='Is Modification Required',default=False)

