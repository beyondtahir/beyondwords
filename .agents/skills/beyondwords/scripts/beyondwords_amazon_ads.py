"""Amazon Ads: official unified Sponsored Products API + v3 asynchronous reports.

No third-party advertising service, browser account cookies, inferred credentials or
automatic mutation retry. The pinned official OpenAPI is data, never executable code.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import io
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from beyondwords_connected import (ConnectionError, Journal, canonical, digest, instant,
                                  now, clean_text, operator_confirmation)

ENDPOINTS = {'NA': 'https://advertising-api.amazon.com', 'EU': 'https://advertising-api-eu.amazon.com',
             'FE': 'https://advertising-api-fe.amazon.com'}
TOKEN_URL = 'https://api.amazon.com/auth/o2/token'
SPEC = Path(__file__).resolve().parents[1]/'assets/contracts/amazon-ads-sp-openapi.json'
SINGULAR = {'campaigns': 'campaign', 'adGroups': 'adGroup', 'ads': 'ad', 'targets': 'target'}
NAMES = {'campaigns': 'Campaign', 'adGroups': 'AdGroup', 'ads': 'Ad', 'targets': 'Target'}
MAX_BYTES = 16*1024*1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTP:
    """Fixed HTTPS destinations, TLS verification, bounded bodies, no proxy inheritance."""
    synthetic = False

    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def send(self, method, url, headers, body=None):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in {None,443}:
            raise ConnectionError('DESTINATION_BLOCKED', 'Invalid API destination')
        if url != TOKEN_URL and parsed.scheme+'://'+parsed.netloc not in ENDPOINTS.values():
            raise ConnectionError('DESTINATION_BLOCKED', 'Only official Ads API endpoints are accepted')
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(MAX_BYTES+1)
                if len(raw) > MAX_BYTES:
                    raise ConnectionError('RESPONSE_TOO_LARGE', 'Response exceeded size limit', uncertain=method!='GET')
                try:
                    data = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise ConnectionError('INVALID_RESPONSE', 'API returned invalid JSON', uncertain=method!='GET') from None
                return response.status, data
        except urllib.error.HTTPError as exc:
            # Do not disclose bodies, URLs with queries, cookies, headers or OAuth secrets.
            raise ConnectionError('HTTP_'+str(exc.code), 'Amazon returned HTTP '+str(exc.code),
                                  uncertain=exc.code >= 500 and method != 'GET') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ConnectionError('NETWORK_ERROR', 'Amazon request failed; no credentials logged', uncertain=method!='GET') from None


def money(value):
    if isinstance(value, bool):
        raise ValueError('Money cannot be boolean')
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid monetary amount') from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal('1000000'):
        raise ValueError('Positive finite monetary amount required')
    return amount


def validate(value, schema, spec=None):
    """Strict subset of OpenAPI used here; unknown fields are rejected, never forwarded."""
    spec = spec or json.loads(SPEC.read_text())
    if '$ref' in schema:
        return validate(value, spec['components']['schemas'][schema['$ref'].split('/')[-1]], spec)
    if value is None and schema.get('nullable'):
        return
    if 'oneOf' in schema:
        good = 0
        for child in schema['oneOf']:
            try:
                validate(value, child, spec); good += 1
            except ValueError:
                pass
        if good != 1:
            raise ValueError('Exactly one documented schema variant is required')
        return
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'integer': int}
    if kind in types and type(value) is not types[kind]:
        raise ValueError('Invalid API field type: '+kind)
    if kind == 'number' and (type(value) not in (float,int) or not math.isfinite(value)):
        raise ValueError('Finite API number required')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Unsupported API enum')
    if kind == 'object':
        props = schema.get('properties', {})
        if set(value)-set(props) or set(schema.get('required', []))-set(value):
            raise ValueError('Unknown or missing API fields')
        for key, item in value.items():
            validate(item, props[key], spec)
    elif kind == 'array':
        if not schema.get('minItems',0) <= len(value) <= schema.get('maxItems',1000):
            raise ValueError('Invalid API array size')
        for item in value:
            validate(item, schema['items'], spec)
    elif kind == 'string':
        clean_text(value, 2000)
        if schema.get('format') == 'date-time':
            instant(value)
    elif kind in {'integer','number'}:
        if value < schema.get('minimum',-math.inf) or value > schema.get('maximum', math.inf):
            raise ValueError('API number outside documented range')


class Ads:
    def __init__(self, config, *, transport=None, credentials=None):
        if set(config)-{'region','profile_id','country','currency'}:
            raise ValueError('Unknown account configuration; never include credentials in JSON')
        self.config = dict(config)
        self.base = ENDPOINTS[config['region']]
        if 'profile_id' not in config and set(config)!={'region'}:
            raise ValueError('Discover profiles with region only, then select profile/country/currency together')
        if 'profile_id' in config and not re.fullmatch(r'[0-9]{1,30}', str(config['profile_id'])):
            raise ValueError('Select an actual numeric Ads profile')
        if 'profile_id' in config and (not re.fullmatch(r'[A-Z]{2}',config.get('country','')) or not re.fullmatch(r'[A-Z]{3}',config.get('currency',''))):
            raise ValueError('Expected profile country and currency required')
        self.transport = transport or HTTP()
        self.synthetic = getattr(self.transport,'synthetic',False)
        self.credentials = credentials or {k: os.environ.get('BEYONDWORDS_ADS_'+k,'') for k in ('CLIENT_ID','CLIENT_SECRET','REFRESH_TOKEN')}
        if not all(isinstance(v,str) and v and '\n' not in v and '\r' not in v for v in self.credentials.values()) or set(self.credentials) != {'CLIENT_ID','CLIENT_SECRET','REFRESH_TOKEN'}:
            raise ConnectionError('ACCOUNT_NOT_CONNECTED', 'Configure approved Amazon Ads OAuth credentials in the private process environment, never in chat or project files')
        self._token = None
        self._expires = 0

    def token(self):
        if self._token and time.monotonic() < self._expires:
            return self._token
        body = urllib.parse.urlencode({'grant_type':'refresh_token','client_id':self.credentials['CLIENT_ID'],
                                      'client_secret':self.credentials['CLIENT_SECRET'],
                                      'refresh_token':self.credentials['REFRESH_TOKEN']}).encode()
        _, response = self.transport.send('POST', TOKEN_URL, {'Content-Type':'application/x-www-form-urlencoded'}, body)
        token = response.get('access_token') if isinstance(response,dict) else None
        if not isinstance(token,str) or not token or '\r' in token or '\n' in token:
            raise ConnectionError('INVALID_OAUTH_RESPONSE', 'OAuth did not return an access token')
        self._token = token
        self._expires = time.monotonic()+max(0,min(int(response.get('expires_in',0))-60,3600))
        return token

    def request(self, method, path, body=None, *, content_type='application/json'):
        headers = {'Authorization':'Bearer '+self.token(),'Amazon-Advertising-API-ClientId':self.credentials['CLIENT_ID'],
                   'Content-Type':content_type,
                   'Accept':'application/json'}
        if self.config.get('profile_id') is not None and path!='/v2/profiles':
            headers['Amazon-Advertising-API-Scope']=str(self.config['profile_id'])
        _, result = self.transport.send(method, self.base+path, headers, canonical(body).encode() if body is not None else None)
        return result

    def profiles(self):
        rows = self.request('GET','/v2/profiles')
        if not isinstance(rows,list):
            raise ConnectionError('INVALID_RESPONSE','Profiles response was not a list')
        return rows

    def identity(self):
        if 'profile_id' not in self.config:
            raise ValueError('Discover and select an actual profile before account operations')
        rows = [r for r in self.profiles() if str(r.get('profileId')) == str(self.config['profile_id'])]
        if len(rows) != 1:
            raise ConnectionError('PROFILE_MISMATCH','Selected profile was not uniquely returned by Amazon')
        p = rows[0]
        if p.get('countryCode') != self.config['country'] or p.get('currencyCode') != self.config['currency']:
            raise ConnectionError('PROFILE_MISMATCH','Selected profile country/currency differs from the intended account')
        if not p.get('accountInfo',{}).get('id'):
            raise ConnectionError('PROFILE_MISMATCH','Profile has no advertiser account identity')
        return {**self.config, 'account_id':str(p['accountInfo']['id']), 'account_type':p['accountInfo'].get('type','UNKNOWN'),
                'timezone':p.get('timezone','UNKNOWN'), 'client_sha256':digest(self.credentials['CLIENT_ID'])}

    def query(self, entity, filters=None):
        if entity not in SINGULAR:
            raise ValueError('Unsupported Ads entity')
        body = {'adProductFilter':{'include':['SPONSORED_PRODUCTS']},'maxResults':1000, **(filters or {})}
        schema = {'$ref':'#/components/schemas/SPQuery'+NAMES[entity]+'Request'}
        validate(body,schema)
        rows, seen = [], set()
        for _ in range(20):
            data = self.request('POST','/adsApi/v1/query/'+entity, body)
            if not isinstance(data,dict) or not isinstance(data.get(entity),list):
                raise ConnectionError('INVALID_RESPONSE','Query response missing entity list')
            rows.extend(data[entity])
            token = data.get('nextToken')
            if not token:
                return rows
            if token in seen:
                raise ConnectionError('PAGINATION_ERROR','Repeated API pagination token')
            seen.add(token); body['nextToken'] = token
        raise ConnectionError('PAGINATION_LIMIT','Account query exceeded page limit; narrow its scope')

    def snapshot(self, entity, item_id):
        rows = self.query(entity,{SINGULAR[entity]+'IdFilter':{'include':[str(item_id)]}})
        if len(rows)!=1 or str(rows[0].get(SINGULAR[entity]+'Id')) != str(item_id):
            raise ConnectionError('ENTITY_MISMATCH','Amazon did not return the exact selected entity')
        return rows[0]

    def prepare(self, journal, payload):
        method, entity = payload['verb'], payload['entity']
        if method not in {'create','update'} or entity not in SINGULAR:
            raise ValueError('Only supported creation/update operations are available')
        body = json.loads(canonical(payload['body']))
        validate(body, {'$ref':'#/components/schemas/SP'+method.title()+NAMES[entity]+'Request'})
        if len(body[entity]) != 1:
            raise ValueError('One entity per durable operation; prepare a reviewed sequence for campaigns')
        item = body[entity][0]
        identity = self.identity()
        limits = payload['limits']
        pause_only=method=='update' and set(item)=={SINGULAR[entity]+'Id','state'} and item['state']=='PAUSED'
        if not (pause_only and limits=={}) and set(limits) != {'max_daily_budget','max_bid'}:
            raise ValueError('Explicit daily-budget and bid bounds required')
        limits = {k:str(money(v)) for k,v in limits.items()}
        intent=digest({'project':journal.project_id,'identity':identity,'verb':method,'entity':entity,'body':body})
        if method == 'create':
            # Correlation is for reconciliation, not an undocumented API idempotency header.
            if 'tags' in item:
                raise ValueError('Correlation tags are connector-owned')
            item['tags'] = [{'key':'beyondwords_operation','value':intent}]
        # This first connected release supports bounded manual targeting only.
        if entity == 'campaigns':
            if method == 'create' and (item['state']!='PAUSED' or item['autoCreationSettings'] != {'autoCreateTargets':False,'autoManageCampaign':False}):
                raise ValueError('Create campaigns paused with explicit manual lifecycle/targeting')
            if method == 'create' and item.get('optimizations') != {'bidSettings':{'bidStrategy':'MANUAL'}}:
                raise ValueError('This bounded connector requires fixed manual bidding without multipliers')
            if method == 'update' and set(item)-{'campaignId','state','budgets','endDateTime'}:
                raise ValueError('Only campaign state, daily budget and end time updates supported')
            for budget in item.get('budgets',[]):
                if budget['recurrenceTimePeriod']!='DAILY' or budget['budgetType']!='MONETARY':
                    raise ValueError('Only monetary daily budgets supported')
                value = budget['budgetValue']['monetaryBudgetValue']['monetaryBudget']['value']
                if money(value) > money(limits['max_daily_budget']):
                    raise ValueError('Daily budget exceeds reviewed limit')
        if entity == 'adGroups':
            if method == 'update' and set(item)-{'adGroupId','state','bid'}:
                raise ValueError('Only ad-group state and bid updates supported')
            if item.get('bid') and money(item['bid']['defaultBid']) > money(limits['max_bid']):
                raise ValueError('Bid exceeds limit')
        if entity == 'ads' and method == 'update' and set(item)-{'adId','state'}:
            raise ValueError('Only ad state updates supported')
        if entity == 'ads' and method == 'create':
            product = item['creative']['productCreative']['productCreativeSettings']
            if set(product) != {'advertisedProduct'} or product['advertisedProduct'].get('productIdType')!='ASIN' or set(product['advertisedProduct'])!={'productId','productIdType'}:
                raise ValueError('Author ads require a specific ASIN and standard product creative')
            if not re.fullmatch('[A-Z0-9]{10}', product['advertisedProduct']['productId']):
                raise ValueError('Selected edition ASIN required')
        if entity == 'targets':
            if method == 'create' and item.get('targetType') not in {'KEYWORD','PRODUCT'}:
                raise ValueError('Only explicit keyword/product targeting supported')
            if method == 'create' and not item.get('adGroupId'):
                raise ValueError('Select the actual ad group for positive or negative targets')
            if method == 'create' and item.get('negative'):
                if item.get('bid'):raise ValueError('Negative targets do not bid for traffic')
                if item['targetType']=='KEYWORD' and item['targetDetails']['keywordTarget']['matchType'] not in {'EXACT','PHRASE'}:
                    raise ValueError('Negative keywords support exact or phrase matching')
            if method == 'update' and set(item)-{'targetId','state','bid'}:
                raise ValueError('Only target state and bid updates supported')
            if item.get('bid') and money(item['bid']['bid']) > money(limits['max_bid']):
                raise ValueError('Target bid exceeds limit')
        preconditions = []
        if method == 'update':
            key = SINGULAR[entity]+'Id'
            current = self.snapshot(entity,item[key])
            preconditions.append({'entity':entity,'id':item[key],'sha256':digest(current)})
        else:
            current = item
        campaign_id = item.get('campaignId') or current.get('campaignId')
        adgroup_id = item.get('adGroupId') or current.get('adGroupId')
        if adgroup_id and entity in {'ads','targets'}:
            group = self.snapshot('adGroups',adgroup_id)
            preconditions.append({'entity':'adGroups','id':adgroup_id,'sha256':digest(group)})
            campaign_id = group['campaignId']
        if campaign_id:
            campaign = self.snapshot('campaigns',campaign_id)
            preconditions.append({'entity':'campaigns','id':campaign_id,'sha256':digest(campaign)})
            if method == 'create' and campaign['state']!='PAUSED':
                raise ValueError('Build new components while the campaign is paused')
            if campaign['state']=='ENABLED' and item.get('state')!='PAUSED':
                self.check_active_limits(campaign,limits)
        if entity == 'campaigns' and method == 'update' and item.get('state')=='ENABLED':
            # Activation reviews the actual assembled campaign, not only an ID.
            campaign = {**current, **item}
            self.check_active_limits(campaign,limits)
            for child in ('adGroups','ads','targets'):
                rows = self.query(child, {'campaignIdFilter':{'include':[item['campaignId']]}})
                if not rows or not any(r.get('state')=='ENABLED' for r in rows):
                    raise ValueError('Activation needs an enabled ad group, ad and target')
                for row in rows:
                    if child == 'adGroups' and money(row['bid']['defaultBid']) > money(limits['max_bid']):
                        raise ValueError('Existing ad group exceeds bid limit')
                    if child == 'targets' and row.get('bid',{}).get('bid') is not None and money(row['bid']['bid'])>money(limits['max_bid']):
                        raise ValueError('Existing target exceeds bid limit')
                preconditions.append({'entity':child,'campaign_id':item['campaignId'],'sha256':digest(rows)})
        validate(body, {'$ref':'#/components/schemas/SP'+method.title()+NAMES[entity]+'Request'})
        return journal.prepare({'project_id':journal.project_id,'synthetic':self.synthetic,'adapter':'amazon_ads',
                                'identity':identity,'verb':method,'entity':entity,'body':body,'limits':limits,
                                **({'intent_sha256':intent} if method=='create' else {}),
                                'preconditions':preconditions,'reason':clean_text(payload['reason'],1000),
                                'warnings':['Daily budgets are platform settings, not guaranteed total-spend caps. Reporting can lag; review Amazon budget rules before activation.']})

    @staticmethod
    def check_active_limits(campaign, limits):
        if not campaign.get('endDateTime') or instant(campaign['endDateTime']) <= now():
            raise ValueError('A future campaign end time is required for activation')
        if campaign.get('autoCreationSettings') != {'autoCreateTargets':False,'autoManageCampaign':False}:
            raise ValueError('Campaign automatic management is outside reviewed scope')
        if campaign.get('optimizations',{}).get('bidSettings') != {'bidStrategy':'MANUAL'}:
            raise ValueError('Campaign bidding multipliers or strategy differ from fixed manual scope')
        if len(campaign.get('budgets',[]))!=1:
            raise ValueError('Exactly one campaign budget required')
        amount=campaign['budgets'][0]['budgetValue']['monetaryBudgetValue']['monetaryBudget']['value']
        if money(amount)>money(limits['max_daily_budget']):
            raise ValueError('Existing campaign exceeds budget bound')

    def execute(self, journal, op_id, *, confirmer=operator_confirmation, guard=None):
        op = journal.get(op_id)
        if op['state']!='PREPARED' or not op['approval_current']:
            raise ConnectionError('RECONCILE_REQUIRED','Operation is expired, dispatched or closed; do not repeat')
        p = op['plan']
        if p.get('adapter')!='amazon_ads' or p['synthetic'] != self.synthetic or p['identity']!=self.identity():
            raise ConnectionError('SCOPE_MISMATCH','Operation belongs to another adapter/account/environment')
        signature = confirmer(op)
        for pre in p['preconditions']:
            current = (self.query(pre['entity'],{'campaignIdFilter':{'include':[pre['campaign_id']]}})
                       if 'campaign_id' in pre else self.snapshot(pre['entity'],pre['id']))
            if digest(current)!=pre['sha256']:
                raise ConnectionError('STALE_APPROVAL','Amazon account state changed; prepare a fresh action')
        # Refresh token before marking dispatch. OAuth failure cannot have sent a campaign.
        self.token()
        if guard:guard(op)
        journal.claim(op_id, signature)
        receipt=None
        try:
            response = self.request('POST','/adsApi/v1/'+p['verb']+'/'+p['entity'],p['body'])
            receipt = self.receipt(p['entity'], response)
            state = 'CONFIRMED' if receipt['accepted'] else 'REJECTED'
            if receipt['accepted']:
                item=p['body'][p['entity']][0]
                expected_id=item.get(SINGULAR[p['entity']]+'Id')
                if expected_id and str(expected_id)!=receipt['remote_id']:
                    raise ValueError('Response returned a different entity ID')
                observed=self.snapshot(p['entity'],receipt['remote_id'])
                state='CONFIRMED' if contains(observed,item) else 'UNKNOWN'
                receipt.update(observed_sha256=digest(observed),readback_matches=state=='CONFIRMED')
        except ConnectionError as exc:
            uncertain=exc.uncertain or bool(receipt and receipt.get('accepted'))
            state = 'UNKNOWN' if uncertain else 'REJECTED'
            receipt = {**(receipt or {}),'error_code':exc.code,'performed':'UNKNOWN' if uncertain else False}
        except (ValueError,KeyError,TypeError):
            state, receipt = 'UNKNOWN', {'error_code':'UNRECOGNIZED_RESPONSE','performed':'UNKNOWN'}
        return journal.finish(op_id,state,receipt)

    def receipt(self, entity, response):
        if not isinstance(response,dict) or set(response)-{'success','error'}:
            raise ValueError('Unknown mutation response')
        success, errors = response.get('success',[]), response.get('error',[])
        if not isinstance(success,list) or not isinstance(errors,list) or len(success)+len(errors)!=1:
            raise ValueError('Missing or ambiguous per-entity outcome')
        if success:
            item = success[0]
            remote = item[SINGULAR[entity]]
            key = SINGULAR[entity]+'Id'
            if item['index']!=0 or not re.fullmatch('[A-Za-z0-9_-]{1,100}',str(remote[key])):
                raise ValueError('Invalid response index/ID')
            return {'accepted':True,'entity':entity,'remote_id':str(remote[key]),'observed_state':remote.get('state','UNKNOWN'),
                    'response_sha256':digest(response),'synthetic':self.synthetic,'served_or_profitable':False}
        if errors[0].get('index')!=0:
            raise ValueError('Invalid error index')
        return {'accepted':False,'response_sha256':digest(response),'synthetic':self.synthetic,
                'error':'Amazon rejected this entity; inspect its account validation before preparing another action'}

    def reconcile(self, journal, op_id):
        op=journal.get(op_id); p=op['plan']
        if op['state'] not in {'IN_FLIGHT','UNKNOWN','CONFIRMED'} or p.get('adapter')!='amazon_ads':
            raise ValueError('Reconciliation requires a dispatched Ads operation')
        if p['identity']!=self.identity() or p['synthetic']!=self.synthetic:
            raise ValueError('Reconciliation account/environment mismatch')
        item=p['body'][p['entity']][0]; key=SINGULAR[p['entity']]+'Id'
        if p['verb']=='update':
            rows=[self.snapshot(p['entity'],item[key])]
            match=[r for r in rows if contains(r,item)]
        else:
            filters={}
            if item.get('adGroupId'): filters={'adGroupIdFilter':{'include':[item['adGroupId']]}}
            elif item.get('campaignId'): filters={'campaignIdFilter':{'include':[item['campaignId']]}}
            rows=self.query(p['entity'],filters)
            match=[r for r in rows if all(t in r.get('tags',[]) for t in item['tags']) and contains(r,item)]
        if len(match)!=1:
            return {'state':'UNKNOWN','operation_id':op_id,'matches':len(match),'retry_allowed':False,
                    'reason':'No unique remotely observed result; eventual consistency or conflicts require account review'}
        receipt={'accepted':True,'remote_id':str(match[0][key]),'observed_state':match[0].get('state','UNKNOWN'),
                 'reconciled_at':now().isoformat(),'response_sha256':digest(match[0]),'synthetic':self.synthetic}
        if op['state']=='CONFIRMED':
            return {**op,'reconciliation':receipt}
        return journal.finish(op_id,'CONFIRMED',receipt)

    def report_request(self, start, end):
        a,b=date.fromisoformat(start),date.fromisoformat(end)
        if a>b or (b-a).days>30 or b>=now().date():
            raise ValueError('Request 1–31 complete past days; use the account timezone when choosing dates')
        self.identity()
        body={'name':'Beyondwords campaign observation','startDate':start,'endDate':end,
              'configuration':{'adProduct':'SPONSORED_PRODUCTS','groupBy':['campaign'],
                               'columns':['date','campaignId','campaignName','impressions','clicks','cost','purchases14d','sales14d'],
                               'reportTypeId':'spCampaigns','timeUnit':'DAILY','format':'GZIP_JSON'}}
        result=self.request('POST','/reporting/reports',body,content_type='application/vnd.createasyncreportrequest.v3+json')
        report_id=result.get('reportId')
        if not isinstance(report_id,str) or not re.fullmatch('[A-Za-z0-9-]{1,100}',report_id):
            raise ConnectionError('INVALID_RESPONSE','Report request returned no valid report ID',uncertain=True)
        return {'report_id':report_id,'configuration':body,'identity':self.identity(),'synthetic':self.synthetic,
                'attribution':'14-day reported purchases/sales; not royalties, settled income or final attribution'}

    def report_status(self, report_id):
        if not re.fullmatch('[A-Za-z0-9-]{1,100}',report_id):
            raise ValueError('Invalid report ID')
        self.identity()
        return self.request('GET','/reporting/reports/'+report_id)


def contains(observed,expected):
    """Provider defaults may add fields; submitted fields must still match on readback."""
    if isinstance(expected,dict):
        return isinstance(observed,dict) and all(k in observed and contains(observed[k],v) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(observed,list) and len(observed)==len(expected) and all(contains(a,b) for a,b in zip(observed,expected))
    if isinstance(expected,str) and re.fullmatch(r'\d{4}-\d\d-\d\dT.*',expected):
        try:return instant(observed)==instant(expected)
        except (ValueError,AttributeError):return False
    return observed==expected


def download_report(url):
    """No OAuth headers on presigned report URLs; bounded gzip expansion and no redirects."""
    from publishing_browser import check_url
    parsed=urllib.parse.urlsplit(url)
    host=parsed.hostname or ''
    # Signed URLs come from the authenticated report response, never arbitrary user payloads.
    if not (re.fullmatch(r'[a-z0-9.-]+\.s3[.-][a-z0-9-]+\.amazonaws\.com',host) or
            re.fullmatch(r'[a-z0-9.-]+\.s3\.amazonaws\.com',host) or
            re.fullmatch(r's3[.-][a-z0-9-]+\.amazonaws\.com',host)):
        raise ConnectionError('REPORT_DESTINATION_BLOCKED','Report download is not an allowed Amazon S3 host')
    check_url(url, 'https://'+host+'/')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(urllib.request.Request(url,headers={'Accept':'application/octet-stream'}),timeout=30) as r:
            raw=r.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise ValueError('Compressed report too large')
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f: expanded=f.read(32*1024*1024+1)
        if len(expanded)>32*1024*1024: raise ValueError('Expanded report too large')
        rows=json.loads(expanded)
        if not isinstance(rows,list) or len(rows)>100000 or not all(isinstance(r,dict) for r in rows):
            raise ValueError('Expected bounded report rows')
        return rows
    except (urllib.error.URLError,OSError,ValueError,EOFError):
        raise ConnectionError('REPORT_DOWNLOAD_FAILED','Report download or decoding failed; signed URL omitted') from None


def dispatch(journal, payload):
    ads=Ads(payload['account'])
    task=payload['task']
    if task in {'prepare-campaign','execute-campaign'}:
        from beyondwords_campaign import prepare, execute
        return prepare(journal,ads,payload['campaign']) if task=='prepare-campaign' else execute(journal,ads,payload['operation_id'])
    if task=='profiles':
        return {'profiles':ads.profiles(),'synthetic':False}
    if task=='query':
        return {'identity':ads.identity(),'rows':ads.query(payload['entity'],payload.get('filters')),'observed_at':now().isoformat(),'synthetic':False}
    if task=='prepare': return ads.prepare(journal,payload)
    if task=='execute': return ads.execute(journal,payload['operation_id'])
    if task=='reconcile': return ads.reconcile(journal,payload['operation_id'])
    if task=='report-request': return ads.report_request(payload['start_date'],payload['end_date'])
    if task in {'report-status','report-download'}:
        result=ads.report_status(payload['report_id'])
        if task=='report-status' or result.get('status')!='COMPLETED':
            # Presigned URLs are credentials. Never print/store them as receipts.
            return {k:v for k,v in result.items() if k not in {'url','location'}}
        rows=download_report(result['url'])
        return {'rows':rows,'identity':ads.identity(),'report_id':payload['report_id'],'observed_at':now().isoformat(),
                'synthetic':False,'attribution_complete':False,'income':None}
    raise ValueError('Unknown Amazon Ads task')
