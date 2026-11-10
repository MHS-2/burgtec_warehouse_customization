/** @odoo-module **/
import { Component, useState } from '@odoo/owl';
import { Dialog } from "@web/core/dialog/dialog";

export class RelatedSaleOrdersDialog extends Component {
    static props = { 
        orderData : Array,
        close: Function,

        }
    static components = { Dialog };
    static template = "burgtec_warehouse_customization.relatedSaleOrders";

    setup() {

    }
}
//#endregion
