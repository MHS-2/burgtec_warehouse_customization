# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_unvalidated = fields.Boolean(defaukt=False)

    # is_pre_validate = fields.Boolean(default=False)
    # validate_state = fields.Selection([
    #         ('pre_validate','Pre-Validated'),
    #         ('un_validate','Un-Validated')
    #     ],default=False)

    # def set_pre_validate(self):
    #     for record in self:
    #         record.write({
    #             'validate_state':'pre_validate',
    #             'is_pre_validate':True,
    #         })
        
    # def set_unvalidate(self):
    #     for record in self:
    #         record.write({
    #             'validate_state':'un_validate',
    #             'is_pre_validate':False,
    #         })
    
    # def button_validate(self):
    #     for record in self:
    #         if not self.env.user.has_group('sales_team.group_sale_manager'):
    #             raise UserError(_("Only Sales Administrator can Validate the pickings!."))
    #         if not record.is_pre_validate:
    #             raise UserError(_('You must set picking to pre-validate, before validating!'))
    #     picking = super().button_validate()
    #     return picking
    
    def _pre_action_done_hook(self):
        for picking in self:
            has_quantity = False
            has_pick = False
            for move in picking.move_ids:
                if move.quantity:
                    has_quantity = True
                if move.location_dest_usage == 'inventory':
                    continue
                if move.picked:
                    has_pick = True
                if has_quantity and has_pick:
                    break
            if has_quantity and not has_pick:
                picking.move_ids.picked = True
        if not self.env.context.get('skip_backorder'):
            pickings_to_backorder = self._check_backorder()
            if pickings_to_backorder:
                if not self.env.user.has_group('purchase.group_purchase_manager'):
                    raise UserError(_('You are not allowed to validate partial quantities !.'))
                return pickings_to_backorder._action_generate_backorder_wizard(show_transfers=self._should_show_transfers())
        return True

