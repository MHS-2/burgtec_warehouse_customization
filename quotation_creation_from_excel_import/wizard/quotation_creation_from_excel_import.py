import base64
import io
import openpyxl
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

COL_ORDER_REF = "Order Reference"
COL_INTERNAL_REF = "Order Lines/Product/Internal Reference"
COL_QUANTITY = "Order Lines/Quantity"
COL_UNIT_PRICE = "Order Lines/Unit Price"
COL_NOTES = "Order Lines/Notes"
COL_GROUP_NAME = "Order Lines/Line Group Name"
COL_SECTION_NAME = "Order Lines/Line Section Name"
COL_KIT_BOM_ID = "Order Lines/Kit BoM ID"


class QuotationCreationExcelImport(models.TransientModel):
    _name = "quotation.creation.excel.import"
    _description = "Create Quotation from Excel"

    state = fields.Selection([("upload", "Upload"), ("preview", "Preview")], default="upload")
    file = fields.Binary("Excel File", required=True)
    filename = fields.Char()
    partner_id = fields.Many2one("res.partner", "Customer", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    line_ids = fields.One2many("quotation.creation.excel.import.line", "wizard_id")
    error_count = fields.Integer(compute="_compute_error_count")
    sale_order_id = fields.Many2one('sale.order', 'Sale Order')

    @api.depends("line_ids.has_error")
    def _compute_error_count(self):
        for wizard in self:
            wizard.error_count = len(wizard.line_ids.filtered("has_error"))

    @api.onchange("file")
    def _onchange_file(self):
        self.line_ids = [Command.clear()]
        self.state = "upload"

    def _reopen_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Create / Update Quotation from Excel"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _get_kit_bom(self, product):
        bom = self.env["mrp.bom"].search([("product_id", "=", product.id)], limit=1)
        if not bom:
            bom = self.env["mrp.bom"].search([
                ("product_tmpl_id", "=", product.product_tmpl_id.id),
                ("product_id", "=", False),
            ], limit=1)
        return bom

    # Preview button: read the Excel and show the quotation lines
    def action_preview(self):
        self.ensure_one()
        self.line_ids = [Command.clear()]

        # Open the Excel file
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(base64.b64decode(self.file)), data_only=True)
        except Exception:
            raise UserError(_("Cannot read the file. Please upload the .xlsx exported from Odoo 18."))
        sheet = workbook.active

        # First row = column headers
        headers = [cell.value for cell in sheet[1]]
        for column in (COL_INTERNAL_REF, COL_QUANTITY):
            if column not in headers:
                raise UserError(_("Column '%s' is missing in the file.", column))

        order_ref = ""
        vendor_ref = ""
        line_group_name = ''
        line_section_name = ''
        line_notes = ''
        row_number = 1
        for values in sheet.iter_rows(min_row=2, values_only=True):
            row_number += 1
            if not any(values):
                continue  # skip empty rows
            row = dict(zip(headers, values))

            # Odoo export writes the order data only on the first line of each order
            if row.get(COL_ORDER_REF):
                order_ref = str(row[COL_ORDER_REF])
            if row.get(COL_NOTES):
                line_notes = str(row[COL_NOTES])
            if row.get(COL_GROUP_NAME):
                line_group_name = str(row[COL_GROUP_NAME])
            if row.get(COL_SECTION_NAME):
                line_section_name = str(row[COL_SECTION_NAME])
            kit_bom_id = 0
            if row.get(COL_KIT_BOM_ID):
                try:
                    kit_bom_id = int(float(row[COL_KIT_BOM_ID]))
                except (TypeError, ValueError):
                    kit_bom_id = 0
            internal_ref = str(row.get(COL_INTERNAL_REF) or "").strip()
            quantity = float(row.get(COL_QUANTITY) or 0.0)
            price_unit = float(row.get(COL_UNIT_PRICE) or 0.0)

            # Find the product and its Kit BoM
            product = self.env["product.product"]
            bom = self.env["mrp.bom"]
            if internal_ref:
                product = product.search([("default_code", "=", internal_ref), ('custom_variant_type', '=', 'product')])

            if not kit_bom_id:
                if len(product) == 1:
                    bom = self._get_kit_bom(product)

            # Validate the line
            error = ""
            if not internal_ref:
                error = _("Internal Reference is empty.")
            elif not product:
                error = _("Product with internal ref '%s' not found in Burgtec Warehouse.", internal_ref)
            elif len(product) > 1:
                error = _("Internal Reference '%s' is used by more than one product in Burgtec Warehouse.",
                          internal_ref)
            elif not bom and not kit_bom_id:
                error = _("No Kit BoM found for '%s'.", product.display_name)

            self.env["quotation.creation.excel.import.line"].create({
                "wizard_id": self.id,
                "row_number": row_number,
                "order_ref": order_ref,
                "internal_ref": internal_ref,
                "product_id": product.id if len(product) == 1 else False,
                "bom_id": kit_bom_id if kit_bom_id else bom.id,
                "quantity": quantity,
                "price_unit": price_unit,
                "line_group_name": line_group_name,
                "line_section_name": line_section_name,
                'notes': line_notes,
                "has_error": bool(error),
                "message": error,
            })

        self.state = "preview"
        return self._reopen_wizard()

    def action_create_quotation(self):
        self.ensure_one()
        if not self.line_ids or self.error_count:
            raise ValidationError(_("Fix the errors in the preview first."))

        purchase_order_value = sum(self.line_ids.mapped('subtotal'))

        quotation = self.env["sale.order"].create({
            "partner_id": self.partner_id.id,
            "is_created_from_excel": True,
            'purchase_order_value': purchase_order_value,
            "customer_po_reference": self.line_ids[0].order_ref,
        })

        for line in self.line_ids:
            self.env["sale.order.line"].create({
                "order_id": quotation.id,
                "product_id": line.product_id.id,
                'notes': line.notes,
                "product_uom_qty": line.quantity,
                "price_unit": line.price_unit,
                "kit_bom_id": line.bom_id.id,
                "line_group_name": line.line_group_name,
                "line_section_name": line.line_section_name,

            })

        quotation.message_post(
            body=_("Quotation created from Excel import."),
            attachments=[(self.filename, base64.b64decode(self.file))],
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": quotation.id,
            "view_mode": "form",
        }

    def action_update_quotation(self):
        self.ensure_one()
        if not self.line_ids or self.error_count:
            raise ValidationError(_("Fix the errors in the preview first."))
        sale_order = self.sale_order_id
        sale_order_lines = sale_order.order_line
        wizard_lines = self.line_ids
        if sale_order_lines:
            sale_order_lines.unlink()
        # if sale_order_lines:
        #     existing_refs = sale_order_lines.mapped("product_id.default_code")
        #     matching_lines = wizard_lines.filtered(lambda l: l.internal_ref in existing_refs)
        #     if matching_lines:
        #         names = "\n".join(matching_lines.mapped("product_id.display_name"))
        #         raise ValidationError(_("Products are already present in Sale Order:\n%s", names))
        for line in wizard_lines:
            self.env["sale.order.line"].create({
                "order_id": sale_order.id,
                "product_id": line.product_id.id,
                'notes': line.notes,
                "product_uom_qty": line.quantity,
                "price_unit": line.price_unit,
                "kit_bom_id": line.bom_id.id,
                "line_group_name": line.line_group_name,
                "line_section_name": line.line_section_name,
            })
        sale_order.message_post(
            body=_("Quotation Updated from Excel import."),
            attachments=[(self.filename, base64.b64decode(self.file))],
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": sale_order.id,
            "view_mode": "form",
        }


