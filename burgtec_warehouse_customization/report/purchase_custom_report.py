from odoo import models

class PurchaseCustomReport(models.AbstractModel):
    _name = 'report.burgtec_warehouse_customization.purchase_custom_report'
    _description = "Purchase Order Custom Report"


    def _get_report_values(self, docids, data=None):
        # get the report action back as we will need its data
        report = self.env['ir.actions.report']._get_report_from_name('burgtec_warehouse_customization.purchase_custom_report')
        # get the records selected for this rendering of the report
        docs = self.env[report.model].browse(docids)

        return {
            'docs':docs
        }