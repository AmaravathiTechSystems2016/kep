/** @odoo-module **/
import { registry } from "@web/core/registry";

// The HR dashboard loads Chart.js from a CDN, which the offline test browser cannot reach.
// This stub exists only in the test bundle so the HR half of the page can mount.
if (!window.Chart) {
    window.Chart = class {
        constructor() {}
        destroy() {}
        update() {}
    };
}

async function waitFor(check, message, timeout = 8000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
        if (check()) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("CRM dashboard tour: " + message);
}

function assert(condition, message) {
    if (!condition) {
        throw new Error("CRM dashboard tour: " + message);
    }
}

const checkDashboard = [
    {
        content: "KPI cards are rendered",
        trigger: ".dcd_root .dcd_kpi",
        run: () => {
            const n = document.querySelectorAll(".dcd_kpi").length;
            assert(n === 12, `expected 12 KPI cards, got ${n}`);
        },
    },
    {
        content: "Pipeline shows every stage and Lost",
        trigger: ".dcd_stage_row:contains('Lost')",
        run: () => {
            const text = [...document.querySelectorAll(".dcd_stage_row .dcd_bar_name")].map((e) => e.textContent.trim());
            const expected = ["Inquiry", "Scheme / Tech Offer", "Commercial Offer", "Discussion", "PO", "Won", "Lost"];
            assert(JSON.stringify(text) === JSON.stringify(expected), "stages were " + JSON.stringify(text));
        },
    },
    {
        content: "Trend chart has bars, effluent table has MEE, owner and engineer tables are filled",
        trigger: ".dcd_heat td:contains('MEE')",
        run: () => {
            assert(document.querySelectorAll(".dcd_svg rect").length > 0, "no trend bars");
            assert(document.querySelectorAll(".dcd_donut circle").length > 0, "no donut");
            assert(document.querySelectorAll(".dcd_table")[0].querySelectorAll("tbody tr").length >= 1, "owner table empty");
            assert(document.querySelector(".dcd_insights li"), "no insights");
        },
    },
    {
        content: "Change the system filter",
        trigger: ".dcd_filters select:eq(3)",
        run: () => {
            const select = document.querySelectorAll(".dcd_filters select")[3];
            const option = [...select.options].find((o) => o.textContent.trim() === "ZLD");
            assert(option, "ZLD option missing");
            select.value = option.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
        },
    },
    {
        content: "Only ZLD remains in the effluent table",
        trigger: ".dcd_heat",
        run: async () => {
            await waitFor(
                () => document.querySelectorAll(".dcd_heat tbody tr").length === 1,
                "expected exactly one system row after filtering by ZLD"
            );
            const row = document.querySelector(".dcd_heat tbody tr").textContent;
            assert(row.includes("ZLD") && !row.includes("MEE"), "remaining row is not ZLD: " + row);
        },
    },
    {
        content: "Reset filters",
        trigger: ".dcd_filters button[title='Reset filters']",
        run: "click",
    },
    {
        content: "Drill down: click the Won KPI",
        trigger: ".dcd_kpi.dcd_click:contains('Won')",
        run: "click",
    },
    {
        content: "A lead list opens",
        trigger: ".o_list_view .o_data_row",
    },
];

registry.category("web_tour.tours").add("dotbd_crm_dashboard_standalone", {
    steps: () => checkDashboard,
});

registry.category("web_tour.tours").add("dotbd_crm_dashboard_tab", {
    steps: () => [
        {
            content: "HR dashboard is shown first with a CRM tab",
            trigger: ".dotbd_dash_tab:contains('CRM')",
            run: "click",
        },
        ...checkDashboard.slice(0, 3),
        {
            content: "Back to the HR tab",
            trigger: ".dotbd_dash_tab:contains('HR')",
            run: "click",
        },
        {
            content: "HR dashboard is visible again and the CRM one hidden",
            trigger: ".o_hr_dashboard:not(.d-none)",
            run: () => {
                assert(!document.querySelector(".dcd_root"), "CRM panel still mounted on the HR tab");
            },
        },
    ],
});
