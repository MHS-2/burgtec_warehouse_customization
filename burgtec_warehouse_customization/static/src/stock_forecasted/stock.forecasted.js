/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { StockForecasted } from "@stock/stock_forecasted/stock_forecasted";

patch(StockForecasted.prototype, {
    
    get graphDomain() {
        const domain = [
            ["state", "=", "forecast"],
            ["warehouse_id", "=", this.context.warehouse_id],
        ];
        if (this.resModel === "product.template") {
            domain.push(["product_tmpl_id", "=", this.productId]);
        } else if (this.resModel === "product.product") {
            domain.push(["product_id", "=", this.productId]);
        }
        else if (this.resModel === "stock.forecast.alert.report") {
            domain.push(["product_id", "=", this.productId]);
        }
        return domain;
    }
});