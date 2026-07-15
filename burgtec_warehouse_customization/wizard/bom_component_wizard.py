from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.fields import Many2one


class BOMComponentWizard(models.TransientModel):
    _name = 'bom.component.wizard'
    _description = 'BOM Component Wizard'

    # Only relation to sale.order.bom.component
    component_id = fields.Many2one('sale.order.bom.component', string='Component', readonly=True)
    parent_line_sequence = fields.Integer()
    parent_product_id = fields.Many2one('product.template')
    parent_line_id = Many2one('sale.order.bom.component.line', readonly=True)

    # Dynamic fields for adding components
    component_line_ids = fields.One2many(
        'bom.component.wizard.line',
        'wizard_id',
        string='Components to Add'
    )

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'sale.order.bom.component.line':
            active_id = self.env.context.get('active_id')
            if active_id:
                parent_line = self.env['sale.order.bom.component.line'].browse(active_id)
                res.update({
                    'component_id': parent_line.component_id.id if parent_line.component_id else False,
                    'parent_product_id': parent_line.product_id.product_tmpl_id.id if parent_line.product_id else False,
                    'parent_line_sequence': parent_line.sequence,
                    'parent_line_id': parent_line.id
                })
                component_lines = []
                component_lines.append((0, 0, {
                    'display_type': 'line_section',
                    'name': parent_line.product_id.name,
                    'section_name': parent_line.product_id.name,
                }))
                res['component_line_ids'] = component_lines
        return res

    def action_add_components(self):
        """Add selected components to the BOM"""
        if not self.component_line_ids:
            raise ValidationError("Please add at least one component.")

        # Filter out section lines and get only actual component lines
        component_lines_to_add = self.component_line_ids.filtered(
            lambda line: line.display_type != 'line_section' and line.product_id and line.product_qty > 0
        )

        if not component_lines_to_add:
            raise ValidationError("Please add at least one valid component.")

        parent_bom_line_id = self.parent_line_id
        child_lines = self.component_id.component_line_ids.filtered(
            lambda l: not l.is_parent
                      and l.order_line_id == parent_bom_line_id.order_line_id)
        child_product_ids = child_lines.mapped('product_id')

        already_exists = component_lines_to_add.filtered(
            lambda line: line.product_id in child_product_ids
        )
        if already_exists:
            product_names = '\n- '.join(already_exists.mapped('product_id.display_name'))
            raise ValidationError(
                f"The following product(s) are already added as components:\n- {product_names}"
            )

        # Count how many lines we're adding
        lines_to_add_count = len(component_lines_to_add)

        # Shift existing lines down to make room for new lines
        # Find all lines that come after the parent line
        existing_lines = self.env['sale.order.bom.component.line'].search([
            ('component_id', '=', self.component_id.id),
            ('sequence', '>', self.parent_line_sequence)
        ])

        # Update sequences of existing lines (shift them down)
        for line in existing_lines:
            line.sequence += lines_to_add_count

        # Create new component lines with sequential numbering
        sequence_counter = self.parent_line_sequence + 1

        for line in component_lines_to_add:
            self.env['sale.order.bom.component.line'].create({
                'component_id': self.component_id.id,
                # 'parent_product_id': self.parent_product_id.id if self.parent_product_id else False,
                'order_line_id': self.parent_line_id.order_line_id.id if self.parent_line_id.order_line_id else False,
                'product_id': line.product_id.id,
                'product_qty': line.product_qty * self.parent_line_id.product_qty,
                # Fixed: Use list_price instead of price_unit
                # 'unit_sale_price' : line.product_id.list_price,
                # 'total_sale_price': (line.product_qty * self.parent_line_id.product_qty) * line.product_id.list_price,
                # 'system_cost_per_unit': (line.product_qty * self.parent_line_id.product_qty) * (
                #         line.product_id.standard_price or 0.0),
                'live_unit_cost': line.product_id.standard_price or 0.0,
                'total_live_cost': (line.product_qty * self.parent_line_id.product_qty) * (
                        line.product_id.standard_price or 0.0),
                'is_parent': False,
                'is_other_than_bom': True,
                'sequence': sequence_counter,
                'supplier_id': self.get_product_suppiler(line.product_id),

            })
            sequence_counter += 1
        # self.component_id.onchange_component_line_ids()

        return {'type': 'ir.actions.act_window_close'}

    def get_product_suppiler(self, product_id):
        if product_id.seller_ids:
            return product_id.seller_ids[0].partner_id.id
        return False


class BOMComponentWizardLine(models.TransientModel):
    _name = 'bom.component.wizard.line'
    _description = 'BOM Component Wizard Line'

    wizard_id = fields.Many2one('bom.component.wizard', string='Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product',
        string='Component',
        domain="[('product_tmpl_id.custom_product_type', '=', 'components')]"
    )

    # Display type and sequence (following the reference pattern)
    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note'),
    ], string='Display Type', default=False)

    name = fields.Char(string='Description')  # Used for section headers
    sequence = fields.Integer(string='Sequence', default=10)

    # Parent/child relationship
    is_parent = fields.Boolean(string='Is Parent', default=False)

    # All fields at line level
    section_name = fields.Char('Section Name')  # Keep this for compatibility
    parent_product_id = fields.Many2one('product.template', string='Parent Product')
    order_line_id = fields.Many2one('sale.order.line', string='Order Line')
    parent_number = fields.Integer('Parent Serial Number')

    # Product details
    product_qty = fields.Float(string='Quantity', digits='Product Quantity', default=1.0)
    unit_sale_price = fields.Float(string='Unit Sale Price', default=0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update unit price when product changes"""
        if self.product_id:
            self.unit_sale_price = self.product_id.standard_price or 0.0
