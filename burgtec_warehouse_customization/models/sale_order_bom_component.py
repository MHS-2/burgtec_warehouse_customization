from odoo import fields, models, api, _
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
    total_parent_product_sale_price = fields.Monetary(currency_field='currency_id',compute='_compute_multi_total_from_bom_lines', store=True)
    total_parent_live_unit_cost = fields.Monetary(currency_field='currency_id',compute='_compute_multi_total_from_bom_lines', store=True)

    component_state_id = fields.Many2one('bom.component.state', copy=False)

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True,
        precompute=True,
        ondelete='restrict'
    )

    @api.depends('order_id','order_id.currency_id')
    def _compute_currency_id(self):
        for rec in self:
            order = rec.order_id
            if not order:
                rec.currency_id = False
            if order:
                rec.currency_id = order.currency_id

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
    _order = 'sequence, id'

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
    product_qty = fields.Float(string='Quantity', digits='Product Quantity',compute="compute_product_qty", inverse="_inverse_product_qty", store=True)
    # product_uom_qty = fields.Float(related="order_line_id.product_uom_qty",store=True)
    unit_component_quantity = fields.Float(string='Unit Component Quantity', digits='Product Unit Quantity',default=1)
    unit_sale_price = fields.Monetary(currency_field='currency_id',string='Unit Sale Price', compute='_compute_unit_sale_price', inverse="_inverse_unit_sale_price", store=True, readonly=False)
    total_sale_price = fields.Monetary(currency_field='currency_id',string="Total Sale Price", compute='_compute_total_sale_price', store=True)
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
    live_unit_cost = fields.Monetary(currency_field='currency_id', string='Live Unit Cost')
    total_live_cost = fields.Monetary(currency_field='currency_id', string='Total Live Cost', compute='_compute_total_live_cost', store=True)
    margin_live_cost = fields.Monetary(currency_field='currency_id', string='Margin Live Cost', compute='_compute_total_sale_price', store=True)

    display_type = fields.Selection([
        ('line_section', "Section"),
    ], string="Display Type")

    unit_margin = fields.Float(
        string="Unit Margin($)",
        currency_field='currency_id',
        compute='_compute_unit_margin',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True,
        precompute=True,
        ondelete='restrict'
    )

    @api.depends('component_id','component_id.currency_id')
    def _compute_currency_id(self):
        for rec in self:
            component = rec.component_id
            if not component:
                rec.currency_id = False
            if component:
                rec.currency_id = component.currency_id

    @api.depends('margin_live_cost', 'product_qty', 'is_parent')
    def _compute_unit_margin(self):
        for line in self:
            if line.is_parent and line.product_qty:
                line.unit_margin = line.margin_live_cost / line.product_qty
            else:
                line.unit_margin = 0.0
    
    @api.depends('order_line_id.price_unit')
    def _compute_unit_sale_price(self):
        for record in self:
            order_line = record.order_line_id
            if not record.is_parent:
                record.unit_sale_price = 0.0
            if record.is_parent:    
                record.unit_sale_price = order_line.price_unit
    
    def _inverse_unit_sale_price(self):
        for rec in self:
            if rec.is_parent:
                rec.order_line_id.price_unit = rec.unit_sale_price

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

    def action_open_sale_order_line(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit Parent Line',
            'res_model': 'sale.order.line',
            'res_id': self.order_line_id.id,
            'view_id': self.env.ref(
                'burgtec_warehouse_customization.burgtec_warehouse_customiation_view_sale_order_line_from_bom_line_form'
            ).id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
            }
        }


    @api.depends('product_qty','live_unit_cost','order_line_id.component_line_ids','order_line_id.component_line_ids.live_unit_cost', 'order_line_id.component_line_ids.product_qty')
    def _compute_total_live_cost(self):
        for rec in self:
            child_components = False
            order_line = rec.order_line_id
            if rec.display_type:
                rec.total_live_cost = 0
            if rec.is_parent:
                child_components =  order_line.component_line_ids.filtered(lambda c: not c.is_parent and not c.display_type)
                if not rec.product_qty > 0:
                    rec.total_live_cost = 0
                if rec.product_qty > 0:
                    for line in child_components:
                        line.total_live_cost = line.live_unit_cost * line.product_qty
                    rec.total_live_cost = sum(child_components.mapped('total_live_cost'))
                    rec.live_unit_cost = rec.total_live_cost / rec.product_qty if rec.product_qty > 0 else 0

            if not rec.is_parent:
                rec.total_live_cost = rec.live_unit_cost * rec.product_qty

    def unlink(self):
        for rec in self:
            if not rec.env.context.get('force_delete') and rec.is_parent:
                raise UserError(_('You are not allowed to delete parent line. If you want to go delete its order line from sales order instead!'))
            bom_component = rec.component_id
            order_id = bom_component.order_id
        res = super().unlink()
        order_lines = order_id.order_line.sorted(lambda o:o.sequence)
        order_id.set_sequences(order_lines,10) # 10 sequence is used by default.
        return res
        
    @api.depends('order_line_id.product_uom_qty','unit_component_quantity')
    def compute_product_qty(self):
        for record in self:
            order_line = record.order_line_id
            if not record.is_parent:
                if order_line.product_uom_qty > 0:
                    record.product_qty = record.unit_component_quantity * order_line.product_uom_qty
                else:
                    record.product_qty = record.unit_component_quantity
            if record.is_parent:    
                record.product_qty = order_line.product_uom_qty
    
    def _inverse_product_qty(self):
        for rec in self:
            if rec.is_parent:
                rec.order_line_id.product_uom_qty = rec.product_qty

    
    @api.constrains('unit_component_quantity')
    def check_unit_component_quantity(self):
        for rec in self:
            if rec.unit_component_quantity <= 0:
                raise UserError(_('You can not set Unit Component Quantity Zero or Less than Zero !!!'))


