local request=...
local sp=request:serverProperty('storeProvider');assert(sp._mainDbPath=='@@CATALOG@@')
local target=(require 'LrWFSyncStatusQueriesCaching').getStashedRequest(sp,'trackingRequest')
assert(type(target)=='table' and target.id==EXPECTED,'exact request ID mismatch')
assert(not _G.localRepairJournalDelta1331010forward)
local raw=rawget(target,'send');local prior=assert(target.send);local now=import 'AgDate'.timeIntervalSinceReferenceDate
local function write(name,s)local f=assert(io.open("@@ROOT@@/runtime/transport/templates/forward/"..name,'a'));f:write(s..'\n');f:close()end
local guard=assert(_G.localRepairIncrementalMapCountPilot);assert(guard.active and guard.mismatches==0 and guard.candidateErrors==0)
local core=assert(guard.core);local priorGet=assert(core.get);local rawGet=rawget(core,'get');local wrappedGet
local bindings=setmetatable({},{__mode='k'});local previous;local model
local function clone(map)local out={};for k,v in pairs(map)do assert(type(k)=='number'and type(v)=='string');out[k]=v end;return out end
local state={calls=0,active=true,deltas=0,fulls=0,oracles=0,constructionSeconds=0,sendSeconds=0};local wrapped
local function read(name)local f=io.open("@@ROOT@@/runtime/transport/templates/forward/"..name,'r');if not f then return nil end;local s=f:read('*a');f:close();return s end
function state.restore(reason)
 if not state.active then return end;state.active=false
 if rawget(target,'send')==wrapped then rawset(target,'send',raw)end
 if rawget(core,'get')==wrappedGet then rawset(core,'get',rawGet)end
 write('SENDER-FINAL.txt',tostring(state.calls));write('SERVER.txt','RESTORED '..reason..' sent='..state.calls)
