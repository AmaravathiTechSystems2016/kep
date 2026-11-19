/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const PALETTE = ["#2f6fed", "#12b886", "#f59f00", "#e8590c", "#7048e8", "#d6336c", "#0ca678", "#1098ad", "#868e96", "#5c7cfa"];
const STAGE_COLORS = ["#4c6ef5", "#3b8bd9", "#22a6b3", "#12b886", "#f59f00", "#2f9e44"];
const EFFLUENT_COLUMNS = [
    { key: "ph_value", label: "pH", decimals: 2 },
    { key: "tds", label: "TDS", decimals: 0 },
    { key: "cod", label: "COD", decimals: 0 },
    { key: "bod", label: "BOD", decimals: 0 },
    { key: "tss", label: "TSS", decimals: 0 },
    { key: "hardness", label: "Hardness", decimals: 0 },
    { key: "oil_grease", label: "Oil & Grease", decimals: 0 },
    { key: "silica", label: "Silica", decimals: 0 },
];

export class CrmDashboard extends Component {
    static template = "dotbd_crm_dashboard.CrmDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.effluentColumns = EFFLUENT_COLUMNS;
        this.state = useState({
            loading: true,
            data: null,
            error: false,
            filters: { period: "12m", owner: "", worker: "", system: "", model: "" },
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        const f = this.state.filters;
        try {
            this.state.data = await this.orm.call("dotbd.crm.dashboard", "get_data", [], {
                period: f.period,
                owner_id: f.owner ? parseInt(f.owner) : false,
                worked_by_id: f.worker ? parseInt(f.worker) : false,
                system_id: f.system ? parseInt(f.system) : false,
                model_id: f.model ? parseInt(f.model) : false,
            });
        } catch (error) {
            this.state.error = true;
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    onFilter(name, ev) {
        this.state.filters[name] = ev.target.value;
        return this.load();
    }

    resetFilters() {
        Object.assign(this.state.filters, { period: "12m", owner: "", worker: "", system: "", model: "" });
        return this.load();
    }

    // ---------- formatting ----------
    fmtInt(v) {
        return v === null || v === undefined || v === false ? "–" : new Intl.NumberFormat("en-IN").format(v);
    }

    fmtMoney(v) {
        if (v === null || v === undefined || v === false) {
            return "–";
        }
        const { symbol, name } = this.state.data.currency;
        const abs = Math.abs(v);
        let text;
        if (name === "INR") {
            text = abs >= 1e7 ? (v / 1e7).toFixed(2) + " Cr" : abs >= 1e5 ? (v / 1e5).toFixed(2) + " L"
                : abs >= 1e3 ? (v / 1e3).toFixed(1) + " K" : v.toFixed(0);
        } else {
            text = abs >= 1e6 ? (v / 1e6).toFixed(2) + " M" : abs >= 1e3 ? (v / 1e3).toFixed(1) + " K" : v.toFixed(0);
        }
        return `${symbol} ${text}`;
    }

    fmtKpi(kpi) {
        if (kpi.value === null || kpi.value === undefined) {
            return "–";
        }
        switch (kpi.fmt) {
            case "money": return this.fmtMoney(kpi.value);
            case "pct": return kpi.value + "%";
            case "days": return kpi.value + " d";
            default: return this.fmtInt(kpi.value);
        }
    }

    fmtDays(v) {
        return v === null || v === undefined ? "–" : v + " d";
    }

    fmtPct(v) {
        return v === null || v === undefined ? "–" : v + "%";
    }

    // ---------- drill-down ----------
    openLeads(name, domain) {
        if (!domain) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: "crm.lead",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain: domain,
            context: { active_test: false },
        });
    }

    // ---------- chart data ----------
    barItems(rows, key, { moneyKey = false, color = null } = {}) {
        const max = Math.max(1, ...rows.map((r) => r[key] || 0));
        return rows.map((r, i) => ({
            id: r.id,
            name: r.name,
            pct: Math.max(r[key] ? 3 : 0, ((r[key] || 0) / max) * 100),
            label: moneyKey ? this.fmtMoney(r[key]) : this.fmtInt(r[key]),
            color: color || PALETTE[i % PALETTE.length],
            domain: r.domain,
        }));
    }

    get stageBars() {
        const data = this.state.data;
        const rows = [...data.stages, { ...data.lost, is_lost: true }];
        const max = Math.max(1, ...rows.map((r) => r.count));
        const first = data.stages.length ? data.stages[0].reach : 0;
        return rows.map((r, i) => ({
            ...r,
            pct: Math.max(r.count ? 4 : 0, (r.count / max) * 100),
            color: r.is_lost ? "#e03131" : STAGE_COLORS[i % STAGE_COLORS.length],
            reachPct: !r.is_lost && first ? Math.round((100 * r.reach) / first) : null,
        }));
    }

    get donutModel() {
        return this.buildDonut(this.state.data.by_model, "count");
    }

    get donutSource() {
        return this.buildDonut(this.state.data.by_source, "count");
    }

    buildDonut(rows, key) {
        const total = rows.reduce((s, r) => s + (r[key] || 0), 0);
        let offset = 25;
        const segments = rows.filter((r) => r[key]).map((r, i) => {
            const pct = (100 * r[key]) / total;
            const seg = {
                name: r.name, count: r[key], pct: pct.toFixed(0), domain: r.domain,
                color: PALETTE[i % PALETTE.length], dash: `${pct} ${100 - pct}`, offset,
            };
            offset -= pct;
            return seg;
        });
        return { total, segments };
    }

    get trendChart() {
        const trend = this.state.data.trend;
        const W = 760, H = 230, left = 34, bottom = 28, top = 12;
        const max = Math.max(1, ...trend.map((t) => Math.max(t.new, t.won, t.lost)));
        const niceMax = Math.max(4, Math.ceil(max / 4) * 4);
        const plotH = H - bottom - top;
        const groupW = (W - left) / trend.length;
        const barW = Math.min(14, groupW / 4);
        const series = [["new", "#4c6ef5", "Inquiries"], ["won", "#2f9e44", "Won"], ["lost", "#e03131", "Lost"]];
        const bars = [], labels = [];
        trend.forEach((t, i) => {
            const gx = left + i * groupW + groupW / 2 - (barW * 3 + 4) / 2;
            series.forEach(([k, color, name], j) => {
                const h = (t[k] / niceMax) * plotH;
                bars.push({
                    x: gx + j * (barW + 2), y: top + plotH - h, w: barW, h: Math.max(h, t[k] ? 1.5 : 0),
                    color, title: `${t.label}: ${t[k]} ${name}`,
                });
            });
            labels.push({ x: left + i * groupW + groupW / 2, text: t.label });
        });
        const grid = [0, 1, 2, 3, 4].map((g) => ({
            y: top + plotH - (g / 4) * plotH, text: Math.round((niceMax * g) / 4),
        }));
        return { W, H, left, bars, labels, grid, legend: series.map(([, c, n]) => ({ c, n })) };
    }

    get turnaroundChart() {
        const trend = this.state.data.trend;
        const W = 760, H = 150, left = 34, bottom = 24, top = 12;
        const vals = trend.map((t) => t.turnaround);
        const max = Math.max(5, ...vals.filter((v) => v !== null));
        const plotH = H - bottom - top;
        const step = (W - left) / trend.length;
        const points = trend.map((t, i) => ({
            x: left + i * step + step / 2,
            y: t.turnaround === null ? null : top + plotH - (t.turnaround / max) * plotH,
            v: t.turnaround, label: t.label,
        }));
        const segments = [];
        let current = [];
        points.forEach((p) => {
            if (p.y === null) {
                if (current.length) { segments.push(current); current = []; }
            } else {
                current.push(p);
            }
        });
        if (current.length) { segments.push(current); }
        return {
            W, H, left, points: points.filter((p) => p.y !== null),
            paths: segments.map((s) => s.map((p) => `${p.x},${p.y}`).join(" ")),
            top: Math.ceil(max), bottomY: top + plotH, topY: top,
            labels: points.filter((_, i) => i % 2 === 0).map((p) => ({ x: p.x, text: p.label })),
        };
    }

    heat(value, key) {
        if (!value) {
            return "";
        }
        const max = Math.max(...this.state.data.effluent.map((r) => r[key] || 0));
        const alpha = max ? (value / max) * 0.4 : 0;
        return `background: rgba(224, 49, 49, ${alpha.toFixed(2)});`;
    }

    get insights() {
        const d = this.state.data;
        const out = [];
        const k = Object.fromEntries(d.kpis.map((x) => [x.key, x]));
        const open = d.stages.filter((s) => !s.is_won && s.count);
        const slow = [...open].filter((s) => s.avg_age).sort((a, b) => b.avg_age - a.avg_age)[0];
        if (slow) {
            out.push({ icon: "fa-hourglass-half", tone: "warn",
                text: _t("Slowest stage: %(stage)s, open leads there have waited %(days)s days on average.", { stage: slow.name, days: slow.avg_age }) });
        }
        const big = [...open].sort((a, b) => b.value - a.value)[0];
        if (big && big.value) {
            out.push({ icon: "fa-money", tone: "info",
                text: _t("Most pipeline value sits in %(stage)s: %(value)s across %(n)s leads.", { stage: big.name, value: this.fmtMoney(big.value), n: big.count }) });
        }
        if (k.win_rate.value !== null) {
            out.push({ icon: "fa-trophy", tone: k.win_rate.value >= 30 ? "good" : "warn",
                text: _t("Win rate is %(rate)s (%(won)s won, %(lost)s lost).", { rate: k.win_rate.value + "%", won: k.won.value, lost: k.lost.value }) });
        }
        const reason = d.lost_reasons[0];
        if (reason && d.lost.count) {
            out.push({ icon: "fa-thumbs-down", tone: "bad",
                text: _t("Top loss reason: %(reason)s (%(n)s of %(total)s lost leads).", { reason: reason.name, n: reason.count, total: d.lost.count }) });
        }
        if (k.pending_offer.value) {
            out.push({ icon: "fa-file-text-o", tone: "warn",
                text: _t("%(n)s open leads still have no submitted offer date.", { n: k.pending_offer.value }) });
        }
        if (k.overdue.value) {
            out.push({ icon: "fa-calendar-times-o", tone: "bad",
                text: _t("%(n)s open leads are past their expected closing date.", { n: k.overdue.value }) });
        }
        if (k.stale.value) {
            out.push({ icon: "fa-bed", tone: "warn",
                text: _t("%(n)s open leads have not moved stage for over 30 days.", { n: k.stale.value }) });
        }
        const owners = d.by_owner.filter((o) => o.id && o.won_value);
        if (owners.length) {
            const top = [...owners].sort((a, b) => b.won_value - a.won_value)[0];
            out.push({ icon: "fa-user", tone: "good",
                text: _t("Top lead owner by won value: %(name)s with %(value)s.", { name: top.name, value: this.fmtMoney(top.won_value) }) });
        }
        const workers = d.by_worker.filter((w) => w.id && w.avg_turnaround !== null);
        if (workers.length > 1) {
            const slowest = [...workers].sort((a, b) => b.avg_turnaround - a.avg_turnaround)[0];
            out.push({ icon: "fa-wrench", tone: "info",
                text: _t("Longest offer turnaround: %(name)s at %(days)s days on average.", { name: slowest.name, days: slowest.avg_turnaround }) });
        }
        const scaling = [...d.effluent].filter((e) => e.silica).sort((a, b) => b.silica - a.silica)[0];
        if (scaling) {
            out.push({ icon: "fa-flask", tone: "info",
                text: _t("Highest average silica (scaling risk): %(name)s at %(v)s ppm.", { name: scaling.name, v: scaling.silica }) });
        }
        return out;
    }

    get periodLabel() {
        const p = this.state.data.options.periods.find((x) => x.id === this.state.filters.period);
        return p ? p.name : "";
    }
}

registry.category("actions").add("dotbd_crm_dashboard", CrmDashboard);
