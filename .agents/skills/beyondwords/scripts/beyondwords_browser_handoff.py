"""Permission-bound handoff to a real host browser and atomic observation import.

The host performs its actual browser call. This module neither invents a tool nor
authenticates what the host reports. Request hashes bind the scope and revision.
"""
import copy
from uuid import uuid4
import publishing_core as core
import publishing_project as project
from publishing_browser import check_url
from publishing_extract import blocked, extract_book

PURPOSES={'listing','review','sample','discovery','reference'}
RECEIPT_KEYS={'host','tool','receipt_reference','observed_at','status','final_url','content_type','body_sha256','scope','redirects','screenshot_sha256'}

def request(store,revision,p):
    state=store.read();project.require_revision(revision)
    if state['revision']!=revision:raise project.ProjectError('STALE_REVISION','Read the current research project')
    operation=p.get('operation','collect')
    if operation not in {'collect','import'}:raise ValueError('Choose collection or authorized import')
    permission=store._permission(state,p['access_id'],p['url'],operation)
    if operation=='collect' and permission['synthetic']:raise ValueError('Synthetic projects cannot collect live evidence')
    purpose=p.get('purpose','listing')
    if purpose not in PURPOSES:raise ValueError('Unsupported browser evidence purpose')
    expected=p.get('expected',{})
    if not isinstance(expected,dict) or set(expected)-{'asin','format','marketplace'} or any(not isinstance(x,str) for x in expected.values()):raise ValueError('Provide selected edition strings only; missing values remain UNKNOWN')
    d=dict(project_id=store.project_id,workspace_sha256=project.digest(str(store.root.resolve()).encode()),revision=revision,access_id=p['access_id'],url=p['url'],operation=operation,purpose=purpose,expected=expected,
           permission_sha256=project.digest(project.canonical(permission)),synthetic=permission['synthetic'])
    return dict(request=d,request_sha256=project.digest(project.canonical(d)),backend='normal_browser',performed=False,
                retention=permission['retention'],next_action='Use the real host browser within the reviewed scope; save only permitted observed content and its actual receipt, then browser-import. A denied source must not be retried through another provider.')

def accept(store,revision,packet,receipt,body,*,screenshot=None):
    if not isinstance(packet,dict) or not isinstance(receipt,dict):raise ValueError('Request packet and real observation receipt required')
    d=packet.get('request',{});current=request(store,revision,d)
    if d!=current['request'] or packet.get('request_sha256')!=current['request_sha256']:raise ValueError('Browser request changed or is stale; reconcile before importing')
    if set(receipt)-RECEIPT_KEYS:raise ValueError('Unexpected receipt metadata; never import cookies, headers, credentials or browser state')
    for key in ('host','tool','receipt_reference','scope'):core.text(receipt.get(key),key,2000)
    status=receipt.get('status')
    if status not in {'OK','PARTIAL','BLOCKED','ERROR','UNAVAILABLE'}:raise ValueError('Record the actual browser outcome')
    when=core.timestamp(receipt['observed_at'],'observed_at')
    if when>core.timestamp(store.clock(),'now'):raise ValueError('Future observation')
    if receipt.get('content_type') not in {'text/html','text/plain'}:raise ValueError('Only explicit UTF-8 HTML or text observations are accepted')
    if not isinstance(body,bytes) or len(body)>project.MAX_BYTES or project.digest(body)!=receipt.get('body_sha256'):raise ValueError('Observation bytes do not match receipt hash or exceed the limit')
    if status in {'OK','PARTIAL'} and not body:raise ValueError('Successful browser observation must contain actual evidence')
    text=body.decode('utf-8')
    redirects=receipt.get('redirects',[])
    if not isinstance(redirects,list) or len(redirects)>10:raise ValueError('Bounded observed redirect list required')
    image_bytes=None
    if screenshot is not None:
        if not isinstance(screenshot,bytes) or not 0<len(screenshot)<=project.MAX_BYTES or project.digest(screenshot)!=receipt.get('screenshot_sha256'):raise ValueError('Screenshot does not match receipt')
        import io
        from PIL import Image
        with Image.open(io.BytesIO(screenshot)) as im:
            if im.format not in {'PNG','JPEG'} or im.width*im.height>25000000:raise ValueError('Bounded PNG/JPEG screenshot required')
            im.verify()
        image_bytes=screenshot
    elif receipt.get('screenshot_sha256'):raise ValueError('Receipt declares a screenshot that was not supplied')
    with store._change(revision,'capture_book_evidence') as (conn,state):
        permission=store._permission(state,d['access_id'],d['url'],d['operation'])
        for url in [receipt['final_url'],*redirects]:check_url(url,permission['url_prefix'],resolve=False)
        if d['operation']=='collect' and when<core.timestamp(permission['reviewed_at'],'reviewed_at'):raise ValueError('Collection occurred before the recorded permission review')
        actual_status='BLOCKED' if blocked(text) or status=='BLOCKED' else status
        can_extract=actual_status in {'OK','PARTIAL'} and d['purpose']=='listing' and receipt['content_type']=='text/html'
        item=extract_book(text,receipt['final_url'],d['expected']) if can_extract else dict(edition_verified=False,issues=['Listing extraction unavailable for this observation scope'])
        if actual_status=='OK' and d['purpose']=='listing' and not item['edition_verified']:actual_status='PARTIAL'
        artifact=store._source_artifact(conn,state,permission,body,'research_source') if body else None
        image_artifact=store._artifact(conn,state,'image-'+uuid4().hex,'research_image',image_bytes,permission['basis'],'observed-browser-screenshot',synthetic=permission['synthetic'],binary=True) if image_bytes else None
        transport={**copy.deepcopy(receipt),'backend':'normal_browser','request_sha256':current['request_sha256'],'host_reported':True,'independently_verified':False}
        item.update(capture_id='capture-'+uuid4().hex,source_url=receipt['final_url'],requested_url=d['url'],observed_at=receipt['observed_at'],recorded_at=store.clock(),
                    source_sha256=artifact['sha256'] if artifact else None,artifact_id=artifact['artifact_id'] if artifact else None,
                    screenshot_sha256=image_artifact['sha256'] if image_artifact else None,screenshot_artifact_id=image_artifact['artifact_id'] if image_artifact else None,
                    access_id=d['access_id'],synthetic=permission['synthetic'],status=actual_status,selected_edition=d['expected'],purpose=d['purpose'],scope=receipt['scope'],
                    provenance='host_browser_observation' if d['operation']=='collect' or permission['synthetic'] else 'authorized_browser_import',retention=permission['retention'],transport=transport)
        store._research(state)['captures'].append(item)
    return state
