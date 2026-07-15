from odoo import fields, models, api
from odoo.exceptions import ValidationError, UserError


class SaleOrderBomComponent(models.Model):
    _name = 'sale.order.bom.component'
    _description = 'Sale Order Bom Component'
    _rec_name = 'order_id'

    order_id = fields.Many2one('sale.order', string='Sale Order', ondelete='cascade')
    state = fields.Selection(related='order_id.state')

    component_line_ids = fields.One2many(
        'sale.order.bom.component.line',
        'component_id',
        copy=True
    )
    # computed cost
    total_parent_product_sale_price = fields.Float(compute='_compute_multi_total_from_bom_lines', store=True)
    total_parent_live_unit_cost = fields.Float(compute='_compute_multi_total_from_bom_lines', store=True)

    component_state_id = fields.Many2one('bom.component.state', copy=False)

    @api.depends('component_line_ids.total_sale_price', 'component_line_ids.total_live_cost')
    def _compute_multi_total_from_bom_lines(self):
        for record in self:
            parent_lines = False
            parent_product_total_sale_price = 0.0
            total_margin_live_cost = 0.0
            component_lines = record.component_line_ids
            if not component_lines:
                record.total_parent_product_sale_price = parent_product_total_sale_price
                record.total_parent_live_unit_cost = total_margin_live_cost
            if component_lines:
                parent_lines = component_lines.filtered(lambda c: c.is_parent)
                if not parent_lines:
                    record.total_parent_product_sale_price = parent_product_total_sale_price
                    record.total_parent_live_unit_cost = total_margin_live_cost
                if parent_lines:
                    parent_product_total_sale_price = sum(parent_lines.mapped('total_sale_price'))
                    total_margin_live_cost = sum(parent_lines.mapped('total_live_cost'))
                    record.total_parent_product_sale_price = parent_product_total_sale_price
                    record.total_parent_live_unit_cost = total_margin_live_cost


class SaleOrderBOMComponentLine(models.Model):
    _name = 'sale.order.bom.component.line'
    _description = 'BOM Component Line'

    name = fields.Char(string='Name')
    component_id = fields.Many2one('sale.order.bom.component', string='Components', ondelete='cascade')
    order_line_id = fields.Many2one('sale.order.line', ondelete='cascade')
    # parent_product_id = fields.Many2one('product.template', string='Parent Product')
    # parent_product_reference = fields.Char('Parent Product Reference')
    product_id = fields.Many2one(
        'product.product',
        string='Component',
    )
    # product_reference = fields.Char(string='Product Reference', related='product_id.default_code')
    product_qty = fields.Float(string='Quantity', digits='Product Quantity')
    unit_component_quantity = fields.Float(string='Unit Component Quantity', digits='Product Unit Quantity')
    unit_sale_price = fields.Float(string='Unit Sale Price')
    total_sale_price = fields.Float(string="Total Sale Price", compute='_compute_total_sale_price', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier')
    is_parent = fields.Boolean(string="Is Parent")
    is_auto_generated = fields.Boolean(
        string="Auto-Generated",
        default=False,
        help="Technical field to identify lines created automatically"
    )
    is_other_than_bom = fields.Boolean(default=False, store=True)
    sequence = fields.Integer("Sequence")
    # costs
    live_unit_cost = fields.Float(string='Live Unit Cost')
    total_live_cost = fields.Float(string='Total Live Cost', compute='_compute_total_live_cost', store=True)
    margin_live_cost = fields.Float(string='Margin Live Cost', compute='_compute_total_sale_price', store=True)

    display_type = fields.Selection([
        ('line_section', "Section"),
    ], string="Display Type")

    unit_margin = fields.Float(
        string="Unit Margin($)",
        currency_field='currency_id',
        compute='_compute_unit_margin',
    )

    def get_live_unit_cost(self):
        self.ensure_one()
        return (self.component_state or {}).get('live_unit_cost')

    def _prepare_state_dict(self):
        self.ensure_one()
        live_unit_cost_proportion = self.live_unit_cost / self.product_qty if self.product_qty else 0.0
        return {'live_unit_cost_proportion': live_unit_cost_proportion}

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        State = self.env['bom.component.state']
        state_vals = [
            {
                'bom_component_line_id': line.id,
                'component_state': line._prepare_state_dict(),
            }
            for line in lines if line.product_id and not line.is_parent and not line.display_type
        ]
        if state_vals:
            State.create(state_vals)
        return lines

    @api.depends('margin_live_cost', 'product_qty', 'is_parent')
    def _compute_unit_margin(self):
        for line in self:
            if line.is_parent and line.product_qty:
                line.unit_margin = line.margin_live_cost / line.product_qty
            else:
                line.unit_margin = 0.0

    @api.depends('product_qty', 'unit_sale_price', 'total_live_cost')
    def _compute_total_sale_price(self):
        for rec in self:
            qty = rec.product_qty or 0.0
            total_sale_price = qty * (rec.unit_sale_price or 0.0)
            rec.total_sale_price = total_sale_price
            if rec.is_parent:
                rec.margin_live_cost = total_sale_price - (rec.total_live_cost or 0.0)
            else:
                rec.margin_live_cost = 0.0

    def action_open_add_components_wizard(self):
        """Open wizard to add components for this parent line"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Components',
            'res_model': 'bom.component.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_component_id': self.component_id.id if self.component_id else False,
                'active_id': self.id,
                'active_model': 'sale.order.bom.component.line',
                'parent_line_seq': self.product_id.sequence,
                'parent_line_id': self.id,
                'dialog_size': 'extra-large',
            }
        }

    def action_open_update_parent_line(self):
        pass

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        for parent in self.filtered('is_parent'):
            children = parent.component_id.component_line_ids.filtered(
                lambda l: (
                        l.order_line_id == parent.order_line_id
                        and not l.is_parent
                        and not l.display_type
                )
            )
            for child in children:
                child.originupdate({
                    'product_qty': child.unit_component_quantity * parent.product_qty,
                })


    @api.onchange('unit_component_quantity')
    def _onchange_unit_component_quantity(self):
        for child in self.filtered(lambda l: not l.is_parent):
            parent = child.component_id.component_line_ids.filtered(
                lambda l: (
                        l.is_parent
                        and l.order_line_id == child.order_line_id
                )
            )[:1]

            if parent:
                child.product_qty = parent.product_qty * child.unit_component_quantity


    @api.depends('product_qty','live_unit_cost')
    def _compute_total_live_cost(self):
        for rec in self:
            rec.total_live_cost = rec.live_unit_cost * rec.product_qty



