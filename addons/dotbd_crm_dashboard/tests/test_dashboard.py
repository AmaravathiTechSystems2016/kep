from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase


class DashboardDataMixin:
    @classmethod
    def _make_demo_leads(cls, env):
        today = fields.Date.context_today(env['crm.lead'])
        stages = env['crm.stage'].search([])
        system_mee = env['crm.lead.system'].search([('name', '=', 'MEE')], limit=1)
        system_zld = env['crm.lead.system'].search([('name', '=', 'ZLD')], limit=1)
        epc = env['crm.lead.type'].search([('name', '=', 'EPC')], limit=1)
        non_epc = env['crm.lead.type'].search([('name', '=', 'Non-EPC')], limit=1)
        capacity = env['crm.lead.capacity'].create({'name': '40 KLPD'})
        admin = env.ref('base.user_admin')
        other = env['res.users'].create({
            'name': 'Dash Engineer', 'login': 'dash_eng@example.com',
            'group_ids': [(6, 0, [env.ref('base.group_user').id])],
        })
        base = {'type': 'opportunity', 'capacity_id': capacity.id}
        leads = env['crm.lead'].create([
            dict(base, name='L1', stage_id=stages[0].id, system_id=system_mee.id, lead_type_id=epc.id,
                 lead_owner_id=admin.id, worked_by_id=other.id, expected_revenue=1000000,
                 inquiry_date=today - timedelta(days=20), submitted_date=today - timedelta(days=10),
                 proposal_no='26001-KEP-MEE-PR-101-R2', tds=12000, silica=30, ph_value=7),
            dict(base, name='L2', stage_id=stages[2].id, system_id=system_mee.id, lead_type_id=non_epc.id,
                 lead_owner_id=admin.id, worked_by_id=admin.id, expected_revenue=2500000,
                 inquiry_date=today - timedelta(days=40), date_deadline=today - timedelta(days=3),
                 tds=8000, silica=50),
            dict(base, name='L3', stage_id=stages[3].id, system_id=system_zld.id, lead_type_id=epc.id,
                 lead_owner_id=other.id, expected_revenue=500000, inquiry_date=today - timedelta(days=5)),
            dict(base, name='L4 won', stage_id=stages[-1].id, system_id=system_zld.id, lead_type_id=epc.id,
                 lead_owner_id=admin.id, worked_by_id=other.id, expected_revenue=4000000,
                 inquiry_date=today - timedelta(days=60), submitted_date=today - timedelta(days=45),
                 proposal_no='26002-KEP-ZLD-PR-102-R6'),
            dict(base, name='L5 lost', stage_id=stages[1].id, system_id=system_mee.id, lead_type_id=epc.id,
                 lead_owner_id=other.id, expected_revenue=700000, inquiry_date=today - timedelta(days=50)),
        ])
        env['crm.lead'].browse(leads[4].id).action_set_lost(
            lost_reason_id=(env['crm.lost.reason'].search([], limit=1) or env['crm.lost.reason'].create({'name': 'Price'})).id)
        return leads


@tagged('post_install', '-at_install')
class TestCrmDashboardData(DashboardDataMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.leads = cls._make_demo_leads(cls.env)

    def kpi(self, data, key):
        return next(k for k in data['kpis'] if k['key'] == key)

    def test_empty_database_filters_do_not_break(self):
        data = self.env['dotbd.crm.dashboard'].get_data(period='month', owner_id=self.env.ref('base.public_user').id)
        self.assertFalse(data['has_data'])
        self.assertEqual(self.kpi(data, 'total')['value'], 0)
        self.assertIsNone(self.kpi(data, 'win_rate')['value'])

    def test_kpis_and_stages(self):
        data = self.env['dotbd.crm.dashboard'].get_data(period='all')
        total_expected = len(self.env['crm.lead'].with_context(active_test=False).search([]))
        self.assertEqual(self.kpi(data, 'total')['value'], total_expected)
        self.assertGreaterEqual(self.kpi(data, 'won')['value'], 1)
        self.assertGreaterEqual(self.kpi(data, 'lost')['value'], 1)
        self.assertEqual([s['name'] for s in data['stages']],
                         ['Inquiry', 'Scheme / Tech Offer', 'Commercial Offer', 'Discussion', 'PO', 'Won'])
        self.assertEqual(self.kpi(data, 'overdue')['value'], 1)
        # every kpi/stage/group drill-down domain must be a valid search domain
        Lead = self.env['crm.lead'].with_context(active_test=False)
        for item in data['kpis'] + data['stages'] + [data['lost']] + data['by_owner'] + data['by_worker'] \
                + data['by_system'] + data['by_model'] + data['by_capacity'] + data['lost_reasons']:
            if item.get('domain') is not None:
                Lead.search_count(item['domain'])
        stage_total = sum(s['count'] for s in data['stages'])
        open_won = self.kpi(data, 'open')['value'] + self.kpi(data, 'won')['value']
        self.assertEqual(stage_total, open_won)

    def test_filters(self):
        admin = self.env.ref('base.user_admin')
        data = self.env['dotbd.crm.dashboard'].get_data(period='all', owner_id=admin.id)
        self.assertTrue(all(r['id'] == admin.id for r in data['by_owner']))
        mee = self.env['crm.lead.system'].search([('name', '=', 'MEE')], limit=1)
        data = self.env['dotbd.crm.dashboard'].get_data(period='all', system_id=mee.id)
        self.assertEqual([r['name'] for r in data['by_system']], ['MEE'])
        for period in ('12m', 'month', 'quarter', 'year', 'all'):
            self.env['dotbd.crm.dashboard'].get_data(period=period)

    def test_engineer_and_effluent_analytics(self):
        data = self.env['dotbd.crm.dashboard'].get_data(period='all')
        worker = next(r for r in data['by_worker'] if r['name'] == 'Dash Engineer')
        self.assertEqual(worker['submitted'], 2)
        self.assertEqual(worker['avg_turnaround'], 12.5)   # L1: 10 days, L4: 15 days
        self.assertEqual(worker['max_revision'], 6)
        mee = next(r for r in data['effluent'] if r['name'] == 'MEE')
        self.assertEqual(mee['tds'], 10000.0)
        self.assertEqual(mee['silica'], 40.0)
        self.assertEqual(mee['tds_n'], 2)
        self.assertEqual(len(data['trend']), 12)
        self.assertTrue(any(r['name'] == 'R6' for r in data['revisions']))


@tagged('post_install', '-at_install')
class TestCrmDashboardUI(DashboardDataMixin, HttpCase):

    def setUp(self):
        super().setUp()
        self._make_demo_leads(self.env)
        admin = self.env.ref('base.user_admin')
        admin.write({'password': 'dashboard-test-pw'})
        self.admin_login = admin.login

    def test_standalone_dashboard_renders(self):
        self.authenticate(self.admin_login, 'dashboard-test-pw')
        self.start_tour('/odoo/action-dotbd_crm_dashboard', 'dotbd_crm_dashboard_standalone', login=self.admin_login)

    def test_dashboard_app_has_crm_tab(self):
        self.authenticate(self.admin_login, 'dashboard-test-pw')
        self.start_tour('/odoo/action-hrms_dashboard.hr_action_dashboard', 'dotbd_crm_dashboard_tab',
                        login=self.admin_login)
