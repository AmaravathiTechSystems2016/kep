from odoo import api, fields, models
from odoo.exceptions import AccessError

class PerformanceEvaluationTopic(models.Model):
    _name = 'performance.evaluation.topic'
    _description = 'Performance Evaluation Topic'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    description = fields.Text(tracking=True)
