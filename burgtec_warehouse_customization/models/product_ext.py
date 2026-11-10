from markupsafe import Markup
from odoo import fields, models, api, _


class ProductTemplateExt(models.Model):
    _inherit = "product.template"

    def _get_default_cbm_uom(self):
        return self._get_volume_uom_name_from_ir_config_parameter()

    custom_product_type = fields.Selection([('product', 'Product'), ('component', 'Component')],
                                           string="Custom Product Type", required=True)
    id_of_it_hub = fields.Char(string="IT Hub ID", compute="compute_id_of_it_hub", store=True)

    split_method_landed_cost = fields.Selection(
        [
            ('equal', 'Equal'),
            ('by_quantity', 'By Quantity'),
            ('by_current_cost_price', 'By Current Cost'),
            ('by_weight', 'By Weight'),
            ('by_volume', 'By Product CBM'),
        ],
        string="Default Split Method",
        help="Default Split Method when used for Landed Cost"
    )

    vendor_currency_id = fields.Many2one('res.currency')

    supplier_code = fields.Char()

    custom_incoming = fields.Float(
            string='Custom Incoming',
            compute='_compute_custom_quantities',
            digits='Product Unit',
        )
    
    custom_outgoing = fields.Float(
        string='Custom Outgoing',
        compute='_compute_custom_quantities',
        digits='Product Unit',
    )

    custom_virtual_available = fields.Float(
        string='Custom Virtual Available',
        compute='_compute_custom_quantities',
        digits='Product Unit',
    )
    
    minimum_qty = fields.Float(compute="_compute_minimum_qty", store=True)
    maximum_qty = fields.Float(compute="_compute_maximum_qty", store=True)

    # Landed Costs.

    average_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",store=True)
        
    maximum_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",store=True)
    
    minimum_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",store=True)
    
    latest_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",store=True)

    manual_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs", store=True)

    actual_landed_cost = fields.Monetary(currency_field='currency_id', string="Actual Landed Cost", compute="compute_landed_costs", store=True)

    product_cbm = fields.Float(compute="compute_product_cbm", digits=(16,6), store=True)

    cbm_uom_name = fields.Char(string='CBM unit of measure label', compute='_compute_cbm_uom_name',
                               default=_get_default_cbm_uom)

    is_obsolete = fields.Boolean(compute="compute_is_obsolete",string="Is Obsolete", store=True)


    package_weight = fields.Float(string='Package Weight', compute="custom_logistics", store=True)
    package_depth = fields.Float(string='Package Depth', compute="custom_logistics", store=True)
    package_width = fields.Float(string='Package Width', compute="custom_logistics", store=True)
    package_height = fields.Float(string='Package Height', compute="custom_logistics", store=True)

    package_cbm = fields.Float(compute="custom_logistics", digits=(16,6), store=True)
    quantities_per_package = fields.Float(string='Quantities Per Package', compute="custom_logistics", store=True)
    product_weight = fields.Float(string='Product Weight', compute="custom_logistics", store=True)


    standard_freight_cost_per_cbm = fields.Monetary(string='Standard Freight Cost per CBM', compute="compute_standard_manual_landed_cost_from_supplier", store=True)
    standard_exchange_rate = fields.Float(string='Standard Exchange Rate', compute="compute_standard_manual_landed_cost_from_supplier", store=True)
    standard_duty_or_tax = fields.Float(string='Standard Duty/Tax', compute="compute_standard_manual_landed_cost_from_supplier", store=True)

    @api.depends('product_variant_ids.id_of_it_hub')
    def compute_id_of_it_hub(self):
        for template in self:
            variants = template.product_variant_ids._origin
            if variants:
                template.id_of_it_hub = variants[-1].id_of_it_hub
            else:
                False

    def _compute_custom_quantities_dict(self):
        variants_available = {
            p['id']: p for p in self.product_variant_ids._origin.read(['custom_incoming', 'custom_outgoing', 'custom_virtual_available'])
        }
        prod_available = {}
        for template in self:
            virtual_available = 0
            incoming_qty = 0
            outgoing_qty = 0
            for p in template.product_variant_ids._origin:
                virtual_available += variants_available[p.id]["custom_virtual_available"]
                incoming_qty += variants_available[p.id]["custom_incoming"]
                outgoing_qty += variants_available[p.id]["custom_outgoing"]
            prod_available[template.id] = {
                "virtual_available": virtual_available,
                "incoming_qty": incoming_qty,
                "outgoing_qty": outgoing_qty,
            }
        return prod_available


    @api.depends(
            'product_variant_ids.custom_incoming',
            'product_variant_ids.custom_outgoing',
            'product_variant_ids.custom_virtual_available',
        )
    def _compute_custom_quantities(self):
        res = self._compute_custom_quantities_dict()
        for template in self.with_context(skip_qty_available_update=True):
            template.custom_virtual_available = res[template.id]['virtual_available']
            template.custom_incoming = res[template.id]['incoming_qty']
            template.custom_outgoing = res[template.id]['outgoing_qty']

    @api.depends('product_variant_ids.minimum_qty',)
    def _compute_minimum_qty(self):
        for template in self:
            if template.product_variant_ids:
                template.minimum_qty = min(template.product_variant_ids.mapped('minimum_qty'))
            else:
                template.maximum_qty = 0.0

    @api.depends('product_variant_ids.maximum_qty',)
    def _compute_maximum_qty(self):
        for template in self:
            if template.product_variant_ids:
                template.maximum_qty = max(template.product_variant_ids.mapped('maximum_qty'))
            else:
                template.maximum_qty = 0.0
    
    def _compute_landed_costs_dict(self):
        variants_available = {
            p['id']: p for p in self.product_variant_ids._origin.read(['average_landed_cost', 'latest_landed_cost', 'maximum_landed_cost','minimum_landed_cost','manual_landed_cost','actual_landed_cost'])
        }
        prod_available = {}
        for template in self:
            average_landed_cost = 0
            latest_landed_cost = 0
            maximum_landed_cost = 0
            minimum_landed_cost = 0
            manual_landed_cost = 0
            actual_landed_cost = 0
            for p in template.product_variant_ids._origin:
                average_landed_cost += variants_available[p.id]["average_landed_cost"]
                latest_landed_cost += variants_available[p.id]["latest_landed_cost"]
                maximum_landed_cost += variants_available[p.id]["maximum_landed_cost"]
                minimum_landed_cost += variants_available[p.id]["minimum_landed_cost"]
                manual_landed_cost += variants_available[p.id]["manual_landed_cost"]
                actual_landed_cost += variants_available[p.id]["actual_landed_cost"]
            prod_available[template.id] = {
                "average_landed_cost": average_landed_cost,
                "latest_landed_cost": latest_landed_cost,
                "maximum_landed_cost": maximum_landed_cost,
                "minimum_landed_cost":minimum_landed_cost,
                "manual_landed_cost":manual_landed_cost,
                "actual_landed_cost":actual_landed_cost,
            }
        return prod_available

    
    @api.depends('product_variant_ids.average_landed_cost','product_variant_ids.latest_landed_cost',
        'product_variant_ids.maximum_landed_cost', 'product_variant_ids.minimum_landed_cost',
        'product_variant_ids.manual_landed_cost', 'product_variant_ids.actual_landed_cost')
    def compute_landed_costs(self):
        res = self._compute_landed_costs_dict()
        for template in self:
            template.average_landed_cost = res[template.id]['average_landed_cost']
            template.latest_landed_cost = res[template.id]['latest_landed_cost']
            template.maximum_landed_cost = res[template.id]['maximum_landed_cost']
            template.minimum_landed_cost = res[template.id]['minimum_landed_cost']
            template.manual_landed_cost = res[template.id]['manual_landed_cost']
            template.actual_landed_cost = res[template.id]['actual_landed_cost']
    
    @api.depends('product_variant_ids.product_cbm')
    def compute_product_cbm(self):
        for template in self:
            variants = template.product_variant_ids
            if variants:
                template.product_cbm = variants[-1].product_cbm
            else:
                template.product_cbm = 0.0
    
    def _compute_cbm_uom_name(self):
        for template in self:
            template.cbm_uom_name = self._get_volume_uom_name_from_ir_config_parameter()

    @api.depends('product_variant_ids.is_obsolete')
    def compute_is_obsolete(self):
        for template in self:
            variants = template.product_variant_ids
            if variants:
                template.is_obsolete = variants[-1].is_obsolete
            else:
                template.is_obsolete = False


    @api.depends('product_variant_ids.package_weight','product_variant_ids.package_depth',
     'product_variant_ids.package_width' ,'product_variant_ids.package_height', 'product_variant_ids.package_cbm',
     'product_variant_ids.quantities_per_package', 'product_variant_ids.product_weight')
    def custom_logistics(self):
        for template in self:
            variants = template.product_variant_ids
            if variants:
                template.package_weight = variants[-1].package_weight
                template.package_depth = variants[-1].package_depth
                template.package_height = variants[-1].package_height
                template.package_width = variants[-1].package_width
                template.package_cbm = variants[-1].package_cbm
                template.quantities_per_package = variants[-1].quantities_per_package
                template.product_weight = variants[-1].product_weight
            else:
                template.package_weight = 0.0
                template.package_depth = 0.0
                template.package_height = 0.0
                template.package_width = 0.0
                template.package_cbm = 0.0
                template.quantities_per_package = 0.0
                template.product_weight = 0.0



            
    
    @api.depends('seller_ids','seller_ids.partner_id','seller_ids.partner_id.standard_freight_cost_per_cbm','seller_ids.partner_id.standard_exchange_rate','seller_ids.partner_id.standard_duty_or_tax')
    def compute_standard_manual_landed_cost_from_supplier(self):
        for record in self:
            sellers = record.seller_ids
            vendor = False
            if not sellers:
                record.standard_freight_cost_per_cbm = 0.0
                record.standard_exchange_rate = 0.0
                record.standard_duty_or_tax = 0.0
                continue
            if sellers:
                # First Vendor
                vendor = sellers[0].partner_id
                record.standard_freight_cost_per_cbm = vendor.standard_freight_cost_per_cbm
                record.standard_exchange_rate = vendor.standard_exchange_rate
                record.standard_duty_or_tax = vendor.standard_duty_or_tax
    
    def action_open_validate_incoming_pos(self):
        dt_object = False
        if self.env.context.get('to_date'):
            dt_object = fields.Datetime.to_datetime(self.env.context.get('to_date'))
        
        domain = [
            ('product_id', '=', self.product_variant_id.id),
            ('state', 'not in', ('cancel')), 
            ('order_id.is_pre_validate','=',True),
        ]

        if dt_object:
            domain.append(('create_date','<=', dt_object))

        # --- Custom incoming = only pre-validated POs ---
        po_lines = self.env['purchase.order.line'].search(domain=domain).filtered(lambda pol: pol.product_qty - pol.qty_received != 0)
        validated_po = po_lines.mapped('order_id.id')

        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action['domain'] = [('id', 'in', validated_po)]
        action['context'] = {'create':False}
        return action
        
    def action_open_validate_outgoing_so(self):
        dt_object = False
        if self.env.context.get('to_date'):
            dt_object = fields.Datetime.to_datetime(self.env.context.get('to_date'))
        
        order_domain = [
            ('product_id', '=', self.product_variant_id.id),
            ('order_state', 'not in', ('cancel')), 
            ('is_pre_validate','=',True),
        ]

        if dt_object:
            order_domain.append(('create_date','<=', dt_object))
        
        # --- Custom outgoing = only pre-validated SOs ---
        so_bom_lines = self.env['sale.order.bom.component.line'].search(domain=order_domain).filtered(lambda bl: bl.product_qty - bl.qty_delivered != 0)
        validated_so = so_bom_lines.mapped('order_line_id.order_id.id')

        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        action['domain'] = [('id', 'in', validated_so)]
        action['context'] = {'create':False}
        return action


