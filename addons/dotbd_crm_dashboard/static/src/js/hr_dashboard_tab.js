/** @odoo-module **/
import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { HrDashboard } from "@hrms_dashboard/js/dashboard";
import { CrmDashboard } from "./crm_dashboard";

// Adds a CRM tab to the existing Dashboard app (hrms_dashboard).
HrDashboard.components = { ...(HrDashboard.components || {}), CrmDashboard };

patch(HrDashboard.prototype, {
    setup() {
        super.setup(...arguments);
        this.dash = useState({ view: "hr", canCrm: false });
        onWillStart(async () => {
            this.dash.canCrm = await user.hasGroup("sales_team.group_sale_salesman");
        });
    },
    showDashboardView(view) {
        this.dash.view = view;
    },
});
