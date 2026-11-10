import { ListController } from '@web/views/list/list_controller';
import { StockReportDashboard } from '@burgtec_warehouse_customization/components/stock_report_dashboard/stock_report_dashboard';
import { useState, onPatched,} from "@odoo/owl";


export class StockReportListController extends ListController {
    static template = "burgtec_warehouse_customization.StockReportListView";
    static components = {
        ...ListController.components,
        StockReportDashboard,
    };

    setup() {
        super.setup();
        this.state = useState({ refreshKey: 0 });
        this._lastListSignature = null;

        onPatched(() => {
            const records = this.env.model.root.records || [];
            const signature = records.map(r => r.id).join(',');

            if (signature !== this._lastListSignature) {
                this._lastListSignature = signature;
                this.state.refreshKey++;
            }
    });
}
}