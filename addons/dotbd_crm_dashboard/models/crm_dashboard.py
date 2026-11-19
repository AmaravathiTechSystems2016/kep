import re
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

LEAD_FIELDS = [
    'name', 'stage_id', 'won_status', 'active', 'expected_revenue', 'date_closed', 'write_date',
    'create_date', 'date_deadline', 'date_last_stage_update', 'day_close',
    'lead_owner_id', 'worked_by_id', 'system_id', 'lead_type_id', 'capacity_id',
    'lost_reason_id', 'source_id', 'inquiry_date', 'submitted_date', 'proposal_no',
    'ph_value', 'tds', 'cod', 'bod', 'tss', 'hardness', 'oil_grease', 'silica',
]
EFFLUENT_FIELDS = ['ph_value', 'tds', 'cod', 'bod', 'tss', 'hardness', 'oil_grease', 'silica']
PERIODS = [
    ('12m', 'Last 12 months'),
    ('month', 'This month'),
    ('quarter', 'This quarter'),
    ('year', 'This year'),
    ('all', 'All time'),
]
STALE_DAYS = 30
REVISION_RE = re.compile(r'-R(\d+)\s*$', re.IGNORECASE)


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _pct(num, den):
    return round(100.0 * num / den, 1) if den else None


class CrmDashboard(models.AbstractModel):
    _name = 'dotbd.crm.dashboard'
    _description = 'CRM Dashboard Data'

    @api.model
    def _period_start(self, period, today):
        if period == 'month':
            return today.replace(day=1)
        if period == 'quarter':
            return today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
        if period == 'year':
            return today.replace(month=1, day=1)
        if period == '12m':
            return today.replace(day=1) - relativedelta(months=11)
        return None

    @staticmethod
    def _inquiry_day(lead):
        return lead.inquiry_date or (lead.create_date and lead.create_date.date())

    @staticmethod
    def _revision(lead):
        match = lead.proposal_no and REVISION_RE.search(lead.proposal_no)
        return int(match.group(1)) if match else None

    @api.model
    def get_data(self, period='12m', owner_id=False, worked_by_id=False, system_id=False, model_id=False):
        Lead = self.env['crm.lead'].with_context(active_test=False)
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        start = self._period_start(period, today)

        base_domain = []
        if owner_id:
            base_domain.append(('lead_owner_id', '=', int(owner_id)))
        if worked_by_id:
            base_domain.append(('worked_by_id', '=', int(worked_by_id)))
        if system_id:
            base_domain.append(('system_id', '=', int(system_id)))
        if model_id:
            base_domain.append(('lead_type_id', '=', int(model_id)))
        period_domain = []
        if start:
            period_domain = ['|', ('inquiry_date', '>=', start),
                             '&', ('inquiry_date', '=', False), ('create_date', '>=', start)]
        domain = base_domain + period_domain

        all_leads = Lead.search_fetch(base_domain, LEAD_FIELDS)
        leads = all_leads.filtered(
            lambda l: not start or (self._inquiry_day(l) and self._inquiry_day(l) >= start))

        def status(lead):
            return lead.won_status or 'pending'

        def value(recs):
            return sum(recs.mapped('expected_revenue'))

        def days_since(dt):
            return (now - dt).days if dt else 0

        open_leads = leads.filtered(lambda l: status(l) == 'pending' and l.active)
        won = leads.filtered(lambda l: status(l) == 'won')
        lost = leads.filtered(lambda l: status(l) == 'lost')

        turnarounds = {}
        for lead in leads:
            if lead.inquiry_date and lead.submitted_date and lead.submitted_date >= lead.inquiry_date:
                turnarounds[lead.id] = (lead.submitted_date - lead.inquiry_date).days

        submitted = leads.filtered(lambda l: l.submitted_date)
        pending_offer = open_leads.filtered(lambda l: not l.submitted_date)
        overdue = open_leads.filtered(lambda l: l.date_deadline and l.date_deadline < today)
        stale_cut = now - relativedelta(days=STALE_DAYS)
        stale = open_leads.filtered(lambda l: l.date_last_stage_update and l.date_last_stage_update < stale_cut)
        open_domain = domain + [('active', '=', True), ('won_status', '=', 'pending')]

        kpis = [
            {'key': 'total', 'label': _('Total Inquiries'), 'value': len(leads), 'fmt': 'int', 'domain': domain},
            {'key': 'open', 'label': _('Open Pipeline'), 'value': len(open_leads), 'fmt': 'int',
             'sub': value(open_leads), 'domain': open_domain},
            {'key': 'won', 'label': _('Won'), 'value': len(won), 'fmt': 'int',
             'sub': value(won), 'domain': domain + [('won_status', '=', 'won')]},
            {'key': 'lost', 'label': _('Lost'), 'value': len(lost), 'fmt': 'int',
             'sub': value(lost), 'domain': domain + [('won_status', '=', 'lost')]},
            {'key': 'win_rate', 'label': _('Win Rate'), 'value': _pct(len(won), len(won) + len(lost)),
             'fmt': 'pct', 'hint': _('Won / (Won + Lost)')},
            {'key': 'avg_deal', 'label': _('Avg Deal Size'),
             'value': (value(won) / len(won)) if won else None, 'fmt': 'money',
             'hint': _('Won value / won count')},
            {'key': 'cycle', 'label': _('Avg Sales Cycle'), 'value': _avg([l.day_close for l in won]),
             'fmt': 'days', 'hint': _('Days from creation to win')},
            {'key': 'turnaround', 'label': _('Offer Turnaround'), 'value': _avg(list(turnarounds.values())),
             'fmt': 'days', 'hint': _('Inquiry date to submitted date')},
            {'key': 'submitted', 'label': _('Offers Submitted'), 'value': len(submitted), 'fmt': 'int',
             'hint': _('%s%% of inquiries') % (_pct(len(submitted), len(leads)) or 0),
             'domain': domain + [('submitted_date', '!=', False)]},
            {'key': 'pending_offer', 'label': _('Offers Pending'), 'value': len(pending_offer), 'fmt': 'int',
             'hint': _('Open leads without a submitted date'),
             'domain': open_domain + [('submitted_date', '=', False)]},
            {'key': 'overdue', 'label': _('Overdue Closing'), 'value': len(overdue), 'fmt': 'int',
             'hint': _('Open leads past expected closing'),
             'domain': open_domain + [('date_deadline', '<', today)]},
            {'key': 'stale', 'label': _('Stale > %s days', STALE_DAYS), 'value': len(stale), 'fmt': 'int',
             'hint': _('Open leads with no stage movement'),
             'domain': open_domain + [('date_last_stage_update', '<', stale_cut)]},
        ]

        # Pipeline by stage. Lost leads keep their old stage, so Lost gets its own bar.
        stage_rows, reach = [], len(open_leads) + len(won)
        for stage in self.env['crm.stage'].search([]):
            recs = (open_leads | won).filtered(lambda l: l.stage_id == stage)
            stage_rows.append({
                'id': stage.id, 'name': stage.name, 'is_won': stage.is_won,
                'count': len(recs), 'value': value(recs), 'reach': reach,
                'avg_age': _avg([days_since(l.date_last_stage_update) for l in recs if status(l) == 'pending']),
                'domain': domain + [('stage_id', '=', stage.id), ('won_status', '!=', 'lost')],
            })
            reach -= len(recs)
        lost_row = {'id': 'lost', 'name': _('Lost'), 'count': len(lost), 'value': value(lost),
                    'domain': domain + [('won_status', '=', 'lost')]}

        # 12-month trend; ignores the period filter so its shape is always visible.
        months = [today.replace(day=1) - relativedelta(months=i) for i in range(11, -1, -1)]
        trend = {m: {'label': m.strftime('%b %y'), 'new': 0, 'won': 0, 'lost': 0, 'won_value': 0.0,
                     'turn': []} for m in months}
        for lead in all_leads:
            inq = self._inquiry_day(lead)
            if inq and inq.replace(day=1) in trend:
                trend[inq.replace(day=1)]['new'] += 1
            closed = lead.date_closed or lead.write_date
            closed_month = closed.date().replace(day=1) if closed else None
            if closed_month in trend:
                if status(lead) == 'won':
                    trend[closed_month]['won'] += 1
                    trend[closed_month]['won_value'] += lead.expected_revenue
                elif status(lead) == 'lost':
                    trend[closed_month]['lost'] += 1
            if lead.inquiry_date and lead.submitted_date and lead.submitted_date >= lead.inquiry_date:
                sub_month = lead.submitted_date.replace(day=1)
                if sub_month in trend:
                    trend[sub_month]['turn'].append((lead.submitted_date - lead.inquiry_date).days)
        trend_rows = []
        for m in months:
            row = trend[m]
            row['turnaround'] = _avg(row.pop('turn'))
            trend_rows.append(row)

        def group(recs, getter, field, top=None, null_label=None):
            buckets = defaultdict(lambda: self.env['crm.lead'])
            for lead in recs:
                buckets[getter(lead)] |= lead
            rows = []
            for rec, g_leads in buckets.items():
                g_won = g_leads.filtered(lambda l: status(l) == 'won')
                g_lost = g_leads.filtered(lambda l: status(l) == 'lost')
                g_open = g_leads.filtered(lambda l: status(l) == 'pending' and l.active)
                key = rec.id if rec else False
                rows.append({
                    'id': key, 'name': rec.display_name if rec else (null_label or _('Not set')),
                    'count': len(g_leads), 'open': len(g_open), 'open_value': value(g_open),
                    'won': len(g_won), 'won_value': value(g_won), 'lost': len(g_lost),
                    'win_rate': _pct(len(g_won), len(g_won) + len(g_lost)),
                    'domain': domain + [(field, '=', key)],
                    '_leads': g_leads,
                })
            rows.sort(key=lambda r: (-r['count'], r['name']))
            return rows[:top] if top else rows

        def clean(rows):
            for row in rows:
                row.pop('_leads', None)
            return rows

        by_system = group(leads, lambda l: l.system_id, 'system_id')
        effluent = []
        for row in by_system:
            entry = {'id': row['id'], 'name': row['name'], 'count': row['count']}
            for fname in EFFLUENT_FIELDS:
                filled = [l[fname] for l in row['_leads'] if l[fname]]
                entry[fname] = _avg(filled)
                entry[fname + '_n'] = len(filled)
            effluent.append(entry)

        by_worker = group(leads, lambda l: l.worked_by_id, 'worked_by_id', null_label=_('Unassigned'))
        for row in by_worker:
            w_leads = row['_leads']
            revs = [r for r in (self._revision(l) for l in w_leads) if r is not None]
            row['submitted'] = len(w_leads.filtered(lambda l: l.submitted_date))
            row['avg_turnaround'] = _avg([turnarounds[l.id] for l in w_leads if l.id in turnarounds])
            row['avg_revision'] = _avg(revs)
            row['max_revision'] = max(revs) if revs else None

        by_owner = group(leads, lambda l: l.lead_owner_id, 'lead_owner_id', null_label=_('Unassigned'))
        by_model = group(leads, lambda l: l.lead_type_id, 'lead_type_id')
        by_capacity = group(leads, lambda l: l.capacity_id, 'capacity_id', top=10)
        by_source = group(leads, lambda l: l.source_id, 'source_id', top=8)
        lost_reasons = group(lost, lambda l: l.lost_reason_id, 'lost_reason_id', null_label=_('No reason'))
        for row in lost_reasons:
            row['domain'] = domain + [('won_status', '=', 'lost'), ('lost_reason_id', '=', row['id'])]

        revision_hist = defaultdict(int)
        for lead in leads:
            if lead.proposal_no:
                revision_hist[self._revision(lead) or 0] += 1
        revisions = [{'name': 'R%s' % k, 'count': v} for k, v in sorted(revision_hist.items())]

        currency = self.env.company.currency_id
        users = self.env['res.users'].search([('share', '=', False)])
        return {
            'period': period,
            'currency': {'symbol': currency.symbol, 'name': currency.name},
            'options': {
                'periods': [{'id': k, 'name': v} for k, v in PERIODS],
                'users': [{'id': u.id, 'name': u.name} for u in users],
                'systems': [{'id': s.id, 'name': s.name} for s in self.env['crm.lead.system'].search([])],
                'models': [{'id': t.id, 'name': t.name} for t in self.env['crm.lead.type'].search([])],
            },
            'kpis': kpis,
            'stages': stage_rows,
            'lost': lost_row,
            'trend': trend_rows,
            'by_system': clean(by_system),
            'by_model': clean(by_model),
            'by_capacity': clean(by_capacity),
            'by_owner': clean(by_owner),
            'by_worker': clean(by_worker),
            'by_source': clean(by_source),
            'lost_reasons': clean(lost_reasons),
            'effluent': effluent,
            'revisions': revisions,
            'has_data': bool(leads),
        }
