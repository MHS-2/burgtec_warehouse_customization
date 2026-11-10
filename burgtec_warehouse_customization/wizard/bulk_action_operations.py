import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup
from odoo.http import request

_logger = logging.getLogger(__name__)

class BulkActionOperations(models.TransientModel):
    _name = 'bulk.action.operations'
    _description = 'BulkActionOperations'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    bulk_lines = fields.One2many('bulk.action.operation.line', 'bulk_action_operation_id')
    operation_type = fields.Selection([('delete', 'Delete'), ('duplicate', 'Duplicate')],
                                      string='Operation Type')
    global_select = fields.Boolean(default=False, string='Global Select')

    target_sale_order_id = fields.Many2one('sale.order', string="Target Sale Order")

    @api.onchange('global_select')
    def _onchange_is_check(self):
        for rec in self:
            product_lines = rec.bulk_lines
            if product_lines:
                if rec.global_select:
                    product_lines.update({
                        'is_check': True,
                    })
                else:
                    product_lines.update({
                        'is_check': False,
                    })

    @api.model
    def default_get(self, fields_list):
        """Populate wizard lines from sale order"""
        res = super(BulkActionOperations, self).default_get(fields_list)
        # Get the active sale order
        sale_order_id = self.env.context.get('active_id')
        if not sale_order_id:
            raise UserError(_('No Sale Order found in context.'))
        sale_order = self.env['sale.order'].browse(sale_order_id)
        res['sale_order_id'] = sale_order_id
        sale_order_lines = sale_order.order_line

        # Prepare lines from sale order lines
        line_vals = []
        for line in sale_order_lines:
            line_vals.append((0, 0, {
                'sequence': line.sequence,
                'name': line.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'currency_id': line.currency_id.id,
                'order_line_id': line.id,
                'is_check': False,
            }))
        res.update({
            'bulk_lines': line_vals,
            'target_sale_order_id':sale_order_id
        })
        return res

    def action_bulk_delete(self):
        """Delete selected lines from sale order"""
        if self.sale_order_id.state != 'draft':
            raise ValidationError(_("You cannot delete order lines from a Confirmed Sales Order !!!"))
        selected_lines = self.bulk_lines.filtered(lambda l: l.is_check)
        if not selected_lines:
            raise UserError(_('No lines selected for deletion.'))

        # Get the original sale order lines
        order_lines_to_delete = selected_lines.mapped('order_line_id')
        count = len(order_lines_to_delete)

        # Prepare product list
        product_list = ''
        for line in order_lines_to_delete:
            product_name = line.product_id.display_name or line.name or 'N/A'
            qty = line.product_uom_qty
            product_list += f'<li>{product_name} (Qty: {qty})</li>'

        # Delete from sale order
        order_lines_to_delete.unlink()

        # Post message on sale order
        message_body = Markup(f"""
            <div style="background-color: #ffcdd2; border: 2px solid #c62828; border-radius: 5px; padding: 15px; margin: 10px 0;">
                <h4 style="color: #c62828; margin: 0 0 10px 0;">
                    <span style="font-size: 18px;">🗑️</span> Bulk Delete Action
                </h4>
                <p style="margin: 5px 0; color: #333; font-weight: bold;">
                    {count} Sale Order Line(s) have been deleted.
                </p>
                <details style="margin-top: 10px;">
                    <summary style="cursor: pointer; color: #c62828; font-weight: bold;">
                        View Deleted Products
                    </summary>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        {product_list}
                    </ul>
                </details>
                <p style="margin: 10px 0 0 0; font-size: 12px; color: #666;">
                    Deleted by: {self.env.user.name} on {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </div>
        """)

        self.sale_order_id.message_post(
            body=message_body,
            subject='Bulk Delete Action',
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        # Close wizard and reload sale order
        return {'type': 'ir.actions.act_window_close'}

    def action_duplicate(self):
        selected_lines = self.bulk_lines.filtered(lambda l: l.is_check)
        if not selected_lines:
            raise UserError(_('No lines selected for duplication.'))

        root_url = request.httprequest.url_root
        sale_order = self.sale_order_id
        target_sale_order = self.target_sale_order_id
        target_sale_order_bom_component_id = target_sale_order.bom_component_id
        product_list = ''
        for line in selected_lines:
            order_line = line.order_line_id
            product_name = order_line.product_id.display_name or order_line.name or 'N/A'
            qty = order_line.product_uom_qty
            product_list += f'<li>{product_name} (Qty: {qty})</li>'

        if target_sale_order.id != sale_order.id:  # Duplicating to a different sale order.
            duplication_statement = f"{len(selected_lines)} Sale Order Line(s) have been duplicated to <a href='{root_url}/odoo/sale.order/{target_sale_order.id}'>{target_sale_order.name}</a>."
        else:
            duplication_statement = f"{len(selected_lines)} Sale Order Line(s) have been duplicated."

        for line in selected_lines:

            order_line_id = line.order_line_id
            new_sale_order_line_vals = order_line_id.copy_data()[0]

            old_bom_component_lines = order_line_id.component_line_ids
            new_bom_component_lines = old_bom_component_lines.copy_data()

            new_sale_order_line_vals['order_id'] = target_sale_order.id
            new_sale_order_line_vals['sequence'] = target_sale_order.next_sequence

            new_sale_order_line = self.env['sale.order.line'].with_context(creation_by_duplication=True).create(new_sale_order_line_vals)

            new_sale_order_line_sequence = new_sale_order_line.sequence
            # now components lines
            for bom_component_line in new_bom_component_lines:

                bom_component_line['order_line_id'] = new_sale_order_line.id
                bom_component_line['component_id'] = (
                    target_sale_order_bom_component_id.id
                )

                if bom_component_line.get('display_type'):
                    bom_component_line['sequence'] = (
                            new_sale_order_line_sequence - 1
                    )

                elif bom_component_line.get('is_parent'):
                    bom_component_line['sequence'] = (
                        new_sale_order_line_sequence
                    )

                else:
                    new_sale_order_line_sequence += 1
                    bom_component_line['sequence'] = (
                        new_sale_order_line_sequence
                    )

            self.env['sale.order.bom.component.line'].create(
                new_bom_component_lines
            )

            target_sale_order.write({
                'next_sequence': new_sale_order_line_sequence + 2
            })

        message_body = Markup(f"""
            <div style="background-color: #B8FFB8;border: 2px solid #7CA37C;border-radius: 5px;padding: 15px;margin: 10px 0;">
                <h4 style="color: #114F11; margin: 0 0 10px 0;">
                    <span style="font-size: 18px;">
                        <i class="fa fa-clone" aria-hidden="true"></i>
                    </span>
                    Bulk Duplicate Action
                </h4>

                <p style="margin: 5px 0;color: #000000;font-weight: bold;">
                    {duplication_statement}
                </p>

                <details style="margin-top: 10px;">
                    <summary style="cursor: pointer;color: #114F11;font-weight: bold;">
                        View Duplicated Products
                    </summary>

                    <ul style="margin: 10px 0;padding-left: 20px;">
                        {product_list}
                    </ul>
                </details>

                <p style="margin: 10px 0 0 0;font-size: 12px;color: #000000;">
                    Duplicated by: {self.env.user.name} on
                    {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </div>
        """)

        self.sale_order_id.message_post(
            body=message_body,
            subject='Bulk Duplicate Action',
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        return {'type': 'ir.actions.act_window_close'}


class BulkActionOperationLines(models.TransientModel):
    _name = 'bulk.action.operation.line'
    _description = 'BulkAction Operation Line'

    is_check = fields.Boolean()
    name = fields.Char()
    sequence = fields.Integer()
    product_id = fields.Many2one('product.product')
    product_uom_qty = fields.Float()
    price_unit = fields.Float()
    price_subtotal = fields.Monetary()
    currency_id = fields.Many2one('res.currency')
    custom_product_name = fields.Char()
    order_line_id = fields.Many2one('sale.order.line')
    bulk_action_operation_id = fields.Many2one('bulk.action.operations')


    @api.onchange('is_check')
    def onchange_check(self):
        if self.is_check and self.bulk_action_operation_id.operation_type == 'duplicate_with_group_and_code':
            group_code_record = self.bulk_action_operation_id.bulk_lines.filtered(lambda b:not b.is_check and (b.order_line_id.id == int(self.line_group_id_value) or b.order_line_id.id == int(self.line_section_id_value)))
            if group_code_record:
                for rec in group_code_record:
                    rec.is_check = True
