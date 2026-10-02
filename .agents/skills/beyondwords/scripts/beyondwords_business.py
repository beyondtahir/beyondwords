"""Explicit financial scenarios and authorized report imports; no BSR estimates."""
from __future__ import annotations
import csv
from datetime import date
from decimal import Decimal, ROUND_CEILING
import io
import json
import publishing_core as core
from publishing_project import digest, ProjectError


def fail(message):
    raise ProjectError('INVALID_REPORT', message)


def amount(value, field, *, signed=False):
    return core.number(value, field, nonnegative=not signed)


def goal_plan(value):
    if not isinstance(value, dict):
        raise ValueError('Goal input must be an object')
    if value.get('goal_type') != 'monthly_pre_tax_profit':
        raise ValueError('This calculator requires goal_type=monthly_pre_tax_profit; cash payouts need separate timing')
    currency = core.currency_code(value.get('currency'))
    target = amount(value.get('target'), 'target')
    fixed = amount(value.get('monthly_fixed_cost'), 'monthly_fixed_cost')
    hours = amount(value.get('weekly_hours'), 'weekly_hours')
    if hours <= 0:
        raise ValueError('weekly_hours must be positive')
    stages = value.get('production_hours')
    if not isinstance(stages, dict) or not stages:
        raise ValueError('Supply production_hours by stage')
    production = sum((amount(v, k) for k, v in stages.items()), Decimal(0))
    scenarios = value.get('scenarios')
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 10:
        raise ValueError('Supply 1–10 named scenarios')
    rows = []
    for scenario in scenarios:
        name = core.text(scenario.get('name'), 'scenario.name')
        basis = core.text(scenario.get('basis'), 'scenario.basis')
        receipts = amount(scenario.get('net_royalty_per_paid_sale'), 'net_royalty_per_paid_sale')
        variable = amount(scenario.get('additional_variable_cost_per_sale'), 'additional_variable_cost_per_sale')
        contribution = receipts-variable
        required = int(((target+fixed)/contribution).to_integral_value(rounding=ROUND_CEILING)) if contribution > 0 else None
        rows.append(dict(name=name, basis=basis, contribution_per_sale=str(contribution), required_monthly_paid_sales=required,
                         demand_established=False, finite_solution=required is not None))
    return dict(currency=currency, goal_type=value['goal_type'], target=str(target), scenarios=rows,
                production_weeks=str(production/hours), production_hours=str(production),
                external_delay_weeks=value.get('external_delay_weeks', 'UNKNOWN'),
                required_number_of_books=None, income_date=None,
                note='Scenario arithmetic, not a sales forecast. Do not deduct printing/delivery twice if already included in net royalties. Catalog size requires actual per-title results.')


