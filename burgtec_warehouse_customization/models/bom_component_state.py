from odoo import models, fields,api, _

class BomComponentState(models.Model):
    _name= "bom.component.state"
    _description = "Replacing Global Dict"

    component_state = fields.Json(string='Component state', default=lambda self: {})
    bom_component_line_id = fields.Many2one('sale.order.bom.component.line', ondelete='cascade')
