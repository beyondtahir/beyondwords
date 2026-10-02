"""Optional read-only Chromium transport. No login, JavaScript, stealth or bypass."""
from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlsplit, unquote, urljoin

MAX_BYTES = 5 * 1024 * 1024


class AccessError(ValueError): pass


def check_url(url, prefix, *, resolve=True):
    def parse(value):
        if not isinstance(value,str) or any(c.isspace() or ord(c)<32 for c in value) or '\\' in value:
            raise AccessError('Invalid URL')
        try:
            parts=urlsplit(value)
            port=parts.port
        except ValueError as exc: raise AccessError('Invalid URL') from exc
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or port not in (None,443) or parts.fragment:
            raise AccessError('Only public HTTPS URLs without credentials or fragments are supported')
        path=parts.path or '/'
        for _ in range(4):
            decoded=unquote(path)
            if decoded==path: break
            path=decoded
        if '%' in path or '\\' in path or any(x in {'.','..'} for x in path.split('/')):
            raise AccessError('Ambiguous or traversing path denied')
        host=parts.hostname.lower().rstrip('.')
        if host!=parts.hostname or host=='localhost' or host.endswith(('.localhost','.local','.internal')):
            raise AccessError('Local or ambiguous host denied')
        try: address=ipaddress.ip_address(host)
        except ValueError: address=None
        if address is not None and not address.is_global: raise AccessError('Private address denied')
        return parts,host,path
    parts,host,path=parse(url); scope,scopehost,scopepath=parse(prefix)
    if host!=scopehost or not (path==scopepath or path.startswith(scopepath.rstrip('/')+'/')):
        raise AccessError('URL outside reviewed source scope')
    if scope.query and parts.query!=scope.query: raise AccessError('Query outside reviewed source scope')
    if resolve:
        try: addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        except OSError as exc: raise AccessError('DNS lookup failed') from exc
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise AccessError('Non-public DNS address denied')
    return url


def guarded_fetch(url,prefix,fetch,*,resolve=True,max_redirects=5):
    """Fetch must disable automatic redirects. Every next hop is validated first."""
    chain=[]
    for _ in range(max_redirects+1):
        check_url(url,prefix,resolve=resolve)
        response=fetch(url)
        status=response['status']; headers={k.lower():v for k,v in response.get('headers',{}).items()}
        chain.append({'url':url,'status':status})
        if status in {301,302,303,307,308}:
            location=headers.get('location')
            if not location: raise AccessError('Redirect has no location')
            url=urljoin(url,location); continue
        body=response.get('body',b'')
        if not isinstance(body,bytes) or len(body)>MAX_BYTES: raise AccessError('Response exceeds capture limit')
        if headers.get('content-type') and not any(x in headers['content-type'].lower() for x in ('text/html','text/plain','application/xhtml+xml')):
            raise AccessError('Unsupported source media type')
        return {'status':status,'headers':headers,'body':body,'final_url':url,'redirects':chain}
    raise AccessError('Redirect limit exceeded')


def doctor():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'installed':False,'configured':False,'reachable':None,'authorized':None,'status':'UNAVAILABLE'}
    from pathlib import Path
    with sync_playwright() as p:
        configured=Path(p.chromium.executable_path).is_file()
    return {'installed':True,'configured':configured,'reachable':None,'authorized':None,
            'status':'AVAILABLE' if configured else 'UNAVAILABLE','scope':'Read-only; each source requires reviewed permission'}


def capture(url,prefix,*,timeout_ms=20000):
    from publishing_extract import blocked
    try:
        check_url(url,prefix)
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'status':'UNAVAILABLE','error':'Playwright is not installed','body':b''}
    except AccessError as exc:
        return {'status':'BLOCKED','error':str(exc),'body':b''}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,chromium_sandbox=True)
            try:
                context=browser.new_context(java_script_enabled=False,service_workers='block',accept_downloads=False)
                page=context.new_page(); result={}
                def route_handler(route):
                    if route.request.method!='GET' or route.request.resource_type!='document' or route.request.frame!=page.main_frame:
                        route.abort(); return
                    try:
                        def fetch(target):
                            response=route.fetch(url=target,max_redirects=0,timeout=timeout_ms,headers={"Cookie":""})
                            try:
                                headers=response.headers
                                if int(headers.get('content-length','0'))>MAX_BYTES: raise AccessError('Response exceeds capture limit')
                                return {'status':response.status,'headers':headers,'body':response.body()}
                            finally: response.dispose()
                        result.update(guarded_fetch(url,prefix,fetch))
                        # No original response headers/cookies/refresh directives enter the page.
                        route.fulfill(status=200,content_type='text/plain',body='Capture completed')
                    except Exception as exc:
                        result.update(error=type(exc).__name__+': '+str(exc),error_status='BLOCKED' if isinstance(exc,AccessError) else 'ERROR'); route.abort()
                page.route('**/*',route_handler)
                try: page.goto(url,wait_until='domcontentloaded',timeout=timeout_ms*2)
                except Exception:
                    if not result: raise
                if result.get('error'): return {'status':result.get('error_status','ERROR'),'error':result['error'],'body':b''}
                raw=result.get('body',b'')
                is_blocked=result.get('status') in {401,403,429} or blocked(raw.decode('utf-8',errors='replace'))
                result.pop('headers',None)  # Never persist response cookies or arbitrary headers.
                return {**result,'http_status':result.get('status'),'status':'BLOCKED' if is_blocked else ('OK' if result.get('status')==200 else 'ERROR')}
            finally: browser.close()
    except Exception as exc:
        return {'status':'ERROR','error':type(exc).__name__+': '+str(exc),'body':b''}
