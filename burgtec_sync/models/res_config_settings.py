from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    burgtec_sync_url = fields.Char(
        string="Burgtec URL",
        config_parameter='burgtec.sync_url',
    )
    burgtec_sync_db = fields.Char(
        string="Burgtec Database",
        config_parameter='burgtec.sync_db',
    )
    burgtec_sync_token = fields.Char(
        string="Burgtec Token",
        config_parameter='burgtec.sync_token',
    )
