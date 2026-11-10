import json
import logging
from odoo import http
from odoo.http import request
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class BurgtecPoDateSync(http.Controller):

    @http.route('/warehouse/update_quotation_date', type='http', auth='public', methods=['POST'], csrf=False)
    def date_update_from_burgtec_po_to_warehouse_quotation(self, webhook_auth_token=None, **kw):
        icp = request.env['ir.config_parameter'].sudo()
        TOKEN = icp.get_param('burgtec.sync_token') or ''
        if not TOKEN or webhook_auth_token != TOKEN:
            return request.make_response('forbidden', status=403)
        try:
            data = json.loads(request.httprequest.get_data() or b'{}')
            so_id = data.get('sale_order_id')
            if so_id:
                order = request.env['sale.order'].sudo().browse(int(so_id)).exists()
                if order:
                    order.write({
                        'po_dispatch_date': data.get('hubspot_dispatch_date') or False,
                        'po_date_planned': data.get('date_planned') or False,
                    })
        except Exception as e:
            _logger.warning("Quotation Date Update Failed: %s", e)
        return request.make_response('ok')
