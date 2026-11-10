/** @odoo-module **/
import { Component, } from '@odoo/owl';
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { useService } from "@web/core/utils/hooks";
import { RelatedSaleOrdersDialog } from "@burgtec_warehouse_customization/related_sales_order_dialog/related_sales_order_dialog";

class RelatedSaleOrdersButton extends Component {
    static props = {
        ...standardWidgetProps,
    };
    static template = "burgtec_warehouse_customization.relatedSaleOrdersButton";

    setup() {
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    }

    async openRelatedOrdersDialog(orderData){
        this.dialog.add(RelatedSaleOrdersDialog,  {
              orderData : orderData,
              close: Function,
            });
    }

    async ormRelatedOrders(productId) {
      const res = await this.orm.call("stock.forecast.alert.report", "fetch_related_orders", [Number(productId)]);
      return res
    }

    async onOpenDialog() {
        const productId = this.props?.record?.data?.product_id?.id
        if (!productId){
            const relatedOrdersData = []
            await this.openRelatedOrdersDialog(relatedOrdersData);
        }
        else if (productId){
            const relatedOrdersData = await this.ormRelatedOrders(productId);
            await this.openRelatedOrdersDialog(relatedOrdersData);
        }
    }

}

const relatedSaleOrdersButton = {
  component: RelatedSaleOrdersButton,
};

registry.category("view_widgets").add("related_so_btn", relatedSaleOrdersButton);