class QuotationCreationExcelImportLine(models.TransientModel):
    _name = "quotation.creation.excel.import.line"
    _description = "Excel Import Preview Line"
    _order = "row_number"

    wizard_id = fields.Many2one("quotation.creation.excel.import")
    row_number = fields.Integer("Row")
    order_ref = fields.Char("Customer Ref")
    internal_ref = fields.Char("Internal Reference")
    product_id = fields.Many2one("product.product", "Product")
    product_tmpl_id = fields.Many2one(related="product_id.product_tmpl_id")
    bom_id = fields.Many2one(
        "mrp.bom", "Kit BoM",
        domain="[('product_tmpl_id', '=', product_tmpl_id), "
               "'|', ('product_id', '=', product_id), ('product_id', '=', False)]")
    quantity = fields.Float(digits="Product Unit")
    price_unit = fields.Float("Unit Price", digits="Product Price")
    subtotal = fields.Float(compute="_compute_subtotal", digits="Product Price")
    has_error = fields.Boolean()
    message = fields.Char("Error")
    notes = fields.Text("Notes")
    line_group_name = fields.Char("Line Group")
    line_section_name = fields.Char("Line Code")

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    def action_done(self):
        if not self.product_id:
            raise ValidationError('Please select a product.')
        if not self.bom_id:
            raise ValidationError('Please select a Kit BoM.')
        res = self.write({
            "has_error": False,
            "message": '',
            'internal_ref': self.product_id.default_code,
            'product_id': self.product_id.id,
            'bom_id': self.bom_id.id,
        })
        if res:
            return {
                "type": "ir.actions.act_window",
                "res_model": "quotation.creation.excel.import",
                "res_id": self.wizard_id.id,
                "view_mode": "form",
                'context': {
                    'wizard_id': self.wizard_id.id,
                },
                'target': 'new',
            }

    def action_custom_cancel(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "quotation.creation.excel.import",
            "res_id": self.wizard_id.id,
            "view_mode": "form",
            'context': {
                'wizard_id': self.wizard_id.id,
            },
            'target': 'new',
        }

    def action_open_edit_line_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "quotation.creation.excel.import.line",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                'quotation_creation_from_excel_import.quotation_creation_excel_import_line_view_from_editable').id,
            'context': {
                'wizard_id': self.wizard_id.id,
            },
            'target': 'new',
        }

    @api.onchange('product_id')
    def onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.bom_id = False
