#!/usr/bin/env python3
"""Install only authored runtime wrappers; never open or write a catalog database."""
from pathlib import Path
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path.home()/'Library/Application Support/FirstPair Lightroom'
LABEL = 'com.firstpair.lightroom.performance-startup'
MENU = 'FirstPair) Apply FirstPair performance fixes.lua'
VERSION = '15.6'
RENEWAL_AUTHORIZATION = 'FirstPair authorized bounded per-invocation renewal\n'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):
    path = Path(path);tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def safe_path(value):
    s = str(Path(value).expanduser().absolute())
    if any(c in s for c in "\n\r\x00\"'\\"):
        raise ValueError('Paths must not contain quotes, backslashes or control characters')
    return Path(s)

def pids(app):
    executable = str(Path(app)/'Contents/MacOS/Adobe Lightroom Classic')
    out = subprocess.run(['/bin/ps','-axo','pid=,comm='],capture_output=True,text=True,check=True).stdout
    return [int(line.strip().split(None,1)[0]) for line in out.splitlines()
            if line.strip().endswith(executable)]

def startup_plist(config):
    root=Path(config['root'])
    return {'Label':LABEL,'ProgramArguments':[config['launcher_uv'],'run','--offline','--no-project','--python',config['launcher_python'],'python',str(root/'manage.py'),'watch','--root',str(root)],
            'StartInterval':30,'RunAtLoad':True,'ProcessType':'Background','WorkingDirectory':str(root),
            'StandardOutPath':str(root/'launchd.stdout.log'),'StandardErrorPath':str(root/'launchd.stderr.log')}

def render(config):
    root = Path(config['root'])
    values = {'@@ROOT@@':str(root),'@@CATALOG@@':config['catalog'],'@@APP@@':config['app'],
              '@@CATALOG_NAME@@':Path(config['catalog']).name,
              '@@SCHEMA@@':str(config['schema_index']).lower(),
              '@@AFFINITY@@':str(config['affinity']).lower(),
              '@@BACKUP@@':str(config['backup_confirmed']).lower()}
    bases = {}
    for p in (REPO/'templates').rglob('*'):
        if p.is_file() and p.suffix in ('.lua','.sql','.applescript'):
            text = p.read_text()
            for a,b in values.items():text=text.replace(a,b)
            bases[str(p.relative_to(REPO/'templates'))] = text
    pins = json.loads((REPO/'templates/SOURCE-PINS.json').read_text())
    mapping = {v['originalSha256']:hashlib.sha256(bases[k].encode()).hexdigest() for k,v in pins.items()}
    # Native sources hash their dependency bytes. Rebind from original author pins
    # until the acyclic dependency closure reaches a stable fixed point.
    for _ in range(40):
        result = {}
        for name,text in bases.items():
            for old,new in mapping.items():text=text.replace(old,new)
            result[name] = text
        new = {v['originalSha256']:hashlib.sha256(result[k].encode()).hexdigest() for k,v in pins.items()}
        if new == mapping:
            for name,text in result.items():
                if '@@' in text:raise ValueError('Unresolved template variable: '+name)
                if '/Users/' in text and str(root) not in text and config['catalog'] not in text:
                    raise ValueError('Unexpected private path: '+name)
            return result
        mapping = new
    raise ValueError('Dependency pin closure did not converge')

