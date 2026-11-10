from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ShipmentRegister(models.Model):
    _name = 'shipment.register'
    _description = 'Shipment Register'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_departure desc, id desc'
    _check_company_auto = True

    # --- Identification ---
    name = fields.Char(
        string='Shipment Reference', required=True, copy=False, readonly=True,
        default='New', index='trigram', tracking=True,
    )
    shipment_status = fields.Selection([
        ("for_booking", "For Booking"),
        ("booking_confirmed", "Booking Confirmed Awaiting Loading"),
        ("loaded", "Loaded Awaiting Departure"),
        ("in_transit", "In Transit"),
        ("arrived_pod", "Arrived at Port of Destination"),
        ("delivered", "Delivered")],
        string="Shipment Status",
        tracking=True,
        copy=False,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company', index=True, default=lambda self: self.env.company,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('booked', 'Booked'),
        ('loading', 'Loading'),
        ('in_transit', 'In Transit'),
        ('arrived_pod', 'Arrived at POD'),
        ('delivered', 'Delivered'),
        ('cancel', 'Cancelled'),
    ], string='Shipment Status', default='draft', required=True, tracking=True, copy=False)

    # --- Container / carrier ---
    container_size = fields.Selection([
        ('40', '40"'),
        ('20', '20"'),
        ('lcl', 'LCL'),
    ], string='Container Size', tracking=True)
    container_number = fields.Char(string='Container Number', tracking=True)
    shipment_mode = fields.Selection([
        ('sea_fcl', 'Sea FCL'),
        ('sea_lcl', 'Sea LCL'),
        ('air', 'Air'),
        ('local', 'Local'),
    ], string='Mode of Shipment', default='sea_fcl', tracking=True)
    fumigation_required = fields.Boolean(string='Fumigation Required', tracking=True)
    freight_forwarder = fields.Char(string='Freight Forwarder', tracking=True)
    carrier_company = fields.Char(string='Carrier Company', tracking=True)
    carrier_route_ref = fields.Char(string='Carrier Route Reference')
    tracking_url = fields.Char(string='Tracking URL')

    # --- Locations ---
    loading_location_ids = fields.Many2many(
        'res.partner', 'shipment_register_loading_partner_rel', 'shipment_id', 'partner_id',
        string='Supplier Loading Location/s', check_company=True,
    )
    port_departure = fields.Char(string='Port of Departure', tracking=True)
    destination = fields.Char(string='Destination (POD)', tracking=True)
    delivery_address_id = fields.Many2one(
        'res.partner', string='Final Delivery Address', check_company=True)

    # --- Dates (manual) ---
    date_loading = fields.Datetime(string='Date of Loading', tracking=True)
    date_loading_cutoff = fields.Datetime(string='Loading Cut-off Date', tracking=True)
    date_departure = fields.Datetime(string='Departure Date', tracking=True)
    date_eta_pod = fields.Date(string='Date ETA POD (Manual)', tracking=True)
    date_eta_delivered = fields.Datetime(string='Date ETA Delivered', tracking=True)

    # --- Dates (auto / imported) ---
    date_eta_pod_auto = fields.Date(
        string='Date ETA POD (Auto)', tracking=True,
        help='Updated from the daily carrier CSV import.',
    )
    eta_pod_diff_days = fields.Integer(
        string='ETA POD Difference (Days)', compute='_compute_eta_pod_diff_days', store=True,
        help='Auto minus Manual. Positive = later than planned.',
    )

    status_comments = fields.Text(string='Shipment Status Comments')

    # --- Purchase orders / totals ---
    shipment_line_ids = fields.One2many('shipment.register.line', 'shipment_id', string='Purchase Orders')
    purchase_order_count = fields.Integer(compute='_compute_totals', store=True, string='# POs')
    total_weight = fields.Float(
        string='Total Shipment Weight', digits=(16, 6), compute='_compute_totals', store=True,
    )
    total_cbm = fields.Float(
        string='Total Shipment CBM', digits=(16, 6), compute='_compute_totals', store=True,
    )

    @api.depends('shipment_line_ids.total_order_cbm', 'shipment_line_ids.total_order_weight')
    def _compute_totals(self):
        for rec in self:
            pos = rec.shipment_line_ids
            rec.purchase_order_count = len(pos)
            rec.total_weight = sum(pos.mapped('total_order_weight'))
            rec.total_cbm = sum(pos.mapped('total_order_cbm'))

    @api.depends('date_eta_pod', 'date_eta_pod_auto')
    def _compute_eta_pod_diff_days(self):
        for rec in self:
            if rec.date_eta_pod and rec.date_eta_pod_auto:
                rec.eta_pod_diff_days = (rec.date_eta_pod_auto - rec.date_eta_pod).days
            else:
                rec.eta_pod_diff_days = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('shipment.register') or 'New'
        return super().create(vals_list)

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id},
        }

    def write(self, vals):
        res = super().write(vals)
        if self.date_eta_delivered:
            for line in self.shipment_line_ids:
                line.purchase_order_id.date_planned = self.date_eta_delivered
        return res


class ShipmentRegisterLine(models.Model):
    _name = 'shipment.register.line'
    _description = 'Shipment Register Line'

    shipment_id = fields.Many2one(
        'shipment.register',
        string='Shipment',
        index='btree_not_null',
        ondelete='cascade',
        copy=False,
        tracking=True,
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
    )

    name = fields.Char(
        related='purchase_order_id.name',
        string='Order Reference',
        store=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        related='purchase_order_id.partner_id',
        string='Vendor',
        store=True,
    )

    date_planned = fields.Datetime(
        related='purchase_order_id.date_planned',
        string='Scheduled Date',
        store=True,
    )

    total_order_weight = fields.Float(
        related='purchase_order_id.total_order_weight',
        string='Total Order Weight',
        store=True,
    )

    total_order_cbm = fields.Float(
        related='purchase_order_id.total_order_cbm',
        string='Total Order CBM',
        store=True,
    )

    amount_total = fields.Monetary(
        related='purchase_order_id.amount_total',
        string='Total',
        store=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='purchase_order_id.currency_id',
        string='Currency',
        store=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='purchase_order_id.company_id',
        string='Company',
        store=True,
    )

    state = fields.Selection(
        related='purchase_order_id.state',
        string='Status',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        res = super(ShipmentRegisterLine, self).create(vals_list)
        for rec in res:
            if rec.env.context.get('shipment'):
                rec.purchase_order_id.shipment_id = rec.shipment_id.id
        return res

    def unlink(self):
        for rec in self:
            rec.purchase_order_id.shipment_id = False
        res = super(ShipmentRegisterLine, self).unlink()
        return res

    @api.constrains('purchase_order_id')
    def _purchase_order_id(self):
        for line in self:
            duplicate_pos = self.env['shipment.register.line'].search([
                ('purchase_order_id', '=', line.purchase_order_id.id),
                ('id', '!=', line.id),
                ('shipment_id', '=', self.shipment_id.id),
            ])
            if duplicate_pos:
                raise ValidationError('You cannot add same purchase order,on a different line')
