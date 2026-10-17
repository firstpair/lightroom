-- Known-SHA proxy registration (K1). Derived from NATIVE-PROXY-TEMPLATE.lua (N3) with: expected proxy SHA required and protected, original-fallback facts recorded not held, compact BEFORE snapshots, configurable arm/guard windows. Normal user Script; no app/process/database launching.
local p=__PLAN__
assert(p.state=='ROOT_BOUND_KNOWN_SHA_PROXY_REGISTRATION' and os.time()>=p.epoch and os.time()<=p.epoch+p.armWindowSeconds,'inert or expired Root arm')
assert(p.batchSize==256 and p.parallelBatches>=1 and p.parallelBatches<=4)
assert(p.annotationOnlyProxyLabelsQualified==true and p.initialEmptyDeadlineSeconds==15 and type(p.armWindowSeconds)=='number' and type(p.guardFreshnessSeconds)=='number','qualified label scope/read-only deadline absent')
local ownerKey='knownShaProxyNative_'..p.nonce
assert(rawget(_G,ownerKey)==nil,'retained one-shot native owner; never replay')
local state={nonce=p.nonce,phase='ENTRY',active=0,nextBatch=1,done=0,recognized=0,held=0,created=0,creationAttempts=0,records=0,bytes=0,batches={},rawErrors={},heldBatches={}}
rawset(_G,ownerKey,state)
local crypto,rx,loop,root,config,pump,queuePump
local function esc(s)return '"'..s:gsub('[%z\1-\31\\"]',function(c)return string.format('\\u%04x',c:byte())end)..'"'end
local function json(x,depth)
 depth=depth or 0;assert(depth<=96,'receipt depth');local t=type(x)
 if t=='nil'then return 'null'elseif t=='boolean'then return x and 'true'or'false'elseif t=='number'then assert(x==x and x~=math.huge and x~=-math.huge);return string.format('%.17g',x)elseif t=='string'then return esc(x)end
 assert(t=='table');local keys={};local numeric=false;for k in pairs(x)do assert(type(k)=='string'or(type(k)=='number'and k>=1 and k%1==0));numeric=numeric or type(k)=='number';keys[#keys+1]=k end;table.sort(keys);local out={}
 if numeric then for i,k in ipairs(keys)do assert(k==i);out[#out+1]=json(x[k],depth+1)end;return '['..table.concat(out,',')..']'end
 for _,k in ipairs(keys)do out[#out+1]=esc(k)..':'..json(x[k],depth+1)end;return '{'..table.concat(out,',')..'}'
end
local function write(path,data,mode)
 local f=assert(io.open(path,mode or'wx'));local ok,e=pcall(function()assert(f:write(data));assert(f:flush())end);local closed,closeError=pcall(function()assert(f:close())end);assert(ok,tostring(e));assert(closed,tostring(closeError))
end
local function record(event,value)
 local line=json({event=event,nonce=p.nonce,value=value})..'\n';assert(#line<=4*1024*1024,'native event size bound');state.records=state.records+1;state.bytes=state.bytes+#line;assert(state.bytes<=p.maxReceiptBytes,'native event aggregate bound')
 if not state.journal then state.journal=assert(io.open(p.run..'/ACTUAL-PROXY-EVENTS.jsonl','wx'))end
 assert(state.journal:write(line));if state.records%64==0 or event:find('ERROR',1,true)or event:find('HELD',1,true)or event=='UI_ENTRY'or event=='PROXY_REQUEST_BEFORE_CREATION'or event=='ACTUAL_PROXY_RETURNED_ROWS'or event=='ACTUAL_PROXY_REQUEST_ERROR'or event=='BATCH_CLOSED_CHECKPOINT'or event=='CONTROLLER_CLOSED'then assert(state.journal:flush())end
end
local function closeJournal()
 if state.journalClosed then return end;assert(state.journal);local flushed,fe=pcall(function()assert(state.journal:flush())end);local closed,ce=pcall(function()assert(state.journal:close())end);state.journalClosed=closed;assert(flushed,tostring(fe));assert(closed,tostring(ce));write(p.run..'/OWNED-JOURNAL-CLOSED.json',json({nonce=p.nonce,journalClosed=true,records=state.records,recordBytes=state.bytes,controllerPhase=state.phase,postGatePending=true})..'\n')
end
local function clone(x,seen)if type(x)~='table'then return x end;seen=seen or{};assert(not seen[x],'cyclic native value');seen[x]=true;local out={};for k,v in pairs(x)do out[k]=clone(v,seen)end;seen[x]=nil;return out end
local function equal(a,b)if type(a)~=type(b)then return false end;if type(a)~='table'then return a==b end;for k,v in pairs(a)do if not equal(v,b[k])then return false end end;for k in pairs(b)do if a[k]==nil then return false end end;return true end
local function typed(x,depth,seen,cells)
 depth=depth or 0;seen=seen or{};cells=cells or{n=0};assert(depth<=48);cells.n=cells.n+1;assert(cells.n<=200000,'native typed cell bound');local t=type(x)
 if t=='nil'then return{type='nil'}elseif t=='string'then assert(#x<=1024*1024);return{type=t,value=x}elseif t=='boolean'or t=='number'then return{type=t,value=x}end
 assert(t=='table'and not seen[x],'unsupported/cyclic native value');seen[x]=true;local keys={};for k in pairs(x)do assert(type(k)=='string'or type(k)=='number');keys[#keys+1]=k end;table.sort(keys,function(a,b)if type(a)==type(b)then return a<b end;return type(a)<type(b)end);local entries={};for i,k in ipairs(keys)do entries[tostring(i)]={key=typed(k,depth+1,seen,cells),value=typed(x[k],depth+1,seen,cells)}end;seen[x]=nil;return{type='table',entries=entries}
end
local function errorEvidence(x)
 state.rawErrors[#state.rawErrors+1]=x
 local ok,value=pcall(typed,x);if ok then return value end
 return{rawType=type(x),rawTostring=tostring(x),typedRepresentationHeld=true,representationError=tostring(value),rawValueRetainedInOwnedState=true}
end
local function digest(pin)local actual=crypto.digestFile(pin.path,'SHA256');assert(type(actual)=='string'and actual:lower()==pin.sha256,'owned metadata pin changed')end
local function loadConfig(pin)
 digest(pin);local f=assert(io.open(pin.path,'rb'));local data=assert(f:read(pin.bytes+1));assert(f:close());assert(#data==pin.bytes and #data<=128*1024*1024,'metadata config size');digest(pin);local fn,e=loadstring(data,'@'..pin.path);assert(fn,e);local value=fn();assert(type(value)=='table');return value
end
local function guard(batchNumber)
 local g=assert(loadfile(p.guardPath))();assert(g.nonce==p.nonce and g.cloudPID==p.cloudPID and g.catalogID==p.catalogID and g.pixelsPath==p.pixelsPath,'owned launcher/source guard identity')
 assert(g.networkDenied==true and g.originalSourceReadDenied==true and g.exactProcessOwnerUnchanged==true and g.physicalSourceDestUnchanged==true,'mandatory actual launcher/source guard absent')
 assert(os.time()>=g.epoch-2 and os.time()<=g.epoch+p.guardFreshnessSeconds,'current launcher/source guard stale')
 assert(g.rowsSHA256==p.rows.sha256 and g.batchConfigSHA256==p.batchConfig.sha256 and g.launcherEvidenceSHA256==p.launcherEvidence.sha256,'fresh source guard exact workset/launcher pins differ')
 if batchNumber then assert(type(g.approvedBatches)=='table');return g.approvedBatches[tostring(batchNumber)]==true end
 return true
end
local function snapshot(b,stage,row,doc)
 local line;if stage=='BEFORE'then line=json({ordinal0=row.ordinal0,assetUUID=row.assetUUID,localID=row.localID,revId=doc._revId,changeCounter=doc._changeCounter,nonEmpty=next(doc)~=nil})..'\n'else line=json({ordinal0=row.ordinal0,assetUUID=row.assetUUID,localID=row.localID,doc=doc})..'\n'end;assert(#line<=8*1024*1024,'full native snapshot row bound')
 b.snapshotBytes=b.snapshotBytes+#line;assert(b.snapshotBytes<=512*1024*1024,'batch native snapshot aggregate bound')
 b[stage..'Lines']=b[stage..'Lines']or{};b[stage..'Lines'][#b[stage..'Lines']+1]=line;b[stage..'Writes']=(b[stage..'Writes']or 0)+1
end
local function sealSnapshot(b,stage)
 if not b[stage..'Lines']or b[stage..'Seal']then return end
 local path=p.run..'/BATCH-'..string.format('%05d',b.number)..'-NATIVE-'..stage..'.jsonl';write(path,table.concat(b[stage..'Lines']));b[stage..'Seal']={path=path,sha256=crypto.digestFile(path,'SHA256'):lower(),rows=b[stage..'Writes']};b[stage..'Lines']=nil
end
local function supportedProxy(d)
 assert(type(d._serverProvidedMetadata)=='table'and type(d._serverProvidedMetadata.links)=='table','current raw server links absent')
 local found=false;for relation,link in pairs(d._serverProvidedMetadata.links)do
  if type(relation)=='string'and relation:find('proxy_type',1,true)and relation:match('/([^/]*)$')=='2560'and type(link)=='table'and type(link.href)=='string'and #link.href>0 then found=true end
 end;assert(found,'no current native supported still proxy relation')
end
local function proxyAnnotation(d)local l=d._localOnly;return type(l)=='table'and type(l.files)=='table'and type(l.files.proxy)=='table'and l.files.proxy['2560']or nil end
local function guardBefore(d,r)
 assert(type(d)=='table'and d._id==r.assetUUID and d._localId==r.localID and d._revId==r.revisionID,'fresh numericID/UUID/revision mismatch')
 assert(d._deleted~=true and d._conflict~=true and d.subtype=='image')
 assert(type(d._changeCounter)=='number'and d._changeCounter>=0 and d._changeCounter%1==0 and d._changeCounter<2^53)
 assert(type(d.importSource)=='table'and d.importSource.proxySHA256==r.expectedProxySHA256,'expected proxy SHA differs from closed ledger; held')
 -- Known-SHA cohort: original-fallback facts are recorded in the ledger; network/original reads are denied by the launcher sandbox.
 assert(proxyAnnotation(d)==nil,'target annotation already exists; no replay')
 supportedProxy(d)
 local projected=clone(d);projected._labels=nil
 assert(equal(projected,r.expectedPersistedDoc),'full native body/annotation/identity differs from exact persisted baseline')
 if d._labels~=nil then assert(type(d._labels)=='table'and equal(d._labels,r.storedLabels),'observed native label view differs from persisted semantics')end
 -- SQL persisted labels never predict an omitted native label view. The actual
 -- before view is retained in full; only the pinned annotation-only nil-view producer
 -- may qualify its exact emitted table-to-nil transition after recognition.
 -- Entire body/develop/profile/masks/auxiliary and actual label view stay protected.
 -- Pending settings, legacy PV and profile status are editing holds, not proxy admission.
end
local function protectedProjection(after,before,r)
 assert(type(after)=='table'and after._id==r.assetUUID and after._localId==r.localID and after._revId==r.revisionID,'native identity/revision changed')
 assert(type(after._changeCounter)=='number'and after._changeCounter>before._changeCounter and after._changeCounter%1==0 and after._changeCounter<2^53,'invalid global sequence')
 local annotation=proxyAnnotation(after);assert(type(annotation)=='table','native proxy annotation absent')
 assert(annotation.volumeGuid==r.expectedVolumeGuid and annotation.relativePath==r.expectedRelativePath and type(annotation.lastSaveTimestamp)=='string'and #annotation.lastSaveTimestamp>0 and #annotation.lastSaveTimestamp<=64,'native exact annotation mapping differs')
 for k in pairs(annotation)do assert(k=='volumeGuid'or k=='relativePath'or k=='lastSaveTimestamp','unobserved proxy annotation field or fabricated SHA')end
 assert(annotation.sha256==nil and after.importSource.proxySHA256==r.expectedProxySHA256,'native annotation SHA field appeared or expected proxy SHA changed')
 local d=clone(after);d._changeCounter=before._changeCounter
 -- A new model can replay the last annotation-only emitted doc on the same keyed
 -- ReplaySubject. Retain both actual label views; never call a table-to-nil view unchanged.
 local labelsUnchanged=equal(after._labels,before._labels)
 local qualifiedNilView=type(before._labels)=='table'and after._labels==nil
 assert(labelsUnchanged or(p.annotationOnlyProxyLabelsQualified and qualifiedNilView),'unqualified native label type/value change')
 if qualifiedNilView then d._labels=clone(before._labels)end
 d._localOnly.files.proxy['2560']=nil
 local priorLocal=before._localOnly;local priorFiles=type(priorLocal)=='table'and priorLocal.files or nil;local priorProxy=type(priorFiles)=='table'and priorFiles.proxy or nil
 if priorProxy==nil then assert(next(d._localOnly.files.proxy)==nil);d._localOnly.files.proxy=nil end
 if priorFiles==nil then assert(next(d._localOnly.files)==nil);d._localOnly.files=nil end
 if priorLocal==nil then assert(next(d._localOnly)==nil);d._localOnly=nil end
 return d,annotation,{literalNativeLabelsUnchanged=labelsUnchanged,annotationOnlyNilViewQualified=qualifiedNilView,before=typed(before._labels),after=typed(after._labels),externalStoredMembershipAndActualWinningSequencePostGateRequired=true}
end
local function closeReader(b)
 local h=b.reader;if not h then return end
 local subOK,subError=true,nil;if not h.subDisposed then subOK,subError=pcall(function()h.sub:dispose()end);h.subDisposed=subOK end
 local modelOK,modelError=true,nil;if not h.modelClosed then modelOK,modelError=pcall(function()h.model:close()end);h.modelClosed=modelOK end
 if subOK and modelOK then h.closed=true;b.reader=nil end
 local logOK,logError=pcall(record,'OWN_DOC_READER_CLOSE',{batch=b.number,ordinal0=h.row.ordinal0,stage=h.stage,subscriptionDisposed=h.subDisposed==true,modelClosed=h.modelClosed==true,subError=not subOK and tostring(subError)or nil,modelError=not modelOK and tostring(modelError)or nil})
 if not logOK then state.halt=true;state.outputError=tostring(logError)end;assert(subOK,tostring(subError));assert(modelOK,tostring(modelError))
end
local function closeRequest(b)
 assert(b.nativeTerminal and b.request and not b.requestClosed,'close only exact terminal owned request')
 local subOK,subError=true,nil;if b.proxySub and not b.proxySubDisposed then subOK,subError=pcall(function()b.proxySub:dispose()end);b.proxySubDisposed=subOK end
 local ok,e=pcall(function()b.request:close()end);if ok then b.requestClosed=true end
 local logged,logError=pcall(record,'OWN_PROXY_REQUEST_CLOSE',{batch=b.number,terminal=b.nativeTerminal,ok=ok,subscriptionDisposed=b.proxySubDisposed==true,error=not ok and tostring(e)or nil,subError=not subOK and tostring(subError)or nil});if not logged then state.halt=true;state.outputError=tostring(logError)end;assert(ok,tostring(e));assert(subOK,tostring(subError))
end
local ROW_HOLD={BEFORE_DOC_HELD=true,AFTER_DOC_HELD=true,EXACT_EMPTY_READONLY_DEADLINE_HELD=true,DOC_STREAM_ERROR=true,DOC_STREAM_COMPLETED_WITHOUT_VALUE=true}
local function held(b,event,e,row)
 if ROW_HOLD[event]then state.rowHolds=(state.rowHolds or 0)+1;record(event,{batch=b.number,phase=b.phase,error=tostring(e),ordinal0=row and row.ordinal0,assetUUID=row and row.assetUUID,rowSkippedNotHalting=true,noReplay=true});return end
 state.halt=true;b.hold=true;record(event,{batch=b.number,phase=b.phase,error=tostring(e),nativeTerminal=b.nativeTerminal,pendingOwnedRequestRetained=b.request~=nil and not b.nativeTerminal,noReplay=true})
end
local function protectedCallback(b,fn)return function(...)
 local args={...};local ok,e=pcall(fn,unpack(args));if not ok then
  local retained,retainError=pcall(held,b,'CALLBACK_ERROR_RETAINED',e);if not retained then state.halt=true;b.hold=true;state.outputError=tostring(retainError)end
  -- A diagnostic failure can close this exact read-only child. Never cancel the
  -- separate proxy request, and never claim closure if dispose/close fails.
  if b.reader then local closed,closeError=pcall(closeReader,b);if closed then b.held=(b.held or 0)+1;b.cursor=b.cursor+1;queuePump()else record('DOC_CLEANUP_ERROR_RETAINED',{batch=b.number,error=tostring(closeError),exactReaderRetained=true})end end
  if b.nativeTerminal and b.request and not b.requestClosed then local closed,closeError=pcall(closeRequest,b);if closed then b.returned=b.returned or{};b.phase='AFTER_DOC';b.cursor=1;queuePump()else state.terminalCleanupError=tostring(closeError)end end
 end
end end
local function finishBatch(b)
 assert(not b.reader and (not b.request or b.requestClosed),'owned batch handles not closed')
 local receipt={batch=b.number,rows=#b.rows,recognized=b.recognized,held=b.held or 0,nativeTerminal=b.nativeTerminal,requestCreated=b.request~=nil,allOwnedHandlesClosed=true,physicalPublicationNotNativeProof=true,independentClosedIndexedPostGatePending=true}
 for _,stage in ipairs({'BEFORE','AFTER'})do sealSnapshot(b,stage);receipt[stage]=b[stage..'Seal']end
 write(p.run..'/BATCH-'..string.format('%05d',b.number)..'-CLOSED.json',json(receipt)..'\n');record('BATCH_CLOSED_CHECKPOINT',receipt)
 if b.hold then state.heldBatches[tostring(b.number)]=b end
 state.active=state.active-1;state.done=state.done+#b.rows;state.recognized=state.recognized+b.recognized;state.held=state.held+(b.held or 0);state.batches[b.slot]=nil;queuePump()
end
local function readOne(b,stage)
 local row=b.rows[b.cursor];if stage=='AFTER'and not b.before[b.cursor]then record('AFTER_SKIPPED_NO_BEFORE',{batch=b.number,ordinal0=row.ordinal0,assetUUID=row.assetUUID});b.cursor=b.cursor+1;queuePump();return end;b.phase=stage..'_DOC';local h={row=row,stage=stage,sub=rx.SingleAssignmentDisposable()};b.reader=h
 h.model=root:subModel('_DEBUG_assetPanelInfoStream',row.assetUUID)
 local subscription=h.model:value():subscribe(protectedCallback(b,function(doc)
  if h.seen then return end
  if type(doc)=='table'and next(doc)==nil then
   if not h.initialEmptyObserved then
    h.initialEmptyObserved=true;record('INITIAL_EXACT_EMPTY_DOC_HYDRATION_WAIT',{batch=b.number,ordinal0=row.ordinal0,assetUUID=row.assetUUID,localID=row.localID,stage=stage,exactEmptyTableObserved=true,sameOwnedReaderRetained=true,identityAndBodyNotAccepted=true,readonlyDeadlineSeconds=15});assert(state.journal:flush())
    h.emptyDeadlineTask=loop.afterDelay(15,protectedCallback(b,function()
     if b.reader~=h or h.closed or h.seen then return end
     snapshot(b,stage,row,{});b.held=(b.held or 0)+1;held(b,'EXACT_EMPTY_READONLY_DEADLINE_HELD','same owned readonly reader remained exact empty for15seconds; no native request replay',row)
     closeReader(b);b.cursor=b.cursor+1;queuePump()
    end))
   end
   return
  end
  h.seen=true;snapshot(b,stage,row,doc)
  local checked,e=pcall(function()
   if stage=='BEFORE'then guardBefore(doc,row);b.before[b.cursor]=clone(doc)
   else
    local projected,annotation,labelViews=protectedProjection(doc,b.before[b.cursor],row);assert(equal(projected,b.before[b.cursor]),'unrelated full native body/develop/profile/mask/aux/server/labels changed')
    assert(b.returned[row.localID]==row.expectedPath,'returned exact proxy path missing/different')
    b.recognized=b.recognized+1;record('ASSET_NATIVE_RECOGNIZED',{ordinal0=row.ordinal0,assetUUID=row.assetUUID,localID=row.localID,batch=b.number,beforeCounter=b.before[b.cursor]._changeCounter,afterCounter=doc._changeCounter,annotation=annotation,fullDocProtected=true,expectedProxySHA256=row.expectedProxySHA256,storedLabelsPostGateRequired=true,nativeLabelViews=labelViews})
   end
  end)
  if not checked then b.held=(b.held or 0)+1;held(b,stage..'_DOC_HELD',e,row);if stage=='BEFORE'then b.before[b.cursor]=nil end end
  closeReader(b);b.cursor=b.cursor+1;queuePump()
 end),protectedCallback(b,function(e)
  snapshot(b,stage,row,{streamError=errorEvidence(e)});b.held=(b.held or 0)+1;held(b,'DOC_STREAM_ERROR',e,row);closeReader(b);b.cursor=b.cursor+1;queuePump()
 end),protectedCallback(b,function()
  if not h.seen then held(b,'DOC_STREAM_COMPLETED_WITHOUT_VALUE','actual empty stream',row);closeReader(b);b.held=(b.held or 0)+1;b.cursor=b.cursor+1;queuePump()end
 end));h.sub:setDisposable(subscription)
end
local function beginRequest(b)
 sealSnapshot(b,'BEFORE');local guardOK,guardResult=pcall(guard,b.number);if not guardOK then held(b,'BEFORE_DISPATCH_SOURCE_GUARD_HELD',guardResult);finishBatch(b);return end
 if not guardResult then b.phase='BEFORE_DISPATCH_GUARD_WAIT';queuePump(1);return end
 assert(not state.halt and not b.hold and not b.request);local ids={};for i,row in ipairs(b.rows)do if b.before[i]then ids[#ids+1]=row.localID end end;if #ids==0 then record('BATCH_NO_ELIGIBLE_ROWS',{batch=b.number,held=b.held or 0});b.phase='AFTER_DOC';b.cursor=#b.rows+1;finishBatch(b);return end
 b.phase='PROXY_REQUEST';state.creationAttempts=state.creationAttempts+1;record('PROXY_REQUEST_BEFORE_CREATION',{batch=b.number,count=#ids,localIds=ids,tag='getProxyPaths',noOriginalRequestByController=true})
 b.proxySub=rx.SingleAssignmentDisposable();b.request=root:subModel('getProxyPaths',ids)
 assert(b.request~=nil and type(b.request.close)=='function','owned normal request handle unavailable after attempt');state.created=state.created+1
 local ownedRequest=b.request
 local subscription=ownedRequest:value():subscribe(protectedCallback(b,function(returnedRows)
  assert(b.request==ownedRequest and not b.nativeTerminal,'foreign/repeated owned observable terminal');b.nativeTerminal='onNext';b.rawReturnedRows=returnedRows;record('ACTUAL_PROXY_RETURNED_ROWS',{batch=b.number,callbackContract='owned request:value():subscribe(rows)',exactOwnedModelBound=true,rows=typed(returnedRows)})
  closeRequest(b);b.returned={};local wanted={};for _,r in ipairs(b.rows)do wanted[r.localID]=r end
  local parseOK,e=pcall(function()
   assert(type(returnedRows)=='table','native returned rows type');local count=0
   for key,r in pairs(returnedRows)do assert(type(key)=='number'and key>=1 and key%1==0 and type(r)=='table','native row shape');count=count+1;local id=r.imageId;assert(type(id)=='number'and wanted[id]and b.returned[id]==nil,'unexpected/repeated numeric ID');b.returned[id]=r.proxyPath or false end
   local expected=0;for i,r in ipairs(b.rows)do if b.before[i]then expected=expected+1;if b.returned[r.localID]~=r.expectedPath then state.rowHolds=(state.rowHolds or 0)+1;b.held=(b.held or 0)+1;record('ROW_RETURN_PATH_MISMATCH_HELD',{batch=b.number,ordinal0=r.ordinal0,assetUUID=r.assetUUID,localID=r.localID,returned=b.returned[r.localID],expected=r.expectedPath,rowSkippedNotHalting=true});b.before[i]=nil end end end;assert(count==expected,'returned cardinality differs')
  end);if not parseOK then held(b,'PROXY_RETURN_PROTOCOL_HELD',e)end
  b.phase='AFTER_DOC';b.cursor=1;queuePump()
 end),protectedCallback(b,function(errorValue)
  assert(b.request==ownedRequest and not b.nativeTerminal);b.nativeTerminal='onError';record('ACTUAL_PROXY_REQUEST_ERROR',{batch=b.number,callbackContract='owned request:value():subscribe(error)',exactOwnedModelBound=true,error=errorEvidence(errorValue)})
  closeRequest(b);b.returned={};held(b,'NATIVE_PROXY_FAILED','genuine observable error retained');b.phase='AFTER_DOC';b.cursor=1;queuePump()
 end),protectedCallback(b,function()
  if b.nativeTerminal then return end;assert(b.request==ownedRequest);b.nativeTerminal='onCompletedWithoutRows';closeRequest(b);b.returned={};held(b,'NATIVE_PROXY_COMPLETED_WITHOUT_ROWS','actual completion without result');b.phase='AFTER_DOC';b.cursor=1;queuePump()
 end));b.proxySub:setDisposable(subscription)
end
queuePump=function(delay)
 if state.pumpQueued then return end;state.pumpQueued=true
 state.pumpTask=loop.afterDelay(delay or 0,function()state.pumpQueued=false;local ok,e=pcall(pump);if not ok then state.halt=true;record('PUMP_ERROR_RETAINED',{error=tostring(e),active=state.active,created=state.created,pendingHandlesNotCancelled=true,noReplay=true})end end)
end
pump=function()
 if state.closed then return end
 local stop=io.open(p.run..'/STOP-NEW-ADMISSIONS.json','rb');if stop then assert(stop:close());state.halt=true;record('STOP_NEW_ADMISSIONS_OBSERVED',{active=state.active,pendingOwnedRequestsNotCancelled=true})end
 for _,b in pairs(state.batches)do
  if not b.reader then
   if b.phase=='BEFORE_DOC'then
    if state.halt then b.hold=true;record('UNSUBMITTED_BATCH_HELD_CLOSED',{batch=b.number,preparedBeforeDocs=b.cursor-1,requestCreated=false});finishBatch(b)
    elseif b.cursor<=#b.rows and not b.hold then readOne(b,'BEFORE')
    elseif b.hold then finishBatch(b)
    else beginRequest(b)end
   elseif b.phase=='AFTER_DOC'then
    if b.cursor<=#b.rows then readOne(b,'AFTER')else finishBatch(b)end
   elseif b.phase=='BEFORE_DISPATCH_GUARD_WAIT'then
    if state.halt then b.hold=true;finishBatch(b)else beginRequest(b)end
   end
  end
 end
 if not state.halt then for slot=1,p.parallelBatches do if not state.batches[slot]and state.nextBatch<=#config then
  local number=state.nextBatch;if not guard(number)then queuePump(1);break end;state.nextBatch=number+1;local rows=loadConfig(config[number]);assert(#rows==config[number].count and #rows<=256)
  local b={slot=slot,number=number,rows=rows,before={},cursor=1,phase='BEFORE_DOC',recognized=0,snapshotBytes=0};state.batches[slot]=b;state.active=state.active+1;record('BATCH_READONLY_BEGIN',{batch=number,rows=#rows});queuePump()
 end end end
 if state.active==0 and (state.halt or state.nextBatch>#config)then
  state.closed=true;state.phase=state.halt and 'HELD_CLOSED' or 'NATIVE_REQUESTS_CLOSED_POST_GATE_PENDING';record('CONTROLLER_CLOSED',{state=state.phase,planned=p.count,closedBatchRows=state.done,recognized=state.recognized,held=state.held,createdRequests=state.created,requestCreationAttempts=state.creationAttempts,allOwnedModelHandlesClosed=true,ownedJournalClosureSidecarRequired=true,unsubmittedBatches=#config-state.nextBatch+1,nativeAcceptanceRequiresIndependentClosedIndexedObserver=true,mainAndPhysicalSourcePostProtectionRequired=true});closeJournal()
 end
end
record('UI_ENTRY',{count=p.count,batchSize=p.batchSize,parallelBatches=p.parallelBatches,nativeRequestsCreated=0})
local ok,e=pcall(function()
 crypto=require'WFCrypto';assert(type(crypto.digestFile)=='function');rx=import'Rx';loop=import'AgEventLoop';assert(type(loop.afterDelay)=='function')
 for _,pin in ipairs({p.arm,p.rows,p.launcherEvidence})do digest(pin)end
 -- initialGuard is a constructor-pinned historical witness. The external Root guard
 -- intentionally refreshes guardPath; its live identity/freshness is checked by guard().
 config=loadConfig(p.batchConfig);local paths=import'AgPathUtils';assert(paths.getStandardFilePath('appData')==p.appData);guard()
 local lib=import'AgLibrary';state.identitySub=rx.SingleAssignmentDisposable();lib.withActiveCatalogModel(function(r)
  if state.ownerEntered then record('ADDITIONAL_OWNER_CALLBACK_HELD',true);return end;state.ownerEntered=true;root=r
  local subscription=root:value():subscribe(function(value)
   if state.rootAccepted then return end
   local accepted,ownerError=pcall(function()
    assert(type(value)=='table'and value.hasCatalog==true and value.ozCatalogId==p.catalogID and value.pixelsPath==p.pixelsPath,'actual ordinary Cloud root owner mismatch');guard();state.rootAccepted=true;record('CURRENT_PUBLIC_ROOT_OWNER',{catalogID=value.ozCatalogId,pixelsPath=value.pixelsPath,hasCatalog=true});assert(pcall(function()state.identitySub:dispose()end));state.identityClosed=true;queuePump()
   end);if not accepted then state.halt=true;record('OWNER_ERROR_RETAINED',{error=tostring(ownerError),created=state.created});assert(pcall(function()state.identitySub:dispose()end));state.identityClosed=true;state.closed=true;record('ZERO_REQUEST_OWNER_HELD_CLOSED',{created=state.created,allOwnedModelHandlesClosed=state.created==0});closeJournal()end
  end,function(errorValue)
   state.halt=true;record('ROOT_IDENTITY_STREAM_ERROR',{error=errorEvidence(errorValue),created=state.created});assert(pcall(function()state.identitySub:dispose()end));state.identityClosed=true
   if state.active==0 and state.creationAttempts==0 then state.closed=true;state.phase='ZERO_REQUEST_IDENTITY_ERROR_CLOSED';record('ZERO_REQUEST_OWNER_HELD_CLOSED',{created=0,actualIdentityTerminal='onError',allOwnedModelHandlesClosed=true});closeJournal()else queuePump()end
  end);state.identitySub:setDisposable(subscription)
 end)
end)
if not ok then state.halt=true;record('TOP_ERROR_RETAINED',{error=tostring(e),created=state.created,active=state.active,pendingOwnedHandlesNotCancelled=true})end
if not state.journalClosed then record('TOP_RETURN',{created=state.created,active=state.active,notTerminalProof=true})end
-- Only the exact initial-empty readonly child has a fixed15second hold/closure deadline.
-- No proxy request timeout, native retries, shared-request cancellation, root.close, global scheduler changes,
-- preference/offlineMode mutation, original/develop/render request, expected SHA setter, Reset or Update.
