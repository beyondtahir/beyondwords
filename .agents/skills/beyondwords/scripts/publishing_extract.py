"""Conservative, offline extraction. HTML is untrusted data, never instructions."""
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack = []; self.nodes = []; self.parts = []; self.hidden = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if len(self.nodes)>50000 or len(self.stack)>256: raise ValueError('HTML complexity limit exceeded')
        attrs = dict(attrs)
        hidden = tag in {'script', 'style', 'template', 'noscript'} or 'hidden' in attrs or attrs.get('aria-hidden') == 'true' or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)',attrs.get('style',''),re.I))
        node = {'tag': tag, 'attrs': attrs, 'parts': [], 'hidden': hidden or any(n['hidden'] for n in self.stack)}
        self.nodes.append(node)
        if tag not in {'input','link','meta','img','br','hr','source','wbr'}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]; break

    def handle_data(self, data):
        if any(n['hidden'] for n in self.stack): return
        self.parts.append(data)
        for node in self.stack: node['parts'].append(data)

    @staticmethod
    def text(node): return ' '.join(' '.join(node['parts']).split())

    def by_id(self, *ids):
        return [n for n in self.nodes if n['attrs'].get('id') in ids and not n['hidden']]


def visible_text(html):
    return ' '.join(' '.join(Document(html).parts).split())


def blocked(html):
    text = visible_text(html).lower()
    return any(x in text for x in ('robot check', 'enter the characters you see below', 'verify you are human', 'access denied', 'captcha'))


