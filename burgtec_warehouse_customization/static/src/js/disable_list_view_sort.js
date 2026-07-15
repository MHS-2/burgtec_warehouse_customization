import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, {
        onClickSortColumn(column) {
            if (this.props.archInfo.className == 'no_reorder'){
                this.preventReorder = true;
            }
        return super.onClickSortColumn(column);
    }
});