def install(args):
    root=safe_path(args.root);app=safe_path(args.app);catalog=safe_path(args.catalog)
    if not args.backup_confirmed:raise ValueError('Make and verify a closed catalog-family backup, then pass --backup-confirmed')
    info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if info.get('CFBundleShortVersionString') != VERSION:raise ValueError('Only the qualified Lightroom Classic 15.6 version is admitted')
    if not catalog.is_file() or catalog.is_symlink() or catalog.resolve()!=catalog:raise ValueError('Expected canonical regular .lrcat path without symlink aliases')
    if catalog.suffix != '.lrcat':raise ValueError('Catalog must be a .lrcat file')
    if not args.stage_only and pids(app):raise ValueError('Quit Classic normally before installation; no app is stopped by this tool')
    scripts=safe_path(args.scripts_dir or Path.home()/'Library/Application Support/Adobe/Lightroom/Scripts')
    config={'root':str(root),'app':str(app),'catalog':str(catalog),'scripts_dir':str(scripts),
            'schema_index':args.enable_schema_index,'affinity':args.enable_affinity,
            'backup_confirmed':args.backup_confirmed,'version':VERSION,'stage_only':args.stage_only,
            'helper':str(root/'FirstPair Lightroom Performance Helper.app')}
    rendered=render(config)
    if args.dry_run:
        print(json.dumps({'dry_run':True,'template_files':len(rendered),'destination':str(root),
                          'scripts_directory':str(scripts),'affinity_enabled':config['affinity'],
                          'schema_index_enabled':config['schema_index'],'catalog_database_access':False},indent=2));return
    if root.exists():raise ValueError('Destination already exists; verify/disable it, then choose a new owned destination')
    root.mkdir(parents=True,mode=0o700)
    for name,text in rendered.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(0o600)
    shutil.copy2(REPO/'scripts/manage.py',root/'manage.py')
    if not args.stage_only:
        subprocess.run(['/usr/bin/osacompile','-o',config['helper'],str(root/'Helper.applescript')],check=True)
        scripts.mkdir(parents=True,exist_ok=True)
        menu=scripts/MENU
        if menu.exists():raise ValueError('Menu already exists; refusing overwrite')
        shutil.copy2(root/'runtime/menu.lua',menu)
        config['menu']=str(menu)
    uv=shutil.which('uv')
    if not uv:raise ValueError('Install uv and rerun from a clean new destination')
    config['launcher_uv']=uv;config['launcher_python']=sys.executable
    plist=startup_plist(config)
    (root/'startup.plist').write_bytes(plistlib.dumps(plist))
    save(root/'config.json',config)
    watched=[root/name for name in rendered]+[root/'manage.py',root/'config.json',root/'startup.plist',Path(sys.executable),Path(uv),app/'Contents/Info.plist',app/'Contents/MacOS/Adobe Lightroom Classic']
    if not args.stage_only:
        watched += [Path(config['menu'])]+[p for p in Path(config['helper']).rglob('*') if p.is_file()]
    save(root/'manifest.json',{'version':VERSION,'sha256':{str(p):sha(p) for p in watched}})
    print(json.dumps({'installed':str(root),'stage_only':args.stage_only,'automation_enabled':False,
                      'start_again':'Quit/relaunch Classic normally after installing the menu; grant helper permissions; enable only after a verified manual run.'},indent=2))

def verified_config(root):
    root=Path(root);config=json.loads((root/'config.json').read_text());manifest=json.loads((root/'manifest.json').read_text())
    for path,pin in manifest['sha256'].items():
        if sha(path)!=pin:raise ValueError('Pinned input changed: '+Path(path).name)
    if config['root']!=str(root):raise ValueError('Configured installation root changed')
    if plistlib.loads((root/'startup.plist').read_bytes())!=startup_plist(config):raise ValueError('Unexpected startup Label, ProgramArguments or owned launch configuration')
    info=plistlib.loads((Path(config['app'])/'Contents/Info.plist').read_bytes())
    if info.get('CFBundleShortVersionString')!=VERSION:raise ValueError('Application version changed')
    return config

def outcome(ui,native):
    if 'actual server error=' in ui or 'native callback result=false' in ui:return 'failed_native'
    if 'native callback result=true' in ui:
        return 'verified' if all('PHASE %d ok=true'%i in native for i in range(7)) else 'failed_phase_receipt'
    return 'waiting_native_callback'

