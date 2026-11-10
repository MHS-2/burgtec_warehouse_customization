from odoo import models, fields, api


class SaleOrderExt(models.Model):
    _inherit = 'sale.order'

    purchase_order_value = fields.Monetary(currency_field='currency_id', string='PO Value', readonly=True)
    is_created_from_excel = fields.Boolean(string='Is Created from Excel File?')
    po_value_warning = fields.Char(compute='_compute_po_value_warning')
    burgtec_po_id = fields.Integer(string="Burgtec PO ID", readonly=True, copy=False)
    burgtec_po_url = fields.Char(string="Burgtec PO URL", readonly=True, copy=False)
    is_created_from_child_po = fields.Boolean(string='Is Created from Child PO?')
    po_dispatch_date = fields.Datetime(string='PO Dispatch Date', copy=False, tracking=True)
    po_date_planned = fields.Datetime(string='PO Expected Arrival', copy=False, tracking=True)

    def action_open_burgtec_po(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.burgtec_po_url,
            "target": "new",
        }

    def _compute_po_value_warning(self):
        for order in self:
            if not order.is_created_from_excel:
                order.po_value_warning = False
                continue
            purchase_order_value = order.purchase_order_value
            amount_untaxed = order.amount_untaxed
            if purchase_order_value != amount_untaxed:
                if purchase_order_value > amount_untaxed:
                    order.po_value_warning = "⚠️ Attention Purchase Order Value is greater than SO Untaxed amount!"
                if purchase_order_value < amount_untaxed:
                    order.po_value_warning = "⚠️ Attention Purchase Order Value is less than SO Untaxed amount!"
            else:
                order.po_value_warning = False


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    notes = fields.Text(string='Notes')
