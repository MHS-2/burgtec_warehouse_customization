from markupsafe import Markup

from odoo import fields, models, api, Command, _
from odoo.exceptions import UserError
from odoo.tools import float_compare

SALE_ORDER_STATE = [
    ('draft', "Quotation"),
    ('sent', "Quotation Sent"),
    ('sale', "Sales Order"),
    ('cancel', "Cancelled"),
]



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
    customer_po_reference = fields.Char()
    is_pre_validate = fields.Boolean(default=False,copy=False)
        
    validate_state = fields.Selection([
            ('pre_validate','Pre-Validated'),
            ('un_validate','Un-Validated')
        ],default=False, tracking=True,copy=False)

    planned_pick_date = fields.Date()
    order_entry_complete = fields.Date()
    order_entry_status = fields.Text()
    pre_validation_comments = fields.Text()
    make_readonly_user = fields.Boolean(compute="compute_make_readonly_usr")

    custom_state = fields.Selection(
        selection=SALE_ORDER_STATE,
        string="Status",
        readonly=True, copy=False, index=True,
        tracking=3,
        default='draft')

    def compute_make_readonly_usr(self):
        for record in self:
            if record.validate_state == 'pre_validate' and not record.env.user.has_group('sales_team.group_sale_manager'):
                record.make_readonly_user = True
            else:
                record.make_readonly_user = False
    
    def _cancel_pickings_keep_state(self):
        """Same as sale_stock._action_cancel, minus invoice cancel and state write."""
        documents = None
        for sale_order in self:
            if sale_order.state == 'sale' and sale_order.order_line:
                quantities = {
                    line: (line.product_uom_qty, 0) for line in sale_order.order_line
                }
                documents = self.env['stock.picking'].with_context(
                    include_draft_documents=True
                )._log_activity_get_documents(quantities, 'move_ids', 'UP')

        pickings = self.picking_ids.filtered(lambda p: p.state != 'done')
        pickings.write({
            'is_unvalidated':True
        })
        pickings.action_cancel()

        if documents:
            filtered_documents = {}
            for (parent, responsible), rendering_context in documents.items():
                if parent._name == 'stock.picking' and parent.state == 'cancel':
                    continue
                filtered_documents[(parent, responsible)] = rendering_context
            self._log_decrease_ordered_quantity(filtered_documents, cancel=True)

    
    def set_pre_validate(self):
        for record in self:
            already_created_pickings = record.picking_ids.filtered(lambda r: r.state != 'cancel')
            if not already_created_pickings:
                record.action_confirm()
            record.write({
                'validate_state':'pre_validate',
                'is_pre_validate':True,
            })
    
    def set_un_validate(self):
        for record in self:
            self._cancel_pickings_keep_state()
            record.write({
                'validate_state':'un_validate',
                'is_pre_validate':False,
                'state':'draft',
            })


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
    
    def write(self, vals):
        list_data = []
        set_seq = False
        order_lines = False
        # if self.is_pre_validate and not self.env.user.has_group('sales_team.group_sale_manager'):
        #     raise UserError(_("You cannot edit Pre Validated Quotation. Contact Sales Administrator."))
        res = super().write(vals)
        if vals.get('order_line'):
            list_data = vals.get('order_line')
            for data in list_data:
                if data[0] == 1 and 'sequence' in data[2]:
                    set_seq = True
                    break
            if set_seq:
                order_lines = self.order_line.sorted(lambda o:o.sequence)
                self.set_sequences(order_lines,10)
        return res
    
    def _action_cancel(self):
        self.write({
            'custom_state': 'cancel',
            'state': 'cancel',
            'is_pre_validate': False,
            'validate_state': False,
        })
        return super()._action_cancel()
    
    def action_draft(self):
        for order in self:
            order.write({
                'custom_state': 'draft'
            })
        return super().action_draft()
    
    def custom_confirm_order(self):
        self.write({'custom_state': 'sale'})
    
    @api.depends('picking_ids')
    def _compute_picking_ids(self):
        for order in self:
            order.delivery_count = len(order.picking_ids.filtered(lambda p: not p.is_unvalidated))
    
    def action_view_delivery(self):
        return self._get_action_view_picking(self.picking_ids.filtered(lambda p: not p.is_unvalidated))
    
    def _get_action_view_picking(self, pickings):
        '''
        This function returns an action that display existing delivery orders
        of given sales order ids. It can either be a in a list or in a form
        view, if there is only one delivery order to show.
        '''
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")

        pickings = pickings.filtered(lambda p: not p.is_unvalidated)
        if len(pickings) > 1:
            action['domain'] = [('id', 'in', pickings.ids)]
        elif pickings:
            form_view = [(self.env.ref('stock.view_picking_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = pickings.id
        # Prepare the context.
        picking_id = pickings.filtered(lambda l: l.picking_type_id.code == 'outgoing')
        if picking_id:
            picking_id = picking_id[0]
        else:
            picking_id = pickings[0]
        action['context'] = dict(
            default_partner_id=self.partner_id.id,
            default_picking_type_id=picking_id.picking_type_id.id,
        )
        return action


class SaleOrderLinesExt(models.Model):
    _inherit = 'sale.order.line'

    kit_bom_id = fields.Many2one(
        'mrp.bom', string='Kit BOM', copy=True,
        domain="[('product_id','=', product_id)]")

    component_line_ids = fields.One2many(
        'sale.order.bom.component.line',
        'order_line_id',
    )

    processing_comments = fields.Text()

    total_live_unit_cost = fields.Monetary(currency_field='currency_id',compute='_compute_multi_total_from_bom_lines', store=True)

    line_group_name = fields.Char()

    line_section_name = fields.Char()

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
        if not self.env.context.get('creation_by_duplication'):
            for order_line in res:
                order_line.set_component_line_ids()
        return res
    
    def write(self, vals):
        if self.order_id.is_pre_validate and not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("You cannot edit Order Lines of Pre Validated Quotation. Contact Sales Administrator."))
        res = super().write(vals)
        if not self.env.context.get('creation_by_duplication'):
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
                        'mrp_bom_id': bom_line.bom_id.id,
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
                        'sequence': bom_line_sequence,
                        'component_notes': bom_line.component_notes,
                        'modification_required': bom_line.modification_required,
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
                        'mrp_bom_id': bom_line.bom_id.id,
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
                        'sequence': bom_line_sequence,
                        'component_notes': bom_line.component_notes,
                        'modification_required': bom_line.modification_required,
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
    

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        """
        Launch procurement run method with required/custom fields generated by a
        sale order line. procurement will launch '_run_pull', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        if self.env.context.get("skip_procurement"):
            return True
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        procurements = []
        for line in self:
            line = line.with_company(line.company_id)
            if line.state != 'sale' or line.order_id.locked or line.product_id.type != 'consu':
                continue
            qty = line._get_qty_procurement(previous_product_uom_qty)
            if float_compare(qty, line.product_uom_qty, precision_digits=precision) == 0:
                continue

            references = line.order_id.stock_reference_ids
            if not references:
                self.env['stock.reference'].create(line._prepare_reference_vals())

            values = line._prepare_procurement_values()
            values.update({'kit_bom_id':line.kit_bom_id.id}) # For our kit selected on order line.
            product_qty = line.product_uom_qty - qty

            line_uom = line.product_uom_id
            quant_uom = line.product_id.uom_id
            product_qty, procurement_uom = line_uom._adjust_uom_quantities(product_qty, quant_uom)
            procurements += line._create_procurements(product_qty, procurement_uom, values)
        if procurements:
            self.env['stock.rule'].custom_run(procurements)

        # This next block is currently needed only because the scheduler trigger is done by picking confirmation rather than stock.move confirmation
        orders = self.mapped('order_id')
        for order in orders:
            pickings_to_confirm = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
            if pickings_to_confirm:
                # Trigger the Scheduler for Pickings
                pickings_to_confirm.action_confirm()
        return True

    
    def write(self, vals):
        for record in self:
            if record.order_id.is_pre_validate and not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_("You cannot edit Pre Validated Quotation Lines. Contact Sales Administrator."))
        res = super().write(vals)
        return res




