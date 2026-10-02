"""Attended KDP browser driver. Discovers actual controls; contains no invented upload API.

Launch in a visible terminal, log in directly in the isolated browser, then use
snapshot/prepare/execute commands. Browser cookies are never exported. Host browser
tools remain another route when this local runtime is unavailable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse

from beyondwords_connected import (Journal, ConnectionError, canonical, digest, now,
                                  clean_text, operator_confirmation)
from publishing_core import scoped_path


SNAPSHOT_JS = r'''() => {
  const visible = el => !!(el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  const names = el => (el.labels?.[0]?.innerText || el.getAttribute('aria-label') || el.innerText || el.getAttribute('title') || el.getAttribute('name') || '').trim().slice(0,250);
  return Array.from(document.querySelectorAll('input,textarea,select,button,[role=button]'))
    .filter(el => visible(el) || el.matches('input[type=file]'))
    .filter(el => !['password','hidden'].includes(el.type))
    .map((el,index) => {
      el.setAttribute('data-beyondwords-control',String(index));
      return {index,tag:el.tagName.toLowerCase(),type:el.type || '',name:names(el),disabled:el.disabled || false,
        state:{value:el.type==='file' ? Array.from(el.files || []).map(f=>({name:f.name,size:f.size})) : (el.value || ''),checked:el.checked || false},
        options:el.tagName==='SELECT' ? Array.from(el.options).map(o=>({value:o.value,label:o.text})) : []};
    });
}'''
SENSITIVE = re.compile(r'password|one.time|verification.code|bank|routing|taxpayer|tax.ident|credit.card|social.security|passport|telephone|phone.number|email.address|account.password', re.I)


CHANNELS = {
    'kdp': {'start':'https://kdp.amazon.com/en_US/bookshelf','actions':{'kdp.amazon.com'},'login':{'kdp.amazon.com','account.kdp.amazon.com','www.amazon.com','amazon.com'}},
    'lulu': {'start':'https://www.lulu.com/','actions':{'www.lulu.com'},'login':{'www.lulu.com','lulu.com','account.lulu.com'}},
    'etsy': {'start':'https://www.etsy.com/','actions':{'www.etsy.com'},'login':{'www.etsy.com','etsy.com'}},
    'shopify': {'start':'https://admin.shopify.com/','actions':{'admin.shopify.com'},'login':{'admin.shopify.com','accounts.shopify.com'}},
}


class Publisher:
    def __init__(self, page, journal, account_label, *, synthetic=False, channel='kdp'):
        if channel not in CHANNELS:raise ValueError('Unsupported publishing channel')
        self.channel=channel
        self.adapter=channel+'_browser'
        self.page,self.journal,self.account_label=page,journal,clean_text(account_label)
        self.synthetic=synthetic
        self._snapshot=None

    def check_location(self):
        p=urllib.parse.urlsplit(self.page.url)
        if self.synthetic:
            if p.scheme not in {'about','file','http'} or (p.scheme=='http' and p.hostname not in {'localhost','127.0.0.1'}):
                raise ConnectionError('SYNTHETIC_SCOPE','Synthetic browser tests cannot visit live publishing sites')
        elif p.scheme!='https' or p.hostname not in CHANNELS[self.channel]['actions'] or p.port not in {None,443} or p.username or p.password:
            raise ConnectionError('LOGIN_OR_DESTINATION','Log in directly, then return to the selected publishing channel. No action sent')
        return self.page.url

    def snapshot(self):
        url=self.check_location()
        controls=self.page.evaluate(SNAPSHOT_JS)
        if not isinstance(controls,list) or len(controls)>500:
            raise ValueError('Unsupported page layout')
        # Do not harvest input values, cookies, full account text, hidden fields or screenshots.
        safe=[r for r in controls if not SENSITIVE.search(r['name'])]
        for control in safe:
            control['state_sha256']=digest(control.pop('state'))
        data={'url':url,'controls':safe,'account_label':self.account_label,'synthetic':self.synthetic,'channel':self.channel}
        data['sha256']=digest(data);self._snapshot=data
        return {**data,'observed_at':now().isoformat(),'untrusted_page_data':True,
                'account_identity':'Owner-selected label; not independently authenticated identity',
                'publication_ready':False}

    def prepare(self, value):
        snap=self.snapshot()
        if value.get('snapshot_sha256')!=snap['sha256']:
            raise ConnectionError('LAYOUT_CHANGED','Page controls changed; inspect a fresh snapshot')
        action=value['action']
        if action not in {'fill','select','check','upload','click'}:
            raise ValueError('Unsupported publishing action')
        matches=[r for r in snap['controls'] if r['index']==value['control']]
        if len(matches)!=1 or matches[0]['disabled']:
            raise ValueError('Select one enabled observed control')
        control=matches[0]
        if not control['name']:
            raise ValueError('Unlabelled controls need attended platform use; do not guess')
        plan={'project_id':self.journal.project_id,'adapter':self.adapter,'channel':self.channel,'synthetic':self.synthetic,
              'account_label':self.account_label,'url':snap['url'],'snapshot_sha256':snap['sha256'],
              'action':action,'control':control,'reason':clean_text(value['reason'],1000)}
        if action=='fill':
            if control['tag'] not in {'input','textarea'} or control['type'] in {'file','checkbox','radio','submit','button'}:
                raise ValueError('Not an editable text control')
            text=value['value']
            if not isinstance(text,str) or not text or len(text)>10000 or any(ord(c)<32 and c not in '\n\t' for c in text):
                raise ValueError('Bounded actual metadata text required')
            plan['value']=text
        elif action=='select':
            if control['tag']!='select' or value['value'] not in [o['value'] for o in control['options']]:
                raise ValueError('Choose one observed select option')
            plan['value']=value['value']
        elif action=='check':
            if control['type'] not in {'checkbox','radio'} or type(value['value']) is not bool:
                raise ValueError('Checkbox/radio requires an explicit boolean decision')
            plan['value']=value['value']
        elif action=='upload':
            if control['type']!='file': raise ValueError('Not an observed file input')
            path=scoped_path(Path(value['file']))
            if not path.is_file() or path.stat().st_size>100*1024*1024 or path.suffix.lower() not in {'.epub','.pdf','.docx','.kpf','.jpg','.jpeg','.png'}:
                raise ValueError('Select a reviewed publishing file, at most 100 MiB')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=value['sha256']:
                raise ValueError('Upload file differs from reviewed hash')
            plan.update(file=str(path),sha256=value['sha256'],size=len(raw))
        elif action=='click':
            if control['tag']!='button' and control['type'] not in {'submit','button'}:
                raise ValueError('Only an observed button can be clicked')
            plan['consequence']='SUBMISSION_OR_PUBLICATION' if re.search(r'publish|submit',control['name'],re.I) else 'ACCOUNT_PAGE_ACTION'
            # Consequential decisions are explicit rather than inferred from the button text.
            if plan['consequence']=='SUBMISSION_OR_PUBLICATION':
                review=value.get('release_review',{})
                required={'files_sha256','metadata_sha256','pricing','territories','ai_disclosure','rights','editorial','reader','platform_preview','account_scope'}
                if set(review)!=required or not all(isinstance(v,str) and v.strip() for v in review.values()):
                    raise ValueError('Submission requires a complete owner-reviewed release record')
                plan['release_review']=review
        return self.journal.prepare(plan)

    def execute(self, op_id, *, confirmer=operator_confirmation):
        op=self.journal.get(op_id);p=op['plan']
        if op['state']!='PREPARED' or not op['approval_current']:
            raise ConnectionError('RECONCILE_REQUIRED','This action is expired or already dispatched')
        if p.get('adapter')!=self.adapter or p.get('channel','kdp')!=self.channel or p['synthetic']!=self.synthetic or p['account_label']!=self.account_label:
            raise ValueError('Publishing account/environment mismatch')
        snap=self.snapshot()
        if snap['url']!=p['url'] or snap['sha256']!=p['snapshot_sha256']:
            raise ConnectionError('LAYOUT_CHANGED','Publishing page changed after preparation')
        signature=confirmer(op)
        # Verify once more after a human may have spent minutes reading the exact plan.
        if self.snapshot()['sha256']!=p['snapshot_sha256']:
            raise ConnectionError('LAYOUT_CHANGED','Publishing page changed during review')
        locator=self.page.locator('[data-beyondwords-control="'+str(p['control']['index'])+'"]')
        if locator.count()!=1: raise ValueError('Control no longer unique')
        raw=None
        if p['action']=='upload':
            path=scoped_path(Path(p['file']))
            if path.stat().st_size!=p['size']: raise ValueError('Reviewed upload changed')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=p['sha256']: raise ValueError('Reviewed upload changed')
        self.journal.claim(op_id,signature)
        try:
            if p['action']=='fill': locator.fill(p['value'],timeout=10000)
            elif p['action']=='select': locator.select_option(p['value'],timeout=10000)
            elif p['action']=='check': locator.set_checked(p['value'],timeout=10000)
            elif p['action']=='upload':
                # Freeze approved bytes instead of letting the browser reread a mutable path.
                import mimetypes
                locator.set_input_files({'name':Path(p['file']).name,'mimeType':mimetypes.guess_type(p['file'])[0] or 'application/octet-stream','buffer':raw},timeout=15000)
            elif p['action']=='click': locator.click(timeout=15000)
            receipt={'browser_action_completed':True,'action':p['action'],'at':now().isoformat(),
                     'synthetic':self.synthetic,'platform_conversion':'UNKNOWN','submitted':'UNKNOWN',
                     'publication_status':'UNKNOWN','next_action':'Inspect the actual conversion/preview/Bookshelf status; a click is not publication'}
            state='CONFIRMED'
        except Exception:
            state='UNKNOWN';receipt={'browser_action_completed':'UNKNOWN','publication_status':'UNKNOWN',
                                     'next_action':'Inspect the account and reconcile; do not blindly repeat this operation'}
        return self.journal.finish(op_id,state,receipt)

    def observe(self, op_id, exact_text):
        """Capture a requested status text on the currently visible page, never infer publication."""
        self.check_location();op=self.journal.get(op_id)
        if op['plan'].get('adapter')!=self.adapter or op['plan']['account_label']!=self.account_label or op['synthetic']!=self.synthetic:
            raise ValueError('Observation belongs to another publishing scope')
        clean_text(exact_text,200)
        loc=self.page.get_by_text(exact_text,exact=True)
        count=loc.count()
        visible=count==1 and loc.is_visible()
        result={'operation_id':op_id,'url':self.page.url,'exact_text':exact_text,'visible_unique_match':visible,
                'at':now().isoformat(),'synthetic':self.synthetic,'publication_status':'UNVERIFIED',
                'warning':'Page text alone does not establish edition/ASIN or public availability. No mutation retry authorized.'}
        with self.journal.db() as db:
            self.journal._event(db,op_id,'PAGE_OBSERVATION',result)
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--project-id',required=True)
    parser.add_argument('--account-label',required=True)
    parser.add_argument('--channel',choices=sorted(CHANNELS),default='kdp')
    args=parser.parse_args(argv)
    if not sys.stdin.isatty(): raise SystemExit('Attended terminal required; no unattended login or approval bypass')
    from playwright.sync_api import sync_playwright
    journal=Journal(args.directory,args.project_id)
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(headless=False,chromium_sandbox=True)
        context=browser.new_context(accept_downloads=False,service_workers='block')
        page=context.new_page()
        # Human login navigation is allowed only on Amazon/KDP. No account session export.
        def guard(route):
            request=route.request
            if request.is_navigation_request() and request.frame==page.main_frame:
                p=urllib.parse.urlsplit(request.url)
                if p.scheme!='https' or p.hostname not in CHANNELS[args.channel]['login']:
                    route.abort();return
            route.continue_()
        page.route('**/*',guard)
        page.goto(CHANNELS[args.channel]['start'],wait_until='domcontentloaded')
        driver=Publisher(page,journal,args.account_label,channel=args.channel)
        print('Sign in directly in the browser. Enter snapshot, quit, or a prepared JSON command. No passwords in terminal.')
        try:
            while True:
                line=input('beyondwords> ').strip()
                if line=='quit': break
                try:
                    if line=='snapshot': result=driver.snapshot()
                    else:
                        data=json.loads(line);task=data.pop('task')
                        if task=='prepare': result=driver.prepare(data)
                        elif task=='execute': result=driver.execute(data['operation_id'])
                        elif task=='observe': result=driver.observe(data['operation_id'],data['exact_text'])
                        else: raise ValueError('Unknown attended publishing command')
                    print(json.dumps(result,indent=2,ensure_ascii=True))
                except Exception as exc:
                    print(canonical({'status':'BLOCKED','error_code':getattr(exc,'code',type(exc).__name__),
                                     'message':str(exc) if isinstance(exc,ValueError) else 'Browser operation failed; inspect the page'}))
        finally:
            context.close();browser.close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
