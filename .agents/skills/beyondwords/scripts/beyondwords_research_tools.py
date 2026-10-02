"""Structured transport for the existing permission-scoped research implementation."""
from pathlib import Path
import publishing_project as project
from publishing_research import ResearchStore


def execute(workspace,project_id,revision,payload):
    if not workspace or not project_id:raise ValueError('Select a project')
    store=ResearchStore(Path(workspace),project_id);task=payload['task']
    if task not in {'brief','status','policy-status'}:project.require_revision(revision)
    status='OK'
    if task=='enable':data=store.enable(revision,payload['context'],synthetic=payload.get('synthetic',False))
    elif task=='browser-request':
        from beyondwords_browser_handoff import request
        data=request(store,revision,payload)
    elif task=='browser-import':
        from beyondwords_browser_handoff import accept
        body=project.load_input(Path(payload['file'])) if payload.get('file') else b''
        screenshot=project.load_input(Path(payload['screenshot_file'])) if payload.get('screenshot_file') else None
        data=accept(store,revision,payload['packet'],payload['receipt'],body,screenshot=screenshot)
        status=data['research']['captures'][-1]['status']
    elif task=='access':data=store.add_access(revision,payload['access'])
    elif task=='import':
        data=store.import_html(revision,payload['access_id'],payload['url'],project.load_input(Path(payload['file'])),payload['observed_at'],payload['expected'])
        status=data['research']['captures'][-1]['status']
    elif task=='capture':
        data=store.capture_book(revision,payload['access_id'],payload['url'],payload['expected'])
        status=data['research']['captures'][-1]['status']
    elif task=='discover':
        data=store.discover(revision,payload['access_id'],payload['url']);status=data['research']['discovery'][-1]['status']
    elif task=='brief':data=store.brief(payload.get('max_age_hours',48))
    elif task=='policy-import':
        data=store.import_policy(revision,payload['access_id'],payload['policy_id'],payload['url'],project.load_input(Path(payload['file'])),payload['observed_at']);status='NEEDS_REVIEW'
    elif task=='policy-capture':
        before=len(store.read()['research'].get('policy_attempts',[]))
        data=store.capture_policy(revision,payload['access_id'],payload['policy_id'],payload['url'])
        attempts=data['research'].get('policy_attempts',[])
        status=attempts[-1]['status'] if len(attempts)>before else ('BLOCKED' if data['research']['policies'][-1]['status']=='BLOCKED' else 'NEEDS_REVIEW')
    elif task=='policy-review':data=store.review_policy(revision,payload['policy_id'],payload['sha256'],payload['reviewer'],payload['notes'])
    elif task=='policy-status':data=store.policy_status(payload['policy_id'])
    elif task=='status':data=store.read()
    else:raise ValueError('Unknown research task')
    return {**data,'operation_status':status}