end
local function pack(...)return{n=select('#',...),...}end
wrapped=function(self,...)
 if not state.active then return prior(self,...)end
 if state.calls>0 and (not guard.active or _G.localRepairIncrementalMapCountPilot~=guard)then state.restore('map owner no longer active');return prior(self,...)end
 local args=pack(...)
 if self~=target or args.n~=1 or type(args[1])~='table'then state.restore('signature fallback');return prior(self,...)end
 state.calls=state.calls+1
 local env={protocol='local-tracking-delta-v1',epoch='combined-nativecopy-20261010-133-forward',kind='full',sequence=state.calls,map=args[1]}
 local start=now();local binding=bindings[args[1]];local fullReason='initial or unbound snapshot'
 local same=binding and previous and binding.group==previous.group and binding.version==previous.version and binding.schema==previous.schema and binding.revision>=previous.revision
 local prepared,prepareError=pcall(function()
  if not(same and guard.active and _G.localRepairIncrementalMapCountPilot==guard and sp.db:getAutoCommit() and read('ACK'..(state.calls-1)..'.txt'))then return end
  local distance=binding.revision-previous.revision
  if distance>1000 then fullReason='revision distance';return end
  local coverage=sp.db:firstRow('SELECT COUNT(DISTINCT revision) AS n FROM temp.local_repair_map_journal WHERE revision>? AND revision<=?',previous.revision,binding.revision).n
  if coverage~=distance then fullReason='journal gap';return end
  local ids=sp.db:gatherArray('SELECT DISTINCT image FROM temp.local_repair_map_journal WHERE revision>? AND revision<=? LIMIT 1001',previous.revision,binding.revision)
  if #ids>1000 then fullReason='ID limit';return end
  local candidate={protocol=env.protocol,epoch=env.epoch,kind='delta',sequence=state.calls,base=state.calls-1,put={},remove={}}
  for _,id in ipairs(ids)do
   assert(type(id)=='number' and id==math.floor(id) and id>0)
   if args[1][id]==nil then candidate.remove[id]=true else assert(type(args[1][id])=='string');candidate.put[id]=args[1][id]end
  end
  for id in pairs(candidate.remove)do model[id]=nil end
  for id,v in pairs(candidate.put)do model[id]=v end
  if state.calls<=3 or state.calls%20==0 then
   for k,v in pairs(args[1])do assert(model[k]==v,'journal/native mismatch')end
   for k,v in pairs(model)do assert(args[1][k]==v,'journal/native extra entry')end
   state.oracles=state.oracles+1;write('SERVER.txt','FULL_NATIVE_ORACLE sequence='..state.calls..' equal=true')
  end
  env=candidate;state.deltas=state.deltas+1
  write('SERVER.txt','JOURNAL_DELTA sequence='..state.calls..' IDs='..#ids..' revisions='..distance..' noFullMapInEnvelope=true')
 end)
 if not prepared then fullReason='candidate failure '..tostring(prepareError);previous=nil end
 if env.kind=='full'then model=clone(args[1]);state.fulls=state.fulls+1;write('SERVER.txt','FULL_FALLBACK sequence='..state.calls..' reason='..fullReason)end
 previous=binding
 local construction=now()-start;state.constructionSeconds=state.constructionSeconds+construction
 write('SERVER.txt','CONSTRUCTION sequence='..state.calls..' kind='..env.kind..' seconds='..construction)
 write('SERVER.txt','SEND_INTENT sequence='..state.calls..' kind='..env.kind)
 local t=now();local result=pack(prior(self,env));local elapsed=now()-t;state.sendSeconds=state.sendSeconds+elapsed;write('SERVER.txt','SEND_RETURN sequence='..state.calls..' seconds='..elapsed)
 if not guard.active or _G.localRepairIncrementalMapCountPilot~=guard then state.restore('map owner ended during notification')end
 if state.calls>=1000 then state.restore('thousand bounded notifications')end
 return unpack(result,1,result.n)
end
function state.recover()
 state.restore('native full resync requested')
 local fresh
 sp:doInReadOnlySession(function(session)fresh=(require 'LrWFSyncStatusTrackedImageQueries').getTrackedImageIdMap(session)end)
 assert(type(fresh)=='table')
 state.calls=state.calls+1
 local env={protocol='local-tracking-delta-v1',epoch='combined-nativecopy-20261010-133-forward',kind='full',sequence=state.calls,map=fresh}
 prior(target,env);write('SENDER-FINAL.txt',tostring(state.calls));write('SERVER.txt','RECOVERY_FULL_SENT sequence='..state.calls)
end
local cleanup;cleanup=function()
 if not state.active then
  -- The exact local wrappers must no longer own these public methods.
  local methodsReleased=rawget(target,'send')~=wrapped and rawget(core,'get')~=wrappedGet
  local drained=state.calls==0
  if state.calls>0 then
   drained=true
   for i=1,state.calls do if read('ACK'..i..'.txt')~=tostring(i)..'\n' then drained=false;break end end
  end
  if methodsReleased and drained then
   -- Preserve a successor that acquired this global name.
   if rawget(_G,'localRepairJournalDelta1331010forward')~=state then return end
   rawset(_G,'localRepairJournalDelta1331010forward',nil)
   if state.calls==0 then
    write('SERVER.txt','RECOVERY_STATE_RELEASED calls=0 noEnvelopes=true ownedMethodsReleased=true')
   else
    write('SERVER.txt','RECOVERY_STATE_RELEASED ack='..state.calls..' deltas='..state.deltas..' fulls='..state.fulls..' oracles='..state.oracles..' constructionSeconds='..state.constructionSeconds..' sendSeconds='..state.sendSeconds)
   end
   return
  end
 end
 import 'AgEventLoop'.afterDelay(2,cleanup)
end
local recoveryControl;sp:doInReadOnlySession(function(session)recoveryControl=(require 'LrWFSyncStatusTrackedImageQueries').getTrackedImageIdMap(session)end);assert(type(recoveryControl)=='table','native recovery getter preflight failed');local controlCount=0;for k,v in pairs(recoveryControl)do assert(type(k)=='number'and type(v)=='string');controlCount=controlCount+1 end;recoveryControl=nil;write('SERVER.txt','NATIVE_RECOVERY_GETTER_PREFLIGHT entries='..controlCount)
wrappedGet=function(self,group)
 local result=pack(priorGet(self,group))
 if state.active and self==core and guard.active and _G.localRepairIncrementalMapCountPilot==guard and type(result[1])=='table'and sp.db:getAutoCommit()then
  local c=core.state;if c and c.group==group then bindings[result[1]]={group=group,revision=c.gen.revision,version=c.gen.version,schema=c.gen.schema}end
 end
 return unpack(result,1,result.n)
end
rawset(core,'get',wrappedGet)
rawset(target,'send',wrapped);_G.localRepairJournalDelta1331010forward=state
import 'AgEventLoop'.afterDelay(2,cleanup)
import 'AgEventLoop'.afterDelay(2400,function()state.restore('sender bound')end)
write('SERVER.txt','INSTALLED exact request='..target.id..' max1000/2400sec journal-derived acked deltas; no database writes')
return 'full envelope sender installed'