def extract_book(html, url, expected=None):
    expected = expected or {}
    doc = Document(html)
    result = dict(asin=None, title=None, marketplace=None, format=None, price=None, currency=None,
                  overall_rank=None, overall_rank_store=None, category_ranks=[], ranking_list=None,
                  edition_verified=False, rating=None, rating_count=None, review_count=None,
                  rating_scope='UNKNOWN', publication_date=None, issues=[], support={})
    host = urlsplit(url).hostname
    markets = {'www.amazon.com':'US','amazon.com':'US','www.amazon.co.uk':'UK','www.amazon.de':'DE','www.amazon.ca':'CA','www.amazon.com.au':'AU','www.amazon.in':'IN'}
    result['marketplace'] = markets.get(host)
    asins = {n['attrs'].get('value','').upper() for n in doc.by_id('ASIN') if n['tag']=='input'}
    asins = {a for a in asins if re.fullmatch(r'[A-Z0-9]{10}', a)}
    if len(asins)==1:
        result['asin'] = asins.pop(); result['support']['asin'] = 'input#ASIN value'
    identities=[]
    identity_urls=[url]+[n['attrs'].get('href','') for n in doc.nodes if n['tag']=='link' and n['attrs'].get('rel')=='canonical']
    for identity_url in identity_urls:
        found=re.search(r'/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)',identity_url)
        if found: identities.append(found.group(1).upper())
    conflicting_identity=bool(result['asin'] and any(value!=result['asin'] for value in identities))
    if conflicting_identity: result['issues'].append('conflicting_product_identity')
    titles = {doc.text(n) for n in doc.by_id('productTitle') if doc.text(n)}
    if len(titles)==1: result['title'] = titles.pop(); result['support']['title'] = 'productTitle'
    ratings=set()
    for n in doc.by_id('acrPopover'):
        value=n['attrs'].get('title','') or doc.text(n)
        found=re.fullmatch(r'([0-5](?:\.[0-9])?) out of 5 stars',value.strip())
        if found and float(found.group(1))<=5:ratings.add(found.group(1))
    if len(ratings)==1:result['rating']=ratings.pop();result['support']['rating']='Visible acrPopover English star label'
    elif len(ratings)>1:result['issues'].append('ambiguous_rating')
    counts=set()
    for n in doc.by_id('acrCustomerReviewText'):
        found=re.fullmatch(r'([0-9][0-9,]*)\s+(ratings?|reviews?)',doc.text(n),re.I)
        if found:counts.add((int(found.group(1).replace(',','')),found.group(2).lower().rstrip('s')))
    if len(counts)==1:
        count,kind=counts.pop();result[kind+'_count']=count;result['support'][kind+'_count']='acrCustomerReviewText visible '+kind+' label'
    elif len(counts)>1:result['issues'].append('ambiguous_rating_count')
    if result['rating'] is not None or result['rating_count'] is not None or result['review_count'] is not None:
        result['rating_scope']='LISTING_AGGREGATE_EDITION_SCOPE_UNKNOWN'
    # Do not interpret locale-dependent dates; retain only explicit ISO dates with a label.
    dates=set()
    for n in doc.nodes:
        if n['hidden'] or n['tag'] not in {'li','tr'}:continue
        match=re.fullmatch(r'Publication date\s*:?\s*(\d{4}-\d{2}-\d{2})',doc.text(n),re.I)
        if match:
            try:
                from datetime import date
                dates.add(date.fromisoformat(match.group(1)).isoformat())
            except ValueError:pass
    if len(dates)==1:result['publication_date']=dates.pop();result['support']['publication_date']='Explicit ISO publication-date row'
    formats = set()
    for node in doc.by_id('selected-format','productSubtitle','tmmSwatches'):
        # The swatches container includes alternate offers: only its selected descendants count.
        if node['attrs'].get('id') == 'tmmSwatches': continue
        value = doc.text(node).lower()
        for label, fmt in [('paperback','paperback'),('hardcover','hardcover'),('kindle edition','kindle'),('ebook','kindle')]:
            if re.search(r'\b'+label+r'\b', value): formats.add(fmt)
    for node in doc.nodes:
        if node['hidden']: continue
        if 'selected' in node['attrs'].get('class','').split() or node['attrs'].get('aria-checked')=='true':
            value=doc.text(node).lower()
            for label,fmt in [('paperback','paperback'),('hardcover','hardcover'),('kindle','kindle')]:
                if re.search(r'\b'+label+r'\b',value): formats.add(fmt)
    if len(formats)==1: result['format']=formats.pop(); result['support']['format']='selected edition label'
    elif len(formats)>1: result['issues'].append('ambiguous_format')
    prices=set()
    for node in doc.by_id('priceblock_ourprice','priceblock_dealprice','kindle-price','selected-price'):
        value=doc.text(node)
        match=re.fullmatch(r'\s*([$£€])\s*([0-9]+(?:\.[0-9]{2})?)\s*',value)
        if match: prices.add(match.groups())
    if len(prices)==1:
        symbol, amount=prices.pop()
        result['price']=amount
        result['currency']={'£':'GBP','€':'EUR'}.get(symbol) or ('USD' if result['marketplace']=='US' and symbol=='$' else None)
        result['support']['price']=symbol+amount
    elif len(prices)>1: result['issues'].append('ambiguous_price')
    rank_texts=[]
    for node in doc.nodes:
        if node['hidden']: continue
        text=doc.text(node)
        if node['attrs'].get('id') in {'SalesRank','detailBulletsWrapper_feature_div'} or (node['tag'] in {'tr','li'} and re.search(r'Best Sellers Rank|Amazon Bestsellers Rank',text,re.I)):
            rank_texts.append(text)
    rank_text=' '.join(dict.fromkeys(rank_texts))
    ranks=[]
    for match in re.finditer(r'#([0-9][0-9,]*)\s+in\s+([^#]+)',rank_text,re.I):
        rank=int(match.group(1).replace(',','')); label=match.group(2).strip()
        if rank <= 0: continue
        label=re.split(r'\(See |See Top|Customer Reviews',label,flags=re.I)[0].strip()
        paidfree=re.search(r'\((Paid|Free)\)',label,re.I)
        listing=paidfree.group(1).lower() if paidfree else None
        category=re.sub(r'\((?:Paid|Free)\)','',label,flags=re.I).strip()
        ranks.append((rank,category,listing))
    ranks=list(dict.fromkeys(ranks))
    roots=[r for r in ranks if r[1].lower() in {'books','kindle store'}]
    result['category_ranks']=[{'rank':r,'category':c,'ranking_list':l} for r,c,l in ranks if c.lower() not in {'books','kindle store'}]
    if len(roots)==1:
        result['overall_rank'],result['overall_rank_store'],result['ranking_list']=roots[0]
        result['support']['overall_rank']=rank_text[:2000]
    elif len(roots)>1: result['issues'].append('ambiguous_overall_rank')
    if len(roots)==1 and result['format'] and ((result['format']=='kindle') != (roots[0][1].lower()=='kindle store')):
        result['overall_rank']=None; result['ranking_list']=None
        result['issues'].append('rank_format_mismatch')
    if result['category_ranks']: result['support']['category_ranks']=rank_text[:2000]
    if not titles and not asins and not result['asin']: result['issues'].append('layout_unrecognized')
    if blocked(html): result['issues'].append('blocked_page')
    aliases={'ebook':'kindle','kindle edition':'kindle'}
    fmt=aliases.get(str(expected.get('format','')).lower(),str(expected.get('format','')).lower())
    # Caller must select an edition; presence of a product-like page alone is insufficient.
    required=bool(expected.get('asin') and fmt and result['asin'] and result['format'])
    match=required and expected['asin'].upper()==result['asin'] and fmt==result['format']
    if expected.get('marketplace') and expected['marketplace']!=result['marketplace']: match=False
    if (expected.get('asin') and expected['asin'].upper()!=result['asin']) or (fmt and fmt!=result['format']):
        result['issues'].append('edition_mismatch')
    result['edition_verified']=bool(match and not conflicting_identity and 'blocked_page' not in result['issues'])
    return result
