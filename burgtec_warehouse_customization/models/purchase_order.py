# -*- coding: utf-8 -*-
from markupsafe import Markup, escape
from odoo.tools import OrderedSet
import logging
from odoo import models, fields, api, _, SUPERUSER_ID, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import groupby

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    supplier_code = fields.Char(related="partner_id.supplier_code", store=True)

    total_order_cbm = fields.Float(compute="compute_total_order_cbm", digits=(16,6), store=True)

    total_order_weight = fields.Float(compute="compute_total_order_weight", digits=(16,6), store=True)


    empty_cbm_warning = fields.Char(compute="compute_empty_cbm_warning")

    is_pre_validate = fields.Boolean(default=False,copy=False)

    validate_state = fields.Selection([
        ('pre_validate','Pre-Validated'),
        ('un_validate','Un-Validated')
    ],default=False, tracking=True,copy=False)

    required_ready_date = fields.Datetime(copy=False)

    make_readonly_user = fields.Boolean(compute="compute_make_readonly_usr")

    custom_state = fields.Selection([
            ('draft', 'RFQ'),
            ('sent', 'RFQ Sent'),
            ('to approve', 'To Approve'),
            ('purchase', 'Purchase Order'),
            ('cancel', 'Cancelled')
        ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    
    def compute_make_readonly_usr(self):
        for record in self:
            if record.validate_state == 'pre_validate' and not record.env.user.has_group('purchase.group_purchase_manager'):
                record.make_readonly_user = True
            else:
                record.make_readonly_user = False
    shipment_id = fields.Many2one(
        'shipment.register', string='Shipment', index='btree_not_null',
        ondelete='set null', copy=False, tracking=True,
    )

    def set_pre_validate(self):
        for record in self:
            already_created_pickings = record.picking_ids.filtered(lambda r: r.state != 'cancel')
            if not already_created_pickings:
                record.button_confirm()
            else:
                record.button_approve()
            record.write({
                'validate_state':'pre_validate',
                'is_pre_validate':True,
            })
    
    def set_unvalidate(self):
        for record in self:
            record._cancel_stock_chain()
            record.write({
                'validate_state':'un_validate',
                'is_pre_validate':False,
                'state':'draft',
            })
    
    def custom_confirm_order(self):
        self.write({'custom_state': 'purchase'})


    @api.depends('order_line.total_product_line_cbm','order_line')
    def compute_total_order_cbm(self):
        for record in self:
            purchase_lines = record.order_line
            total_cbm = 0.0
            if not purchase_lines:
                record.total_order_cbm = total_cbm
                continue
            if purchase_lines:
                record.total_order_cbm = sum(purchase_lines.mapped('total_product_line_cbm'))

    @api.depends('order_line.total_product_line_weight', 'order_line')
    def compute_total_order_weight(self):
        for record in self:
            purchase_lines = record.order_line
            total_weight = 0.0
            if not purchase_lines:
                record.total_order_weight = total_weight
                continue
            if purchase_lines:
                record.total_order_weight = sum(purchase_lines.mapped('total_product_line_weight'))

    
    def action_create_invoice(self, attachment_ids=False):
        """Create the invoice associated to the PO.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit')

        # 1) Prepare invoice vals and clean-up the section lines
        invoice_vals_list = []
        sequence = 10
        for order in self:
            # Now We Wont Allow User To Upload Multi Bills.
            existing_bills = order.invoice_ids
            if existing_bills:
                raise UserError(_('Bill is already created for the existing Purchase Order %s',order.name))
            order = order.with_company(order.company_id)
            pending_section = None
            # Invoice values.
            invoice_vals = order._prepare_invoice()
            # Invoice line values (keep only necessary sections).
            for line in order.order_line:
                if line.display_type in ('line_section', 'line_subsection'):
                    pending_section = line
                    continue
                if pending_section:
                    line_vals = pending_section._prepare_account_move_line()
                    line_vals.update({'sequence': sequence})
                    invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                    sequence += 1
                    pending_section = None
                line_vals = line._prepare_account_move_line()
                line_vals.update({'sequence': sequence})
                invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                sequence += 1
            
            # Now landed costs will be used on manual bills specific to landed costs and then user can assign values to purchase order bills.
            
            # Section/Note Before LC Products.
            lc_vals = {}
            lc_vals['display_type'] = 'line_section'
            lc_vals['name'] = 'Landed Costs'
            lc_vals['sequence'] = sequence
            sequence += 1
            invoice_vals['invoice_line_ids'].append((0, 0, lc_vals))
            landed_cost_products = self.env['product.product'].sudo().search([
                ('landed_cost_ok','=',True),('name','ilike','Exchange')
            ])
            # Section/Note Before LC Products.

            # Landed Costs Products Being Added Automatically Instead Letting User Add Them Manually On Bills.
            for product in landed_cost_products:
                lc_vals = {}
                lc_vals['sequence'] = sequence
                lc_vals['product_id'] = product.id
                lc_vals['is_landed_costs_line'] = product.landed_cost_ok
                lc_vals['is_currency_exchange'] = True
                sequence += 1
                invoice_vals['invoice_line_ids'].append((0, 0, lc_vals))
            # Landed Costs Products Being Added Automatically Instead Letting User Add Them Manually On Bills.
            invoice_vals_list.append(invoice_vals)

        # 2) group by (company_id, partner_id, currency_id) for batch creation
        new_invoice_vals_list = []
        for _grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: (x.get('company_id'), x.get('partner_id'), x.get('currency_id'))):
            origins = set()
            ref_invoice_vals = None
            for invoice_vals in invoices:
                if not ref_invoice_vals:
                    ref_invoice_vals = invoice_vals
                else:
                    ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                origins.add(invoice_vals['invoice_origin'])
            ref_invoice_vals.update({
                'invoice_origin': ', '.join(origins),
            })
            new_invoice_vals_list.append(ref_invoice_vals)
        invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.
        invoices = self.env['account.move']
        AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
        for vals in invoice_vals_list:
            invoices |= AccountMove.with_company(vals['company_id']).create(vals)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        invoices.filtered(lambda m: m.currency_id.round(m.amount_total) < 0).action_switch_move_type()

        # 5) Link the attachments to the invoice
        attachments = self.env['ir.attachment'].browse(attachment_ids)
        if not attachments:
            return self.action_view_invoice(invoices)

        if len(invoices) > 1:
            raise ValidationError(_("You can only upload a bill for a single vendor at a time."))
        invoices.with_context(skip_is_manually_modified=True)._extend_with_attachments(
            invoices._to_files_data(attachments),
            new=True,
        )

        invoices.message_post(attachment_ids=attachments.ids)

        attachments.write({'res_model': 'account.move', 'res_id': invoices.id})
        return self.action_view_invoice(invoices)
    

    def _create_picking(self):
        StockPicking = self.env['stock.picking']
        for order in self.filtered(lambda po: po.state == 'purchase'):
            if any(product.type == 'consu' for product in order.order_line.product_id):
                order = order.with_company(order.company_id)
                pickings = order.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel'))
                if not pickings:
                    res = order._prepare_picking()
                    picking = StockPicking.with_user(SUPERUSER_ID).create(res)
                    pickings = picking
                else:
                    picking = pickings[0]
                moves = order.order_line._create_stock_moves(picking)
                moves = moves.filtered(lambda x: x.state not in ('done', 'cancel'))._action_confirm()
                seq = 0
                for move in sorted(moves, key=lambda move: move.date):
                    seq += 5
                    move.sequence = seq

                # We dont need to assign automatically
                # moves._action_assign()

                # Get following pickings (created by push rules) to confirm them as well.
                forward_pickings = self.env['stock.picking']._get_impacted_pickings(moves)
                (pickings | forward_pickings).action_confirm()
                picking.message_post_with_source(
                    'mail.message_origin_link',
                    render_values={'self': picking, 'origin': order},
                    subtype_xmlid='mail.mt_note',
                )
    
    def compute_empty_cbm_warning(self):
        for record in self:
            purchase_lines = record.order_line
            cbm_list = []
            if not purchase_lines:
                record.empty_cbm_warning = False
            if purchase_lines:
                cbm_list = purchase_lines.mapped('product_unit_cbm')
                if 0.0 in cbm_list:
                    record.empty_cbm_warning = "There are purchase lines having 0 Product CBM."
                else:
                    record.empty_cbm_warning = False
    
    def button_cancel(self):
        self.write({'custom_state':'cancel',
            'validate_state':'un_validate',
            'is_pre_validate':False,})
        return super().button_cancel()
    
    def button_draft(self):
        self.write({'custom_state':'draft'})
        return super().button_draft()
    
    def _cancel_stock_chain(self, log_message=None):
        """Cancel/cleanup the stock moves and pickings linked to the PO,
        without changing the PO state."""
        order_lines_ids = OrderedSet()
        pickings_to_cancel_ids = OrderedSet()
        pickings_to_cancel = False

        for order in self:
            if order.state in ('draft', 'sent', 'to approve', 'purchase'):
                order_lines_ids.update(order.order_line.ids)
            pickings_to_cancel_ids.update(
                order.picking_ids.filtered(lambda r: r.state not in ('cancel', 'done')).ids
            )
            for picking in order.picking_ids:
                if picking.state == 'done':
                    picking.message_post(body=log_message or self.env._(
                        "The purchase order %s this receipt is linked to was cancelled.",
                        order._get_html_link()))

            if order.reference_ids:
                order.reference_ids.purchase_ids = [Command.unlink(order.id)]

        order_lines = self.env['purchase.order.line'].browse(order_lines_ids)
        moves_to_cancel_ids = OrderedSet()
        moves_to_recompute_ids = OrderedSet()
        for order_line in order_lines:
            moves_to_cancel_ids.update(order_line.move_ids.filtered(lambda m: m.state != 'done').ids)
            if order_line.move_dest_ids:
                move_dest_ids = order_line.move_dest_ids.filtered(
                    lambda m: m.state != 'done' and m.location_dest_usage != 'inventory')
                moves_to_mts = move_dest_ids.filtered(
                    lambda m: m.rule_id.route_id != m.location_dest_id.warehouse_id.reception_route_id)
                move_dest_ids -= moves_to_mts
                moves_to_recompute_ids.update(moves_to_mts.ids)
                moves_to_unlink = move_dest_ids.filtered(lambda m: len(m.created_purchase_line_ids.ids) > 1)
                if moves_to_unlink:
                    moves_to_unlink.created_purchase_line_ids = [Command.unlink(order_line.id)]
                move_dest_ids -= moves_to_unlink
                if order_line.propagate_cancel:
                    moves_to_cancel_ids.update(move_dest_ids.ids)
                else:
                    moves_to_recompute_ids.update(move_dest_ids.ids)

        if moves_to_cancel_ids:
            self.env['stock.move'].browse(moves_to_cancel_ids)._action_cancel()

        if moves_to_recompute_ids:
            moves_to_recompute = self.env['stock.move'].browse(moves_to_recompute_ids)
            moves_to_recompute.write({'procure_method': 'make_to_stock'})
            moves_to_recompute._recompute_state()

        if pickings_to_cancel_ids:
            pickings_to_cancel = self.env['stock.picking'].browse(pickings_to_cancel_ids)
            pickings_to_cancel.write({'is_unvalidated':True})
            pickings_to_cancel.action_cancel()

        if order_lines:
            order_lines.write({'move_dest_ids': [(5, 0, 0)]})
    
    @api.depends('picking_ids')
    def _compute_incoming_picking_count(self):
        for order in self:
            order.incoming_picking_count = len(order.picking_ids.filtered(lambda p: not p.is_unvalidated))
    
    def action_view_picking(self):
        return self._get_action_view_picking(self.picking_ids.filtered(lambda p: not p.is_unvalidated))
    
    def _get_action_view_picking(self, pickings):
        """ This function returns an action that display existing picking orders of given purchase order ids. When only one found, show the picking immediately.
        """
        self.ensure_one()
        result = self.env["ir.actions.actions"]._for_xml_id('stock.action_picking_tree_all')
        # override the context to get rid of the default filtering on operation type
        result['context'] = {'default_partner_id': self.partner_id.id, 'default_origin': self.name, 'default_picking_type_id': self.picking_type_id.id}
        # choose the view_mode accordingly
        pickings = pickings.filtered(lambda p: not p.is_unvalidated)
        if not pickings or len(pickings) > 1:
            result['domain'] = [('id', 'in', pickings.ids)]
        elif len(pickings) == 1:
            res = self.env.ref('stock.view_picking_form', False)
            form_view = [(res and res.id or False, 'form')]
            result['views'] = form_view + [(state, view) for state, view in result.get('views', []) if view != 'form']
            result['res_id'] = pickings.id
        return result
    
    def write(self, vals):
        pickings = False
        picking_names = []
        if 'date_planned' in vals:
            pickings = self.picking_ids.filtered(lambda p:p.state not in ['done','cancel'])
            if pickings:
                if len(pickings) == 1:
                    pickings.write({
                        'scheduled_date': vals['date_planned'],
                    })
                if len(pickings) > 1:
                    picking_names = ", ".join(pickings.mapped('name'))
                    self.message_post(body=Markup(
                        '<div style="background-color:#FFA500; color:#000; padding:8px 12px; border-radius:4px;">'
                        '<b>Warning:</b> The date planned of the purchase order has been changed.<br/>'
                        'But there are multiple receipts for this Purchase Order.<br/>'
                        '<b>%s</b><br/>'
                        'Change their <b>Scheduled Date</b> manually.'
                        '</div>'
                    ) % escape(picking_names))       
        res = super().write(vals)
        return res

    
class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_unit_cbm = fields.Float(related="product_id.product_cbm", store=True)

    product_unit_weight = fields.Float(related="product_id.product_weight", store=True)

    total_product_line_cbm = fields.Float(compute="compute_total_product_line_cbm", digits=(16,6), store=True)

    total_product_line_weight = fields.Float(compute="compute_total_product_line_weight", digits=(16,6), store=True)


    @api.depends('product_qty','product_unit_cbm')
    def compute_total_product_line_cbm(self):
        for record in self:
            record.total_product_line_cbm = record.product_qty * record.product_unit_cbm

    @api.depends('product_qty', 'product_unit_weight')
    def compute_total_product_line_weight(self):
        for record in self:
            record.total_product_line_weight = record.product_qty * record.product_unit_weight
    
    def write(self, vals):
        if self.order_id.is_pre_validate and not self.env.user.has_group('purchase.group_purchase_manager'):
            raise UserError(_("You cannot edit Pre Validated Purchase Quotation. Contact Purchase Administrator."))      
        res = super().write(vals)
        return res



