from markupsafe import Markup

from odoo import fields, models, api, Command, _
from odoo.exceptions import UserError


class SaleOrderExt(models.Model):
    _inherit = 'sale.order'

    bom_component_id = fields.Many2one(
        'sale.order.bom.component',
        string='BOM Components'
    )

    next_sequence = fields.Integer(string='Next Sequence',default="10")

    total_live_unit_cost = fields.Monetary(currency_field='currency_id',compute='_compute_total_live_unit_cost', store=True)
    gp_cost = fields.Monetary(currency_field='currency_id',compute='_compute_multi_costs', store=True)
    percentage_margin_live_cost = fields.Float(compute='_compute_multi_costs', store=True)
    percentage_markup_live_cost = fields.Float(compute='_compute_multi_costs', store=True)
    floating_table_html = fields.Html(compute="_compute_floating_table_html")


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
    
    def set_sequences(self, order_lines, seq):
        bom_seq = seq - 1 # 9 due to display line.
        # new_sequence = seq + 1
        child_boms = False
        for order_line in order_lines:
            child_boms = order_line.component_line_ids
            if child_boms:
                for child in child_boms:
                    if child.is_parent:
                        order_line.sequence = bom_seq
                    child.sequence = bom_seq
                    bom_seq += 1
        self.next_sequence = bom_seq+1 # Gap of 2 always because of display line before parent line.
    

    @api.depends('order_line','order_line.total_live_unit_cost')
    def _compute_total_live_unit_cost(self):
        for record in self:
            order_lines = record.order_line
            if not order_lines:
                record.total_live_unit_cost = 0.0
            if order_lines:
                record.total_live_unit_cost = sum(order_lines.mapped('total_live_unit_cost'))
    
    @api.depends('total_live_unit_cost','amount_untaxed')
    def _compute_multi_costs(self):
        for record in self:
            total_live_cost = record.total_live_unit_cost
            amount_untaxed = record.amount_untaxed
            amount_cost_diff = amount_untaxed - total_live_cost
            # cost
            record.gp_cost =  amount_cost_diff

            # Margin %
            record.percentage_margin_live_cost = (amount_cost_diff) / amount_untaxed if amount_untaxed else 0.0

            # Markup %
            record.percentage_markup_live_cost = (
                    (amount_cost_diff) / total_live_cost
                    if total_live_cost else 0.0
                )
    
    def _compute_floating_table_html(self):
        for record in self:
            table_code = Markup("""
            <div class="o_margin_header_panel border">
                <table class="o_margin_header_table">
                    <tr>
                        <td class="o_mh_label">Total$</td>
                        <td class="o_mh_value" data-field="total_untaxed_amount">{untaxed_amount}</td>
                        <td class="o_mh_sep">┃</td>
                        <td class="o_mh_label">GP$</td>
                        <td class="o_mh_value" data-field="gp">{gp_cost}</td>
                        <td class="o_mh_sep">┃</td>
                        <td class="o_mh_label">Margin</td>
                        <td class="o_mh_value" data-field="margin">{margin}%</td>
                        <td class="o_mh_sep">┃</td>
                        <td class="o_mh_label">Markup</td>
                        <td class="o_mh_value" data-field="markup">{markup}%</td>
                    
                    </tr>
                </table>
            </div>
            """).format(untaxed_amount=record.amount_untaxed,gp_cost=record.gp_cost,margin=round(record.percentage_margin_live_cost*100,2),markup=round(record.percentage_markup_live_cost*100,2))

            record.floating_table_html = table_code





class SaleOrderLinesExt(models.Model):
    _inherit = 'sale.order.line'

    kit_bom_id = fields.Many2one(
        'mrp.bom', string='Kit BOM', copy=True,
        domain="[('product_id','=', product_id)]")

    component_line_ids = fields.One2many(
        'sale.order.bom.component.line',
        'order_line_id',
    )

    total_live_unit_cost = fields.Monetary(currency_field='currency_id',compute='_compute_multi_total_from_bom_lines', store=True)

    @api.depends('component_line_ids','component_line_ids.total_live_cost', 'component_line_ids.live_unit_cost',)
    def _compute_multi_total_from_bom_lines(self):
        for rec in self:
            parent_line = rec.component_line_ids.filtered(lambda l:l.is_parent)
            if not parent_line:
                rec.total_live_unit_cost = 0.0
            if parent_line:
                rec.total_live_unit_cost = parent_line.total_live_cost



    @api.model_create_multi
    def create(self, vals_list):
        res = super(SaleOrderLinesExt, self).create(vals_list)
        for order_line in res:
            order_line.set_component_line_ids()
        return res
    
    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if vals.get('kit_bom_id'):
                rec.update_component_line_ids()
        return res
            
    def set_component_line_ids(self):
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
                order_line.component_line_ids = [(5, 0, 0)]
            order_id = order_line.order_id
            bom_component = order_id.bom_component_id
            # Child sequence 1 ahead then parent's
            # seq = order_line.sequence
            seq = order_id.next_sequence
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
            order_line.sequence = bom_line_sequence
            vals = {
                'component_id': bom_component.id,
                'is_parent': True,
                'order_line_id': order_line.id,
                'product_id': order_line.product_id.id,
                'product_qty': order_line.product_uom_qty,
                'unit_component_quantity': 1.0,
                'unit_sale_price': order_line.price_unit,
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
                if not other_order_lines:
                    order_id.next_sequence = bom_line_sequence+2
                if other_order_lines:
                    order_line.set_sequences(other_order_lines, bom_line_sequence)
                order_line.component_line_ids = list_vals
                list_vals = []
    
    def update_component_line_ids(self):
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
                order_line.component_line_ids.with_context(force_delete=True).unlink()
            order_id = order_line.order_id
            bom_component = order_id.bom_component_id
            # Child sequence 1 ahead then parent's
            # seq = order_line.sequence
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
            # order_line.sequence = bom_line_sequence
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
                #Updating so will set sequence of all lines.
                order_lines = order_id.order_line.sorted(lambda o: o.sequence)
                order_line.component_line_ids = list_vals
                order_id.set_sequences(order_lines,10)
                list_vals = []



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
        self.order_id.next_sequence = new_sequence+1

    # def create(self, vals_list):
    #     res = super(SaleOrderLinesExt, self).create(vals_list)
    #     for line in res:
    #         line.sequence = line.order_id.next_sequence
    #         # line.order_id._compute_next_sequence()
    #     return res

    def unlink(self):
        for rec in self:
            order_id = rec.order_id
        res = super().unlink()
        order_lines = order_id.order_line.sorted(lambda o:o.sequence)
        if not order_lines:
            order_id.next_sequence = 10
            return res
        order_id.set_sequences(order_lines,10) # 10 sequence is used by default.
        return res
    

    # When changing already added product on a line it must remove the kit bom
    @api.onchange('product_id')
    def onchange_product_id(self):
        if self._origin.kit_bom_id and self._origin.kit_bom_id.product_id.id != self.product_id.id:
            self.kit_bom_id = False
    


