from odoo import fields, models, api, Command, _


class SaleOrderExt(models.Model):
    _inherit = 'sale.order'

    bom_component_id = fields.Many2one(
        'sale.order.bom.component',
        string='BOM Components'
    )

    next_sequence = fields.Integer(string='Next Sequence', compute='_compute_next_sequence', store=True)

    @api.depends('bom_component_id.component_line_ids', 'order_line')
    def _compute_next_sequence(self):
        for rec in self:
            bom_component_id = rec.bom_component_id
            component_line_ids = bom_component_id.component_line_ids.sorted(lambda l: l.sequence)
            order_line = rec.order_line.sorted(lambda l: l.sequence)
            if not component_line_ids and not order_line:
                rec.next_sequence = 10
            if not component_line_ids and order_line:
                rec.next_sequence = order_line[-1].sequence + 2
            if component_line_ids:
                rec.next_sequence = component_line_ids[-1].sequence + 2

    @api.model_create_multi
    def create(self, vals_list):
        res = super(SaleOrderExt, self).create(vals_list)
        for order in res:
            bom_res = self.env['sale.order.bom.component'].sudo().create({
                'order_id': order.id
            })
            res.bom_component_id = bom_res.id
        return res

    def action_show_component(self):
        self.ensure_one()
        return {
            'name': _('BOM Components'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.bom.component',
            'res_id': self.bom_component_id.id,
            'view_mode': 'form',
            'view_id': self.env.ref('burgtec_warehouse_customization.view_sale_order_bom_components_form').id,
            'target': 'current',

        }


class SaleOrderLinesExt(models.Model):
    _inherit = 'sale.order.line'

    kit_bom_id = fields.Many2one(
        'mrp.bom', string='Kit BOM', copy=True,
        domain="[('product_id','=', product_id)]")

    component_line_ids = fields.One2many(
        'sale.order.bom.component.line',
        'order_line_id',
        compute='_compute_component_line_ids', store=True,
    )

    @api.depends('kit_bom_id')
    def _compute_component_line_ids(self):
        order_id = False
        bom_component = False
        kit_bom_id = False
        bom_line_ids = False
        multiply_qty = 0.0
        child_product_qty = 0.0
        order_line_product_qty = 0.0
        bom_line_product_qty = 0.0
        bom_line_product = False
        seq = False
        list_vals = []
        vals = {}
        bom_line_sequence = 0
        for order_line in self:
            order_line_bom_component_lines = order_line.component_line_ids
            if order_line_bom_component_lines:
                order_line_bom_component_lines = [(5, 0, 0)]
            order_id = order_line.order_id
            bom_component = order_id.bom_component_id
            # Child sequence 1 ahead then parent's
            seq = order_line.sequence
            bom_line_sequence = seq - 1
            kit_bom_id = order_line.kit_bom_id
            order_line_product_qty = order_line.product_uom_qty
            # display_line
            vals = {
                'component_id': bom_component.id,
                'display_type': 'line_section',
                'name': order_line.product_id.display_name,
                'sequence': bom_line_sequence,
                'order_line_id': order_line.id
            }
            list_vals.append((0, 0, vals))
            vals = {}
            # Parent Line
            bom_line_sequence += 1
            vals = {
                'component_id': bom_component.id,
                'is_parent': True,
                'order_line_id': order_line.id,
                'product_id': order_line.product_id.id,
                'product_qty': order_line.product_uom_qty,
                'unit_component_quantity': 1.0,
                'unit_sale_price': order_line.price_unit,
                'live_unit_cost': 0.0,
                'is_auto_generated': True,
                'supplier_id': self.get_product_suppiler(order_line.product_id),
                'sequence': bom_line_sequence,
            }
            list_vals.append((0, 0, vals))
            vals = {}
            if kit_bom_id:
                bom_line_ids = kit_bom_id.bom_line_ids
                for bom_line in bom_line_ids:
                    # Child sequence 1 ahead then parent's
                    bom_line_sequence += 1
                    bom_line_product = bom_line.product_id
                    bom_line_product_qty = bom_line.product_qty
                    if order_line_product_qty <= 0:
                        multiply_qty = bom_line_product_qty
                        if bom_line_product_qty > 0:
                            child_product_qty = bom_line_product_qty
                        else:
                            child_product_qty = 1.0
                    if order_line_product_qty > 0:
                        child_product_qty = order_line_product_qty * bom_line_product_qty
                        multiply_qty = order_line_product_qty * bom_line_product_qty

                        # multiply_qty = bom_line_product_qty * order_line.product_uom_qty if order_line.product_uom_qty > 0 else bom_line_product_qty
                    # new_proportion = bom_line_product_qty
                    vals = {
                        'component_id': bom_component.id,
                        'is_parent': False,
                        'display_type': order_line.display_type,
                        'product_id': bom_line_product.id,
                        'product_qty': child_product_qty,
                        'unit_component_quantity': bom_line_product_qty if bom_line_product_qty > 0 else 1.0,
                        'order_line_id': order_line.id,
                        # 'origin_order_line': sol.old_order_line if sol.old_order_line else False,
                        'is_auto_generated': True,
                        'supplier_id': self.get_product_suppiler(bom_line_product),
                        'live_unit_cost': bom_line_product.standard_price,
                        'total_live_cost': multiply_qty * bom_line_product.standard_price,
                        'sequence': bom_line_sequence
                    }
                    list_vals.append((0, 0, vals))
                    vals = {}
                # If order line after this one.
                other_order_lines = order_id.order_line.sorted(lambda o: o.sequence).filtered(
                    lambda l: l.sequence > order_line.sequence and l.id != order_line.id)
                if other_order_lines:
                    order_line.set_sequences(other_order_lines, bom_line_sequence)
                order_line.component_line_ids = list_vals



    def get_product_suppiler(self, product_id):
        if product_id.seller_ids:
            return product_id.seller_ids[0].partner_id.id
        return False

    def _domain_product_id(self):
        return [('sale_ok', '=', True), ('custom_product_type', '=', 'product')]

    def set_sequences(self, other_order_lines, seq):
        new_sequence = seq + 1
        child_boms = False
        for order_line in other_order_lines:
            order_line.sequence = new_sequence
            child_boms = order_line.component_line_ids
            if child_boms:
                for child in child_boms:
                    new_sequence += 1
                    child.sequence = new_sequence
                new_sequence += 1

    def create(self, vals_list):
        res = super(SaleOrderLinesExt, self).create(vals_list)
        for line in res:
            line.sequence = line.order_id.next_sequence
            line.order_id._compute_next_sequence()
        return res
