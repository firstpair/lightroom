-- Lightroom (Cloud) Smart Preview download controller, rendered by prepare.py (parameters in __PARAMS__).
-- Asks Lightroom's ordinary getProxyPaths for each photo; Lightroom downloads and registers its own server preview.
-- Retries CannotSync/Transient statuses (bounded attempts, delayed) and backs off during outages (a batch with zero paths and mostly CannotSync pauses admissions, then probes with one batch before resuming).
local p=__PARAMS__
assert(os.time()>=p.epoch and os.time()<=p.epoch+3600,'expired')
local crypto=require'WFCrypto';assert(crypto.digestFile(p.run..'/IDS.lua','SHA256'):lower()==p.idsSHA256,'input roster changed');local claim=assert(io.open(p.run..'/NATIVE-ENTRY.lock','wx'),'persistent native entry already exists; no replay');assert(claim:write(p.nonce..'\n'));assert(claim:flush());assert(claim:close());local key='proxyFetchBulk_'..p.nonce
assert(rawget(_G,key)==nil,'no replay');local state={next=1,active=0,batches=0,returned=0,paths=0,statuses=0,errors=0,timeouts=0,retryQueued=0,retryAdmitted=0,retryExhausted=0,outages=0,backoffUntil=0,backoffSeconds=0,probing=false};rawset(_G,key,state)
local retry={head=1,tail=0};local attempts={}
local j=assert(io.open(p.run..'/EVENTS.txt','a'))
local function rec(s)j:write(os.time()..'\t'..s..'\n');j:flush()end
local ids=assert(loadfile(p.run..'/IDS.lua'))()
local member={};for _,id in ipairs(ids)do member[id]=true end
rec('UI_ENTRY\t'..#ids)
local rx=import'Rx';local lib=import'AgLibrary';local loop=import'AgEventLoop'
local root,pump
local function retryCount()return retry.tail-retry.head+1 end
local function progress()
 local f=io.open(p.run..'/PROGRESS.json','w');if f then f:write(string.format('{"t":%d,"next":%d,"total":%d,"active":%d,"batches":%d,"returned":%d,"paths":%d,"statuses":%d,"errors":%d,"timeouts":%d,"retryPending":%d,"retryQueued":%d,"retryAdmitted":%d,"retryExhausted":%d,"outages":%d,"backoffUntil":%d,"probing":%s}\n',os.time(),state.next,#ids,state.active,state.batches,state.returned,state.paths,state.statuses,state.errors,state.timeouts,retryCount(),state.retryQueued,state.retryAdmitted,state.retryExhausted,state.outages,state.backoffUntil,tostring(state.probing)));f:close()end
end
local function safePump()local ok,e=pcall(pump);if not ok then rec('PUMP_ERROR\t'..tostring(e))end end
local function wakeAt(t)
 local d=math.max(1,t-os.time())
 if state.wakeAt and state.wakeAt<=t then return end
 state.wakeAt=t;loop.afterDelay(d,function()if state.wakeAt==t then state.wakeAt=nil end;safePump()end)
end
local function retryable(status)return status=='CannotSyncDownloadToFileError' or status=='TransientDownloadToFileError' end
local function takeIds()
 local out={}
 while #out<p.batchSize and state.next<=#ids do out[#out+1]=ids[state.next];state.next=state.next+1 end
 local now=os.time()
 while #out<p.batchSize and retry.head<=retry.tail and retry[retry.head].at<=now do
  out[#out+1]=retry[retry.head].id;retry[retry.head]=nil;retry.head=retry.head+1;state.retryAdmitted=state.retryAdmitted+1
 end
 return out
end
local function startBatch(bids)
 local b={ids=bids,done=false,t0=os.time(),paths=0,cannot=0,rows=0}
 state.active=state.active+1;state.batches=state.batches+1;local number=state.batches
 local function finish(kind)
  if b.done then return end;b.done=true;local ds,de=pcall(function()b.sub:dispose()end);local cs,ce=pcall(function()b.m:close()end);rec('CLIENT_CLOSE_CALLS\t'..number..'\t'..tostring(ds)..'\t'..tostring(cs));if not ds or not cs then state.stopped=true;rec('REQUEST_CLOSURE_HELD\t'..number..'\t'..tostring(de)..'\t'..tostring(ce));progress();return end
  state.active=state.active-1
  if kind=='returned' or kind=='completed' then
   if b.paths>0 then
    if state.probing or state.backoffSeconds>0 then rec('OUTAGE_RECOVERED\t'..number)end
    state.probing=false;state.backoffSeconds=0
   elseif b.rows>0 and b.cannot*2>=b.rows and os.time()>=state.backoffUntil then
    state.outages=state.outages+1;state.backoffSeconds=math.min(p.backoffMax,math.max(p.backoffBase,state.backoffSeconds*2))
    state.backoffUntil=os.time()+state.backoffSeconds;state.probing=true;rec('OUTAGE_BACKOFF\t'..number..'\t'..state.backoffSeconds)
   end
  end
  rec('BATCH_END\t'..number..'\t'..kind..'\t'..(os.time()-b.t0));progress();loop.afterDelay(0,safePump)
 end
 local ok,e=pcall(function()
  b.m=root:subModel('getProxyPaths',b.ids);b.sub=rx.SingleAssignmentDisposable()
  b.sub:setDisposable(b.m:value():subscribe(function(rows)
   if b.done then return end
   for _,row in pairs(rows)do
    state.returned=state.returned+1;b.rows=b.rows+1;local pth=tostring(row.proxyPath);local id=row.imageId
    if pth:sub(1,1)=='/'then state.paths=state.paths+1;b.paths=b.paths+1;rec('ROW_PATH\t'..tostring(id))
    else
     state.statuses=state.statuses+1;rec('STATUS\t'..tostring(id)..'\t'..pth)
     if pth=='CannotSyncDownloadToFileError' then b.cannot=b.cannot+1 end
     if retryable(pth) and member[id] then
      local n=(attempts[id] or 0)+1;attempts[id]=n
      if n<=p.maxRetries then retry.tail=retry.tail+1;retry[retry.tail]={id=id,at=os.time()+p.retryDelay};state.retryQueued=state.retryQueued+1;rec('RETRY_QUEUED\t'..tostring(id)..'\t'..n)
      else state.retryExhausted=state.retryExhausted+1;rec('RETRY_EXHAUSTED\t'..tostring(id))end
     end
    end
   end
   finish('returned')
  end,function(err)state.errors=state.errors+1;rec('ERROR\t'..number..'\t'..tostring(err));finish('error')end,function()finish('completed')end))
 end)
 if not ok then state.errors=state.errors+1;rec('START_ERROR\t'..number..'\t'..tostring(e));finish('start_error');return end
 rec('BATCH_START\t'..number..'\t'..#b.ids)
 loop.afterDelay(p.timeoutSeconds,function()if not b.done then state.timeouts=state.timeouts+1;rec('DEADLINE_PENDING_NOT_TERMINATED\t'..number);progress()end end)
end
pump=function()
 if state.closed then return end
 local stop=io.open(p.run..'/STOP.json','rb');if stop then stop:close();if not state.stopped then state.stopped=true;rec('STOP_OBSERVED')end end
 local work=state.next<=#ids or retryCount()>0
 if not state.stopped and state.syncPaused~=false and work then
  if not state.pauseWake then state.pauseWake=true;rec('WAIT_SYNC_RUNNING');loop.afterDelay(5,function()state.pauseWake=false;safePump()end)end;return
 end
 if not state.stopped and state.syncPaused==false and work then
  local now=os.time()
  if now<state.backoffUntil then wakeAt(state.backoffUntil)
  else
   local limit=state.probing and 1 or p.parallel
   while state.active<limit do
    local bids=takeIds();if #bids==0 then break end;startBatch(bids)
   end
   if state.next>#ids and retry.head<=retry.tail and state.active<limit then wakeAt(retry[retry.head].at)end
  end
 end
 if state.active==0 and(state.stopped or(state.next>#ids and retryCount()==0))and not state.closed then state.closed=true;progress();if state.userSub then state.userSub:dispose()end;rec('CLOSED\t'..state.returned..'\t'..state.paths..'\t'..state.statuses..'\t'..retryCount()..'\t'..state.retryExhausted);j:close()end
end
local ok,e=pcall(function()
 state.userSub=rx.SingleAssignmentDisposable()
 lib.withActiveUserModel(function(u)
  if state.userSeen then return end;state.userSeen=true
  state.userSub:setDisposable(u:value():subscribe(function(v)
   if state.closed then return end
   local paused=type(v)=='table' and v.syncPaused or nil
   if type(v)=='table' and type(v.syncPaused)=='boolean' then paused=v.syncPaused end
   if state.syncPaused~=paused then state.syncPaused=paused;rec('SYNC_PAUSED_STATE\t'..tostring(paused))end
   if root then loop.afterDelay(0,safePump)end
  end))
 end)
 state.ownerSub=rx.SingleAssignmentDisposable()
 lib.withActiveCatalogModel(function(r)
  if root then return end
  state.ownerSub:setDisposable(r:value():subscribe(function(v)
   if root or type(v)~='table' or v.hasCatalog~=true or v.ozCatalogId~=p.catalogID or v.pixelsPath~=p.pixelsPath then return end
   root=r;state.ownerSub:dispose();rec('OWNER');progress();loop.afterDelay(0,safePump)
  end))
 end)
end)
if not ok then rec('TOP_ERROR\t'..tostring(e))end
