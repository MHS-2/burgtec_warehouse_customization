from odoo import models

class BurgtecStockPickingSlipReport(models.AbstractModel):
    _name = 'report.burgtec_warehouse_customization.stock_picking_slip'
    _description = "Stock Custom Report"

    def _get_report_values(self, docids, data=None):
        report = self.env['ir.actions.report']._get_report_from_name(
            'burgtec_warehouse_customization.stock_picking_slip'
        )

        docs = self.env[report.model].browse(docids)

        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'company': self.env.company,
            'docs': docs,
            'get_product_location_quantities':
                self.get_product_location_quantities,
        }

    def get_product_location_quantities(self, product):
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '!=', 0),
        ])

        result = []

        for quant in quants:
            result.append({
                'location': quant.location_id.display_name,
                'quantity': quant.quantity,
            })

        return result