def watch(args):
    root=Path(args.root)
    if not (root/'ENABLED').exists() or (root/'PAUSED').exists():return
    lock=(root/'watcher.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    config=verified_config(root)
    if config['stage_only']:raise ValueError('A staged fixture cannot dispatch')
    found=pids(config['app'])
    if len(found)!=1:return
    pid=found[0];start=subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart='],capture_output=True,text=True,check=True).stdout.strip()
    key=hashlib.sha256((str(pid)+':'+start).encode()).hexdigest()[:24]
    folder=root/'lifecycle'/key;folder.mkdir(parents=True,exist_ok=True);statefile=folder/'state.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else {'pid':pid,'launch_time':start,'phase':'not_dispatched'}
    runs=root/'runs';runs.mkdir(exist_ok=True)
    if state['phase']=='click_submitted':
        fresh=[p for p in runs.iterdir() if p.is_dir() and p.name not in state['prior_runs']]
        if len(fresh)==1:
            r=fresh[0];status=outcome((r/'UI.txt').read_text() if (r/'UI.txt').exists() else '',(r/'native.txt').read_text() if (r/'native.txt').exists() else '')
            if status!='waiting_native_callback':state.update(phase=status,native_run=str(r));save(statefile,state)
        elif len(fresh)>1:state.update(phase='ambiguous_native_receipts');save(statefile,state)
        return # Absence, timeout and failed callback never authorize another click.
    if state['phase']!='not_dispatched':return
    nonce=uuid.uuid4().hex
    state.update(phase='click_submitted',prior_runs=[p.name for p in runs.iterdir() if p.is_dir()],helper_nonce=nonce,
                 intent_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save(statefile,state)
    (root/'HELPER-REQUEST.txt').write_text(str(pid)+'\n'+nonce+'\n'+str(int(time.time())+120))
    result=subprocess.run(['/usr/bin/open','-W','-g','-n',config['helper']],capture_output=True,text=True)
    response=(root/'HELPER-RESPONSE.txt').read_text().splitlines() if (root/'HELPER-RESPONSE.txt').exists() else []
    value=response[1] if result.returncode==0 and len(response)==2 and response[0]==nonce else 'UNVERIFIED_HELPER_RESPONSE'
    state.update(helper_exit=result.returncode,helper_result=value)
    if result.returncode:state['phase']='failed_ui_automation'
    elif value.startswith('WAIT_FOR_') or value=='PROCESS_GONE':state['phase']='not_dispatched'
    elif value!='CLICK_SUBMITTED':state['phase']='blocked_'+value
    save(statefile,state)

def verify(args):
    root=Path(args.root);config=verified_config(root)
    runs=root/'runs';observed=[]
    for r in sorted(runs.glob('run-*'))[-3:] if runs.exists() else []:
        observed.append({'run':r.name,'outcome':outcome((r/'UI.txt').read_text() if (r/'UI.txt').exists() else '',(r/'native.txt').read_text() if (r/'native.txt').exists() else '')})
    print(json.dumps({'source_pins':'verified','version':config['version'],'stage_only':config['stage_only'],
                      'automation_enabled':(root/'ENABLED').exists() and not (root/'PAUSED').exists(),
                      'affinity_enabled':config['affinity'],'recent_runs':observed,
                      'native_completion_proven':any(v['outcome']=='verified' for v in observed)},indent=2))

def enable(args):
    root=Path(args.root);config=verified_config(root)
    if config['stage_only']:raise ValueError('Stage-only installation cannot be enabled')
    if not args.accept_menu_automation:raise ValueError('Pass --accept-menu-automation after granting permissions and verifying one manual run')
    # Native acceptance is required; pins/compilation alone are insufficient.
    runs=root/'runs';good=False
    for r in runs.glob('run-*') if runs.exists() else []:
        if (r/'UI.txt').exists() and (r/'native.txt').exists() and outcome((r/'UI.txt').read_text(),(r/'native.txt').read_text())=='verified':good=True
    if not good:raise ValueError('No actual successful manual native callback and seven-phase receipt; leave startup disabled')
    if pids(config['app']):raise ValueError('Quit Classic normally before enabling; the next launch owns its own startup request')
    destination=Path.home()/'Library/LaunchAgents'/ (LABEL+'.plist');destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():raise ValueError('Existing LaunchAgent retained; refusing overwrite')
    shutil.copy2(root/'startup.plist',destination)
    authorization=root/'AUTOMATIC-RENEWAL-AUTHORIZED';authorization.write_text(RENEWAL_AUTHORIZATION);authorization.chmod(0o600)
    (root/'PAUSED').unlink(missing_ok=True);(root/'ENABLED').touch(mode=0o600)
    try:subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(destination)],check=True)
    except Exception:
        (root/'PAUSED').touch(mode=0o600);(root/'ENABLED').unlink(missing_ok=True);authorization.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    print('Enabled startup watcher. It watches Classic launches, not photo folders.')

def disable(args):
    root=safe_path(args.root)
    if not (root/'config.json').is_file() or not (root/'manage.py').is_file():raise ValueError('Expected installed FirstPair root')
    (root/'PAUSED').touch(mode=0o600)
    (root/'AUTOMATIC-RENEWAL-AUTHORIZED').unlink(missing_ok=True)
    destination=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
    if destination.exists():
        owned=plistlib.loads(destination.read_bytes())
        if owned.get('Label')!=LABEL or str(root/'manage.py') not in owned.get('ProgramArguments',[]):raise ValueError('LaunchAgent belongs to another installation; its file and service were retained')
        subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid()),str(destination)],check=False)
        destination.unlink()
    print('Startup and future renewal disabled. Existing native requests retain their receipts. Quit Classic normally to release runtime TEMP objects/hooks. Durable SHA index remains; see README.')

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('install');q.add_argument('--root',default=str(DEFAULT_ROOT));q.add_argument('--app',default='/Applications/Adobe Lightroom Classic/Adobe Lightroom Classic.app');q.add_argument('--catalog',required=True);q.add_argument('--scripts-dir');q.add_argument('--backup-confirmed',action='store_true');q.add_argument('--enable-affinity',action='store_true');q.add_argument('--enable-schema-index',action='store_true');q.add_argument('--stage-only',action='store_true');q.add_argument('--dry-run',action='store_true');q.set_defaults(func=install)
    for name,fn in [('watch',watch),('verify',verify),('enable',enable),('disable',disable)]:
        q=sub.add_parser(name);q.add_argument('--root',default=str(DEFAULT_ROOT));q.set_defaults(func=fn)
        if name=='enable':q.add_argument('--accept-menu-automation',action='store_true')
    args=p.parse_args()
    try:args.func(args)
    except Exception as error:print('HELD: '+str(error),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