class ProductProductExt(models.Model):
    _inherit = "product.product"

    def _get_default_cbm_uom(self):
        return self.env['product.template']._get_volume_uom_name_from_ir_config_parameter()

    custom_variant_type = fields.Selection([('product', 'Product'), ('component', 'Component')],
                                           string="Custom Variant Type", compute="compute_custom_variant_type",
                                           store=True)
    id_of_it_hub = fields.Char(string="IT Hub ID")

    stock_valuation_adjustment_line_ids = fields.One2many('stock.valuation.adjustment.lines', 'product_id')

    average_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_average_landed_cost",
                                          store=True)
    
    maximum_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",
                                              store=True)
    
    minimum_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",
                                                  store=True)
    
    latest_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_landed_costs",
                                                  store=True)

    manual_landed_cost = fields.Monetary(currency_field='currency_id', compute="compute_manual_landed_cost", store=True)

    actual_landed_cost = fields.Monetary(currency_field='currency_id', string="Actual Landed Cost")

    product_cbm = fields.Float(compute="compute_product_cbm", digits=(16,6), store=True)

    cbm_uom_name = fields.Char(string='CBM unit of measure label', compute='_compute_cbm_uom_name',
                               default=_get_default_cbm_uom)

    is_obsolete = fields.Boolean(default=False, string="Is Obsolete")

    # additional field

    package_weight = fields.Float(string='Package Weight')
    package_depth = fields.Float(string='Package Depth')
    package_width = fields.Float(string='Package Width')
    package_height = fields.Float(string='Package Height')
    package_cbm = fields.Float(compute="compute_package_cbm", digits=(16,6), store=True)
    quantities_per_package = fields.Float(string='Quantities Per Package')
    product_weight = fields.Float(string='Product Weight', compute="compute_product_weight", store=True)

    standard_freight_cost_per_cbm = fields.Monetary(string='Standard Freight Cost per CBM', compute="compute_standard_manual_landed_cost_from_supplier", store=True)
    standard_exchange_rate = fields.Float(string='Standard Exchange Rate', compute="compute_standard_manual_landed_cost_from_supplier", store=True)
    standard_duty_or_tax = fields.Float(string='Standard Duty/Tax', compute="compute_standard_manual_landed_cost_from_supplier", store=True)

    product_average_landed_cost = fields.Monetary(currency_field='currency_id',
                                                  compute="compute_product_landed_costs",
                                                  store=True)

    product_manual_landed_cost = fields.Monetary(currency_field='currency_id',
                                                 compute="compute_product_landed_costs",
                                                 store=True)
    
    vendor_currency_id = fields.Many2one('res.currency', compute="compute_vendor_currency_id", store=True)

    supplier_code = fields.Char(compute="compute_supplier_code", store=True)

    warning_html = fields.Html(compute="compute_warning_html")

    minimum_reorder_qty = fields.Float()

    custom_incoming = fields.Float(
        string='Custom Incoming',
        compute='_compute_custom_virtual_available',
        digits='Product Unit',
    )

    custom_outgoing = fields.Float(
        string='Custom Outgoing',
        compute='_compute_custom_virtual_available',
        digits='Product Unit',
    )

    custom_virtual_available = fields.Float(
        string='Custom Virtual Available',
        compute='_compute_custom_virtual_available',
        digits='Product Unit',
    )

    minimum_qty = fields.Float()
    maximum_qty = fields.Float()

    @api.depends(
        'qty_available',
        'purchase_order_line_ids.order_id.is_pre_validate',
        'purchase_order_line_ids.qty_received',
        'purchase_order_line_ids.product_qty',
    )
    @api.depends_context('date_to')
    def _compute_custom_virtual_available(self):
        for product in self:
            incoming = 0.0
            outgoing = 0.0
            dt_object = False

            if product.env.context.get('to_date'):
                dt_object = fields.Datetime.to_datetime(product.env.context.get('to_date'))
                # create_date <= dt_object
            
            domain = [
                ('product_id', '=', product.id),
                ('state', 'not in', ('cancel')), 
                # ('qty_received', '<', 'product_qty'),
                # ('company_id', '=', self.env.company.id),
                ('order_id.is_pre_validate','=',True),
            ]

            if dt_object:
                domain.append(('create_date','<=', dt_object))

            # --- Custom incoming = only pre-validated POs ---
            po_lines = self.env['purchase.order.line'].search(domain=domain)
            for line in po_lines:
                incoming += line.product_uom_id._compute_quantity(
                    line.product_qty - line.qty_received,
                    product.uom_id,
                )
            
            order_domain = [
                ('product_id', '=', product.id),
                ('order_state', 'not in', ('cancel')), 
                # ('qty_delivered', '<', 'product_qty'),
                # ('company_id', '=', self.env.company.id),
                ('is_pre_validate','=',True),
            ]

            if dt_object:
                order_domain.append(('create_date','<=', dt_object))

            # --- Custom outgoing = only pre-validated SOs ---
            so_bom_lines = self.env['sale.order.bom.component.line'].search(domain=order_domain)
            for line in so_bom_lines:
                outgoing += line.order_line_id.product_uom_id._compute_quantity(
                    line.product_qty - line.qty_delivered,
                    product.uom_id,
                )
            product.custom_incoming = incoming
            product.custom_outgoing = outgoing
            product.custom_virtual_available = product.qty_available + incoming - outgoing
    
    def action_open_validate_incoming_pos(self):
        dt_object = False
        if self.env.context.get('to_date'):
            dt_object = fields.Datetime.to_datetime(self.env.context.get('to_date'))
        
        domain = [
            ('product_id', '=', self.id),
            ('state', 'not in', ('cancel')), 
            ('order_id.is_pre_validate','=',True),
        ]

        if dt_object:
            domain.append(('create_date','<=', dt_object))

        # --- Custom incoming = only pre-validated POs ---
        po_lines = self.env['purchase.order.line'].search(domain=domain).filtered(lambda pol: pol.product_qty - pol.qty_received != 0)
        validated_po = po_lines.mapped('order_id.id')

        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_form_action")
        action['domain'] = [('id', 'in', validated_po)]
        action['context'] = {'create':False}
        return action
    
    def action_open_validate_outgoing_so(self):
        dt_object = False
        if self.env.context.get('to_date'):
            dt_object = fields.Datetime.to_datetime(self.env.context.get('to_date'))
        
        order_domain = [
            ('product_id', '=', self.id),
            ('order_state', 'not in', ('cancel')), 
            ('is_pre_validate','=',True),
        ]

        if dt_object:
            order_domain.append(('create_date','<=', dt_object))
        
        # --- Custom outgoing = only pre-validated SOs ---
        so_bom_lines = self.env['sale.order.bom.component.line'].search(domain=order_domain).filtered(lambda bl: bl.product_qty - bl.qty_delivered != 0)
        validated_so = so_bom_lines.mapped('order_line_id.order_id.id')

        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        action['domain'] = [('id', 'in', validated_so)]
        action['context'] = {'create':False}
        return action
                                    
    def _compute_cbm_uom_name(self):
        for package_type in self:
            package_type.cbm_uom_name = self.env['product.template']._get_volume_uom_name_from_ir_config_parameter()

    @api.depends('package_depth', 'package_width', 'package_height')
    def compute_package_cbm(self):
        for record in self:
            record.package_cbm = (record.package_depth * record.package_width * record.package_height) / 1000000000 # Conversion mm3 to m3.

    @api.depends('package_cbm', 'quantities_per_package')
    def compute_product_cbm(self):
        for record in self:
            if record.quantities_per_package:
                record.product_cbm = record.package_cbm / record.quantities_per_package
                record.volume = record.package_cbm / record.quantities_per_package
            else:
                record.product_cbm = 0.0
                record.volume = 0.0

    @api.depends('package_weight', 'quantities_per_package')
    def compute_product_weight(self):
        for record in self:
            if record.quantities_per_package:
                record.product_weight = record.package_weight / record.quantities_per_package
            else:
                record.product_weight = 0.0

    @api.depends('product_tmpl_id.custom_product_type')
    def compute_custom_variant_type(self):
        for record in self:
            record.custom_variant_type = record.product_tmpl_id.custom_product_type

    def view_valuation_adjustments(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Landed Cost Adjustments"),
            'res_model': 'stock.valuation.adjustment.lines',
            'view_id': self.env.ref(
                'burgtec_warehouse_customization.burgtec_warehouse_view_stock_valuation_adjustment_lines_list').id,
            'view_mode': 'list',
            'domain': [('product_id', '=', self.id)],
        }

    @api.depends('stock_valuation_adjustment_line_ids', 'stock_valuation_adjustment_line_ids.additional_landed_cost', )
    def compute_average_landed_cost(self):
        for record in self:
            stock_valuation_adjustments = record.stock_valuation_adjustment_line_ids
            landed_costs = stock_valuation_adjustments.mapped('cost_id').sorted('id')
            total_additional_landed_costs = 0
            if not stock_valuation_adjustments:
                record.average_landed_cost = 0
                continue
            if stock_valuation_adjustments:
                total_additional_landed_costs = sum(stock_valuation_adjustments.mapped('additional_landed_cost_per_unit'))
                # Instead of dividing by lines. More than one lines can belong to one landed cost record. So for average it is best to devide by landed cost's record number.
                record.average_landed_cost = total_additional_landed_costs / len(landed_costs) 

    @api.depends('stock_valuation_adjustment_line_ids', 'stock_valuation_adjustment_line_ids.additional_landed_cost')
    def compute_landed_costs(self):
        for record in self:
            adjustment_lines = record.stock_valuation_adjustment_line_ids
            landed_costs = adjustment_lines.mapped('cost_id').sorted('id')
            total_amounts = []
            latest_cost_lines = False
            cost_lines = False
            if not landed_costs:
                record.maximum_landed_cost = 0
                record.minimum_landed_cost = 0
                record.latest_landed_cost = 0
                continue
            if landed_costs:
                # Sorted the last record will be the latest record created for Landed Cost.
                # latest_cost_lines = adjustment_lines.filtered(lambda lc:lc.cost_id.id == landed_costs[-1].id)

                # For Minimum, Maximum and Latest Landed Costs.
                for landed_cost in landed_costs:
                    cost_lines = adjustment_lines.filtered(lambda lc:lc.cost_id.id == landed_cost.id)
                    total_amounts.append(sum(cost_lines.mapped('additional_landed_cost_per_unit')))

                record.maximum_landed_cost = max(total_amounts)
                record.minimum_landed_cost = min(total_amounts)
                record.latest_landed_cost = total_amounts[-1] # last is for the latest lc.






    @api.depends('standard_price', 'standard_freight_cost_per_cbm', 'standard_exchange_rate', 'standard_duty_or_tax',
                 'product_cbm')
    def compute_manual_landed_cost(self):
        for record in self:
            cost_of_standard_exchange_rate = (record.standard_price * record.standard_exchange_rate) / 100
            cost_of_standard_duty_or_tax = (record.standard_price * record.standard_duty_or_tax) / 100
            standard_freight_cost_per_cbm = record.standard_freight_cost_per_cbm
            product_cbm = record.product_cbm
            record.manual_landed_cost = cost_of_standard_exchange_rate + cost_of_standard_duty_or_tax + (
                    standard_freight_cost_per_cbm * product_cbm)

    @api.depends('bom_ids','bom_ids.bom_line_ids','bom_ids.bom_line_ids.product_id','bom_ids.bom_line_ids.product_id.manual_landed_cost','bom_ids.bom_line_ids.product_id.average_landed_cost')
    def compute_product_landed_costs(self):
        for record in self:
            if record.custom_variant_type == 'product' and record.bom_ids:
                manual_landed_cost_totals = []
                average_landed_cost_totals = []
                for bom in record.bom_ids:
                    manual_landed_cost = sum(
                        line.product_id.manual_landed_cost
                        for line in bom.bom_line_ids
                        if line.product_id
                    )
                    manual_landed_cost_totals.append(manual_landed_cost)
                    average_landed_cost = sum(
                        line.product_id.average_landed_cost
                        for line in bom.bom_line_ids
                        if line.product_id
                    )
                    average_landed_cost_totals.append(average_landed_cost)

                record.product_manual_landed_cost = max(manual_landed_cost_totals, default=0.0)
                record.product_average_landed_cost = max(average_landed_cost_totals, default=0.0)
            else:
                record.product_manual_landed_cost = 0.0
                record.product_average_landed_cost = 0.0
    
    @api.depends('product_tmpl_id.vendor_currency_id')
    def compute_vendor_currency_id(self):
        for record in self:
            record.vendor_currency_id = record.product_tmpl_id.vendor_currency_id
    
    @api.depends('product_tmpl_id.supplier_code')
    def compute_supplier_code(self):
        for record in self:
            record.supplier_code = record.product_tmpl_id.supplier_code
    
    @api.depends('seller_ids','seller_ids.partner_id','seller_ids.partner_id.standard_freight_cost_per_cbm','seller_ids.partner_id.standard_exchange_rate','seller_ids.partner_id.standard_duty_or_tax')
    def compute_standard_manual_landed_cost_from_supplier(self):
        for record in self:
            sellers = record.seller_ids
            vendor = False
            if not sellers:
                record.standard_freight_cost_per_cbm = 0.0
                record.standard_exchange_rate = 0.0
                record.standard_duty_or_tax = 0.0
                continue
            if sellers:
                # First Vendor
                vendor = sellers[0].partner_id
                record.standard_freight_cost_per_cbm = vendor.standard_freight_cost_per_cbm
                record.standard_exchange_rate = vendor.standard_exchange_rate
                record.standard_duty_or_tax = vendor.standard_duty_or_tax
    


    def compute_warning_html(self):
        for record in self:
            zero_fields = []

            if record.custom_variant_type == 'product':
                warning_html = False
                record.warning_html = warning_html
                continue

            if record.product_weight == 0.0:
                zero_fields.append("Product Weight")

            if record.product_cbm == 0.0:
                zero_fields.append("Product CBM")

            if record.package_cbm == 0.0:
                zero_fields.append("Package CBM")

            if zero_fields:
                fields = ", ".join(zero_fields)

                warning_html = Markup(f'''
                    <div class="alert alert-warning" role="alert">
                        Following <strong>{fields}</strong> are <strong>ZERO</strong>.
                    </div>
                ''')
            else:
                warning_html = False

            record.warning_html = warning_html
    
    def set_minimum_reorder_qty(self):
        for record in self:
            record.minimum_reorder_qty = record.qty_available
    
    def _compute_display_name(self):
        for record in self:
            if record.env.context.get('code_first'):
                record.display_name = f"{record.default_code} {record.name}"
            else:
                return super()._compute_display_name()
            