def parse_report(raw, config, now):
    if not isinstance(raw, bytes) or not raw or len(raw) > 5*1024*1024:
        fail('CSV must be nonempty and at most 5 MiB')
    kind = config.get('kind')
    if kind not in {'royalties', 'ads', 'costs', 'sales'}:
        fail('kind must be royalties, ads, costs, or sales')
    for key in ('account_label', 'marketplace', 'title_id', 'permission_basis', 'source_description'):
        core.text(config.get(key), key)
    if type(config.get('synthetic')) is not bool or config.get('authorized') is not True:
        fail('Declare authorized import and synthetic context explicitly')
    if config.get('basis') not in {'estimated', 'finalized'}:
        fail('basis must distinguish estimated from finalized reports')
    currency = core.currency_code(config.get('currency'))
    start, end = date.fromisoformat(config['period_start']), date.fromisoformat(config['period_end'])
    if start > end or end > core.timestamp(now, 'now').date():
        fail('Report period is reversed or in the future')
    mapping = config.get('column_map')
    if not isinstance(mapping, dict) or not {'date', 'amount', 'currency'} <= mapping.keys():
        fail('Map date, amount and currency to actual CSV column names')
    allowed = {'date', 'amount', 'currency', 'units', 'clicks', 'impressions', 'attributed_orders', 'attributed_sales', 'row_id'}
    if set(mapping) - allowed or len(set(mapping.values())) != len(mapping):
        fail('Unknown fields or reused column mappings')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        fail('CSV has missing or duplicate headers')
    if not set(mapping.values()) <= set(reader.fieldnames):
        fail('Mapped columns are missing; inspect the actual report header')
    rows, seen = [], set()
    total = Decimal(0)
    for index, row in enumerate(reader, 2):
        if index > 100002:
            fail('Too many rows')
        if None in row or None in row.values():
            fail('Malformed CSV row')
        item = {key: row[column].strip() for key, column in mapping.items()}
        observed = date.fromisoformat(item['date'])
        if not start <= observed <= end or item['currency'] != currency:
            fail('Row outside declared period or mixed currencies; split reports')
        val = amount(item['amount'], 'amount', signed=kind in {'royalties','sales'})
        item['amount'] = str(val); total += val
        if 'row_id' in item:
            if not item['row_id'] or item['row_id'] in seen:
                fail('Duplicate or empty row ID')
            seen.add(item['row_id'])
        for field in ('units', 'clicks', 'impressions', 'attributed_orders'):
            if field in item:
                try:
                    item[field] = int(item[field])
                except ValueError:
                    fail('Counts must be whole integers')
                if item[field] < 0 and (kind not in {'royalties','sales'} or field != 'units'):
                    fail('Negative ad counts are invalid')
        if 'attributed_sales' in item:
            item['attributed_sales'] = str(amount(item['attributed_sales'], 'attributed_sales'))
        if 'clicks' in item and 'impressions' in item and item['clicks'] > item['impressions']:
            fail('Clicks exceed impressions; review the mapping')
        rows.append(item)
    if not rows:
        fail('Report contains no data rows')
    expected = amount(config.get('source_total'), 'source_total', signed=kind in {'royalties','sales'})
    if total != expected:
        fail('Imported rows do not reconcile to the supplied source total')
    return dict(kind=kind, currency=currency, account_label=config['account_label'], marketplace=config['marketplace'],
                title_id=config['title_id'], period_start=str(start), period_end=str(end),
                basis=config['basis'], synthetic=config['synthetic'], source_sha256=digest(raw),
                permission_basis=config['permission_basis'], source_description=config['source_description'],
                imported_at=now, total=str(total), source_total=str(expected), rows=rows, reconciled=True,
                independent_source_authentication=False,
                attribution_window=config.get('attribution_window', 'UNKNOWN'))


def summarize_reports(reports):
    groups = {}
    # Preserve period/account/title grain. Never combine attribution sales with royalties.
    for report in reports:
        key = tuple(report[x] for x in ('currency', 'account_label', 'marketplace', 'title_id', 'period_start', 'period_end'))
        group = groups.setdefault(key, {'reports': [], 'totals': {}, 'basis': [], 'ads': []})
        group['reports'].append(report['source_sha256'])
        group['totals'][report['kind']] = group['totals'].get(report['kind'], Decimal(0))+Decimal(report['total'])
        group['basis'].append(report['basis'])
        if report['kind'] == 'ads':
            group['ads'].append(report)
    result = []
    for key, group in groups.items():
        totals = group['totals']
        missing = [kind for kind in ('royalties', 'ads', 'costs') if kind not in totals]
        profit = totals['royalties']-totals['ads']-totals['costs'] if not missing else None
        ad_rows = [row for report in group['ads'] for row in report['rows']]
        metrics = {}
        for field in ('clicks', 'impressions', 'attributed_orders', 'attributed_sales'):
            metrics[field] = sum((Decimal(str(row[field])) for row in ad_rows), Decimal(0)) if ad_rows and all(field in row for row in ad_rows) else None
        def ratio(numerator, denominator):
            return str(numerator/denominator) if numerator is not None and denominator and denominator > 0 else None
        metrics.update(cost_per_click=ratio(totals.get('ads'), metrics['clicks']),
                       click_through_rate=ratio(metrics['clicks'], metrics['impressions']),
                       cost_per_attributed_order=ratio(totals.get('ads'), metrics['attributed_orders']),
                       attributed_retail_roas=ratio(metrics['attributed_sales'], totals.get('ads')))
        result.append({**dict(zip(('currency', 'account_label', 'marketplace', 'title_id', 'period_start', 'period_end'), key)),
                       'totals': {k: str(v) for k, v in totals.items()}, 'reported_pre_tax_profit': str(profit) if profit is not None else None,
                       'missing': missing, 'basis': 'finalized' if set(group['basis']) == {'finalized'} else 'estimated',
                       'source_hashes': group['reports'], 'ad_metrics': {k: str(v) if v is not None else None for k, v in metrics.items()},
                       'attribution_windows': sorted({r.get('attribution_window', 'UNKNOWN') for r in group['ads']})})
    return {'groups': result, 'note': 'Net royalties minus separately incurred ads/costs for matching periods. Missing reports are not zero. Attribution sales are not author income; profit is not cash payout or proof ads caused the sales.'}
