"""Pure pair selection from one independently audited eight-key publication.

A pair is a recognition input view, never a separate publish or render event.
The caller authenticates the parent bytes and adds that pin to runtime sources.
This module performs no filesystem, database, native or media operations.
Promotion of this pure selector does not qualify the private runtime pipeline.
"""
import copy
import re
PAIRS=((1,2),(3,4),(5,6),(7,8))
def need(v,code):
    if not v:raise ValueError(code)
def integer(v,lo=0):return type(v)is int and v>=lo
def project_pair(parent,parent_pin,indices):
    need(type(parent_pin)is dict and set(parent_pin)=={'path','bytes','sha256'}and
         type(parent_pin['path'])is str and parent_pin['path'].startswith('/')and
         integer(parent_pin['bytes'],1)and type(parent_pin['sha256'])is str and
         re.fullmatch('[0-9a-f]{64}',parent_pin['sha256']),'PARENT_AUDIT_PIN')
    need(type(indices)is list and len(indices)==2 and all(type(i)is int for i in indices)and
         tuple(indices)in PAIRS,'EXACT_RECOGNITION_PAIR')
    need(type(parent)is dict and parent.get('state')=='EIGHT_ORIGINAL_STANDARD_INITIAL_INSERTS_INDEPENDENTLY_VERIFIED'and
         type(parent.get('records'))is list and len(parent['records'])==8,'WHOLE_EIGHT_PUBLICATION_AUDIT')
    for k,n in [('oldTenPreviewsPermanentlyRetained',0),('stagedEncodedOutputs',32),('QuasarHighestTiers',8),
                ('sourceOriginalPayloadReads',0),('nativeInvocations',0)]:
        need(type(parent.get(k))is int and parent[k]==n,'WHOLE_EIGHT_COUNTERS')
    need(parent.get('unknownMarkers')==[]and parent.get('wholeDatabaseHashOrCopy')is False and
         parent.get('fullCatalogComplete')is False,'WHOLE_EIGHT_SCOPE')
    w=parent['actualWorkerWait'];need(integer(w.get('pid'),2)and type(w.get('returncode'))is int and w['returncode']==0 and
        w.get('reaped')is True and w.get('other_group_members_absent_before_reap')is True and w.get('timed_out')is False,
        'WHOLE_EIGHT_WORKER_CLOSED')
    t=parent.get('priorRootToolTerminal');need(type(t)is dict and integer(t.get('session'),1)and type(t.get('exitCode'))is int and
        t['exitCode']==0 and t.get('noRunningSession')is True,'WHOLE_EIGHT_ACTUAL_TOOL_CLOSED')
    seen=set()
    for r in parent['records']:
        need(type(r.get('key'))is list and len(r['key'])==2 and all(type(v)is str for v in r['key'])and
             tuple(r['key'])not in seen,'WHOLE_EIGHT_DISTINCT_KEYS');seen.add(tuple(r['key']))
        need(all(r.get(k)is True for k in ('selectedSQLRowsExact','rootPixelsPreservedExact',
             'unrelatedRowWitnessesUnchanged','originalSourceStat8Unchanged')),'EVERY_PARENT_KEY_QUALIFIED')
        need(type(r.get('payloads'))is list and len(r['payloads'])==4 and
             sum(p.get('highestNativeLevel')is True for p in r['payloads'])==1 and
             type(r.get('permanentlyRetainedOldTenPreviews'))is list and len(r['permanentlyRetainedOldTenPreviews'])==0,
             'EVERY_PARENT_COMPLETE_AND_RETAINED')
    selected=copy.deepcopy(parent);selected.update(
        state='TWO_ORIGINAL_STANDARD_INITIAL_INSERTS_INDEPENDENTLY_VERIFIED',
        schema='ROOT_TWO_RECOGNITION_KEYS_SELECTED_FROM_ONE_EIGHT_PUBLICATION_AUDIT_V1',
        records=[copy.deepcopy(parent['records'][i-1])for i in indices],
        oldTenPreviewsPermanentlyRetained=0,stagedEncodedOutputs=8,QuasarHighestTiers=2,
        parentPublicationAudit=copy.deepcopy(parent_pin),sourceKeyIndices=list(indices),sourcePublicationKeyCount=8,
        selectionScope='TWO_KEYS_FOR_CACHE_RECOGNITION_ONLY_NOT_A_NEW_PUBLICATION_OR_RENDER_EVENT',
        parentToolTerminalScope='ONE_REAL_EIGHT_KEY_PUBLICATION_TOOL_RETURN_REFERENCED_NOT_A_PER_PAIR_TOOL_EVENT')
    return selected
