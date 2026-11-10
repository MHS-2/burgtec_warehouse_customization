import { user } from '@web/core/user';
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onWillUpdateProps,} from "@odoo/owl";

export class StockReportDashboard extends Component {
    static template = "burgtec_warehouse_customization.StockReportDashboard";
    static props = ['refreshKey'];
    
    setup() {
        this.action = useService('action');
        this.orm = useService('orm');
        this.state = useState({
            dashboardValues: null,
        });

        onWillStart(this.onWillStart);

        onWillUpdateProps(async () => {
            this._fetchData();
        });

    }

    async onWillStart() {
        await this._fetchData();
    }

    async _fetchData() {
        const records = this?.env?.model?.root?.records || [];
        const result = records.map(record => ({
            product_id: record.data.product_id?.id || false,
            incoming_qty: record.data.custom_incoming_qty || 0,
            outgoing_qty: record.data.custom_outgoing_qty || 0,
            forecasted_qty: record.data.custom_forecasted || 0,
            status: record.data.status || '',
        }));

        const idList = records.map(rec => rec.data.product_id.id);
        this.state.dashboardValues = await this.orm.call(
            'stock.forecast.alert.report',
            'retrieve_dashboard',
            [],
            { context: user.context, records: idList, result: result},
        );
    }

}