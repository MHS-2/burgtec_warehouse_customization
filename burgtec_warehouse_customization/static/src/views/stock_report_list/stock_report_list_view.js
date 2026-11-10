import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';
import { StockReportListController } from './stock_report_list_controller';

export const StockReportListView = {
    ...listView,
    Controller: StockReportListController,
    searchview_hidden: true,
};

registry.category('views').add('custom_stock_report_list_view', StockReportListView);