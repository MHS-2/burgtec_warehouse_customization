# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_only_landed_cost_bill = fields.Boolean(compute="compute_is_only_landed_cost_bill",store=True)

    landed_cost_product_ids = fields.Many2many('product.product',compute="compute_landed_cost_products",store=True)

    transferred_move_ids = fields.Many2many(string="Transferred Entries",
            comodel_name='account.move',
            relation='account_move_transferred_rel',
            column1='original_move_id',
            column2='transferred_move_id',
            help="The transferred entries created by this invoice when linked to other move.",
            copy=False,
            compute="compute_transferred_move_ids",
            store=True)
    

    @api.depends('invoice_line_ids','invoice_line_ids.is_line_linked')
    def compute_transferred_move_ids(self):
        for record in self:
            move_lines = record.invoice_line_ids.filtered(lambda i:i.is_line_linked)
            if not move_lines:
                record.transferred_move_ids = False
            if move_lines:
                record.transferred_move_ids = move_lines.mapped('transfer_move_id')
    
    @api.depends('partner_id','partner_id.product_ids')
    def compute_landed_cost_products(self):
        for record in self:
            if not record.partner_id:
                record.landed_cost_product_ids = False
                continue
            record.landed_cost_product_ids = record.partner_id.product_ids
    


    def button_create_landed_costs(self):
        """Create a `stock.landed.cost` record associated to the account move of `self`, each
        `stock.landed.costs` lines mirroring the current `account.move.line` of self.
        """
        self.ensure_one()
        product_lines = self.line_ids.filtered(lambda line:not line.is_landed_costs_line)
        cbm_list = product_lines.mapped('product_id.product_cbm')
        if 0.0 in cbm_list:
            raise UserError(_('Product in your lines have 0 CBM. Make sure CBM is not 0 as it will affect landed costs!'))
        landed_costs_lines = self.line_ids.filtered(lambda line: line.is_landed_costs_line)
        source_orders = self.line_ids.purchase_line_id.order_id
        transfers = source_orders.mapped('picking_ids').filtered(lambda p:p.state == 'done')

        sign = -1 if self.move_type in ['in_refund'] else 1
        landed_costs = self.env['stock.landed.cost'].with_company(self.company_id).create({
            'vendor_bill_id': self.id,
            'picking_ids': transfers if transfers else False,
            'pick_domain': source_orders.mapped('name')[0],
            'cost_lines': [(0, 0, {
                'product_id': l.product_id.id,
                'name': l.product_id.name,
                'account_id': l.product_id.product_tmpl_id.get_product_accounts()['stock_valuation'].id,
                'price_unit': sign * l.currency_id._convert(l.price_subtotal, l.company_currency_id, l.company_id, self.invoice_date or fields.Date.context_today(l)),
                'split_method': l.product_id.split_method_landed_cost or 'equal',
            }) for l in landed_costs_lines],
        })
        action = self.env["ir.actions.actions"]._for_xml_id("stock_landed_costs.action_stock_landed_cost")
        return dict(action, view_mode='form', res_id=landed_costs.id, views=[(False, 'form')])
    
    def add_landed_cost_product(self):
        line_vals = {}
        vendor = self.partner_id 
        if not vendor:
            raise UserError(_('Kindly select the vendor for this bill. !'))
        move_lines = self.invoice_line_ids.sorted(lambda m:m.sequence)
        sequence = 10
        if move_lines:
            sequence = move_lines[-1].sequence + 1
        lc_product = self.env['product.product'].sudo().search([
            ('seller_ids.partner_id','=',vendor.id),
            ('landed_cost_ok', '=', True),
        ],limit=1)
        if not lc_product:
            raise UserError(_('No Landed Cost Product Found For Vendor %s',vendor.name))
        if lc_product:
            line_vals['sequence'] = sequence
            line_vals['product_id'] = lc_product.id
            line_vals['is_landed_costs_line'] = lc_product.landed_cost_ok
        if line_vals:
            self.invoice_line_ids = [(0,0,line_vals)]
    
    @api.depends('partner_id', 'date', 'state', 'move_type')
    @api.depends_context('input_full_display_name','po_bill')
    def _compute_display_name(self):
        for move in self:
            if move.env.context.get('po_bill'):
                if move.name:
                    move.display_name = f"{move.purchase_order_name} - {move.name}"
                else:
                    move.display_name = move.purchase_order_name
            else:
                move.display_name = move._get_move_display_name(show_ref=True)
    
    @api.depends('partner_id','partner_id.is_landed_cost_vendor')
    def compute_is_only_landed_cost_bill(self):
        for record in self:
            if not record.partner_id:
                record.is_only_landed_cost_bill = False
                continue
            record.is_only_landed_cost_bill = record.partner_id.is_landed_cost_vendor

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    parent_move_line_id = fields.Many2one('account.move.line', ondelete='cascade')

    transfer_move_id = fields.Many2one('account.move',help="From this Move Id this line will be tranferred and linked to another move id.")

    is_line_linked = fields.Boolean()

    is_currency_exchange = fields.Boolean()

    def link_line(self):
        line_vals = []
        transfer_move = self.transfer_move_id
        product = self.product_id
        if not product:
            raise UserError(_('Product is required to link !!'))
        if not transfer_move:
            raise UserError(_('Kindly select the Purchase Vendor Bill to link this line.'))
        existing_lines = transfer_move.invoice_line_ids.sorted(lambda i:i.sequence)
        # transferred_lines = existing_lines.filtered(lambda tl:tl.parent_move_line_id)
        sequence=10
        if existing_lines:
            sequence = existing_lines[-1].sequence + 1
        # if transferred_lines:
        #     sequence = transferred_lines[-1].sequence + 1
        
        # if not transferred_lines:
        #     line_vals.append({
        #         'move_id':transfer_move.id,
        #         'display_type':'line_section',
        #         'name': 'Landed Costs',
        #         'sequence':sequence
        #     })
        #     sequence += 1
        lc_product_already_added = existing_lines.filtered(lambda i:i.product_id.id == product.id) 
        if lc_product_already_added:
            raise UserError(_('%s, is already added in the selected purchase vender bill %s.', lc_product_already_added.product_id.name, transfer_move.purchase_order_name))
        line_data = self.copy_data()[0]
        line_data['sequence'] = sequence
        line_data['move_id'] = transfer_move.id
        line_data['parent_move_line_id'] = self.id

        line_vals.append(line_data)

        res = self.env['account.move.line'].sudo().create(line_vals)
        if res:
            self.move_id.write({
                'transferred_move_ids': [(4,transfer_move.id,0)],
            })
            self.write({
                'is_line_linked': True,
            })
    
    def unlink(self):
        for record in self:
            if not record.env.user.has_group('account.group_account_manager'):
                raise UserError(_('You are not allowed to delete bill or its lines !. Contact Administrator.'))
        return super().unlink()


            
