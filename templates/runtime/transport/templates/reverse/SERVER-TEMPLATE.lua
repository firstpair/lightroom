local request=...
local sp=request:serverProperty('storeProvider');assert(sp._mainDbPath=='@@CATALOG@@')
local target=(require 'LrWFSyncStatusQueriesCaching').getStashedRequest(sp,'assetIdToImageIdMapChangedRequest')
assert(type(target)=='table' and target.id==EXPECTED,'exact request ID mismatch')
assert(not _G.localRepairReverseJournalDelta1331010reverse)
local raw=rawget(target,'send');local prior=assert(target.send);local now=import 'AgDate'.timeIntervalSinceReferenceDate
local function write(name,s)local f=assert(io.open("@@ROOT@@/runtime/transport/templates/reverse/"..name,'a'));f:write(s..'\n');f:close()end
local codecPath="@@ROOT@@/runtime/codec/ReverseDeltaMap.lua"
assert(string.lower((require 'WFCrypto').digestFile(codecPath,'SHA256'))=='904c5db99849a6d882f748c88fcb42adb3be3e7cd4ca8cf3c2f62e3a0bc5d115','Reverse codec source changed')
local codec=assert(loadfile(codecPath))()('combined-nativecopy-20261010-133-reverse')

local guard=assert(_G.localRepairIncrementalMapCountPilot);assert(guard.active and guard.mismatches==0 and guard.candidateErrors==0)
local helper="@@ROOT@@/runtime/incremental/ReverseMapCache.lua";assert(string.lower((require 'WFCrypto').digestFile(helper,'SHA256'))=='d2eef7788a318503fab9a9ccf964fac53cd4b762157ea1c4d3b2e2bcd8408a06')
local owner=require 'LrWFSyncStatusOzIdQueries';local getter=owner.getAssetIdToImageIdMap;local rawGetter=rawget(owner,'getAssetIdToImageIdMap');local cache=assert(loadfile(helper))()(sp.db,getter);local binding,lastGen;local getWrapper
local function same(a,b)return a and b and a.revision==b.revision and a.version==b.version and a.schema==b.schema end

local state={calls=0,gets=0,active=true};local wrapped;local recoveryGroup
local function read(name)local f=io.open("@@ROOT@@/runtime/transport/templates/reverse/"..name,'r');if not f then return nil end;local s=f:read('*a');f:close();return s end
function state.restore(reason)
 if not state.active then return end;state.active=false
 if rawget(target,'send')==wrapped then rawset(target,'send',raw)end
 if rawget(owner,'getAssetIdToImageIdMap')==getWrapper then rawset(owner,'getAssetIdToImageIdMap',rawGetter)end;binding=nil;cache.state=nil
 write('SENDER-FINAL.txt',tostring(state.calls));write('SERVER.txt','RESTORED '..reason..' sent='..state.calls)
end
local function pack(...)return{n=select('#',...),...}end
wrapped=function(self,...)
 if not state.active then return prior(self,...)end
 if state.calls>0 and (not guard.active or _G.localRepairIncrementalMapCountPilot~=guard)then state.restore('map owner no longer active');return prior(self,...)end
 local args=pack(...)
 if self~=target or args.n~=1 or type(args[1])~='table'then state.restore('signature fallback');return prior(self,...)end
 state.calls=state.calls+1
 local env={protocol='local-reverse-delta-v1',epoch='combined-nativecopy-20261010-133-reverse',kind='full',sequence=state.calls,map=args[1]}
 local patch=binding and binding.patch
 if state.calls>1 and read('ACK'..(state.calls-1)..'.txt') and binding and binding.map==args[1] and patch and patch.output==args[1] and patch.group==binding.group and same(patch.from,lastGen) and same(patch.to,binding.gen) and sp.db:getAutoCommit() then
  local candidate={protocol=env.protocol,epoch=env.epoch,kind='delta',sequence=state.calls,base=state.calls-1,put=patch.put,remove=patch.remove}
  local check=state.calls<=3 or state.calls%20==0
  if check then
   local rebuilt=codec:accept(candidate);local entries=0
   for k,v in pairs(args[1])do assert(rebuilt[k]==v,'producer full equality');entries=entries+1 end;for k,v in pairs(rebuilt)do assert(args[1][k]==v,'producer reverse equality')end
   write('SERVER.txt','ORACLE sequence='..state.calls..' entries='..entries..' equal=true')
  else
   -- Producer model updates only; full output construction reserved for oracles.
   for k in pairs(candidate.remove)do codec.map[k]=nil end;for k,v in pairs(candidate.put)do codec.map[k]=v end;codec.sequence=state.calls
  end
  env=candidate;write('SERVER.txt','JOURNAL_DELTA sequence='..state.calls..' noFullMapInEnvelope=true')
 else codec:accept(env);write('SERVER.txt','FULL_BASELINE_OR_BINDING_ACK_FALLBACK sequence='..state.calls)end
 lastGen=binding and binding.gen;binding=nil
 write('SERVER.txt','SEND_INTENT sequence='..state.calls..' kind='..env.kind)
 local t=now();local result=pack(prior(self,env));write('SERVER.txt','SEND_RETURN sequence='..state.calls..' seconds='..(now()-t))
 if not guard.active or _G.localRepairIncrementalMapCountPilot~=guard then state.restore('map owner ended during notification')end
 if state.calls>=1000 then state.restore('thousand bounded notifications')end
 return unpack(result,1,result.n)
end
function state.recover()
 state.restore('native full resync requested')
 local fresh
 sp:doInReadOnlySession(function(session)
  local group=(require 'LrWFSyncStatusCurrentOzCatalogIdQueries').maybeGetCurrentOzCatalogIdForSession(session)
  assert(group==recoveryGroup,'Current Cloud catalog changed; no recovery dispatch')
  fresh=(require 'LrWFSyncStatusOzIdQueries').getAssetIdToImageIdMap(session,group)
 end)
 assert(type(fresh)=='table')
 state.calls=state.calls+1
 local env={protocol='local-reverse-delta-v1',epoch='combined-nativecopy-20261010-133-reverse',kind='full',sequence=state.calls,map=fresh}
 prior(target,env);write('SENDER-FINAL.txt',tostring(state.calls));write('SERVER.txt','RECOVERY_FULL_SENT sequence='..state.calls)
end
local cleanup;cleanup=function()
 if not state.active then
  -- The exact local wrappers must no longer own these public methods.
  local methodsReleased=rawget(target,'send')~=wrapped and rawget(owner,'getAssetIdToImageIdMap')~=getWrapper
  local drained=state.calls==0
  if state.calls>0 then
   drained=true
   for i=1,state.calls do if read('ACK'..i..'.txt')~=tostring(i)..'\n' then drained=false;break end end
  end
  if methodsReleased and drained then
   -- Preserve a successor that acquired this global name.
   if rawget(_G,'localRepairReverseJournalDelta1331010reverse')~=state then return end
   rawset(_G,'localRepairReverseJournalDelta1331010reverse',nil)
   if state.calls==0 then
    write('SERVER.txt','RECOVERY_STATE_RELEASED calls=0 noEnvelopes=true ownedMethodsReleased=true')
   else
    write('SERVER.txt','RECOVERY_STATE_RELEASED ack='..state.calls)
   end
   return
  end
 end
 import 'AgEventLoop'.afterDelay(2,cleanup)
end
local recoveryControl;sp:doInReadOnlySession(function(session)
 recoveryGroup=(require 'LrWFSyncStatusCurrentOzCatalogIdQueries').maybeGetCurrentOzCatalogIdForSession(session)
 assert(type(recoveryGroup)=='string' and recoveryGroup~='','Current Cloud catalog missing')
 recoveryControl=(require 'LrWFSyncStatusOzIdQueries').getAssetIdToImageIdMap(session,recoveryGroup)
end);assert(type(recoveryControl)=='table','native recovery getter preflight failed');local controlCount=0;for k,v in pairs(recoveryControl)do assert(type(k)=='string'and type(v)=='number' and v>0 and v==math.floor(v));controlCount=controlCount+1 end;recoveryControl=nil;write('SERVER.txt','NATIVE_RECOVERY_GETTER_PREFLIGHT entries='..controlCount)
getWrapper=function(session,group)
 if not state.active then return getter(session,group)end
 if _G.localRepairIncrementalMapCountPilot~=guard or not guard.active or guard.mismatches~=0 or guard.candidateErrors~=0 then state.restore('guard changed');return getter(session,group)end
 local ok,map=pcall(cache.get,cache,session,group)
 if not ok then state.restore('cache error '..tostring(map));return getter(session,group)end
 state.gets=state.gets+1
 if state.gets<=3 or state.gets%20==0 then local native=getter(session,group);local equal=true;for k,v in pairs(native)do if map[k]~=v then equal=false end end;for k,v in pairs(map)do if native[k]~=v then equal=false end end;if not equal then state.restore('getter mismatch');return native end;write('SERVER.txt','GETTER_ORACLE '..state.gets..' equal=true')end
 binding={map=map,patch=cache.lastPatch,gen=cache.state and cache.state.gen,group=group};return map
end
rawset(owner,'getAssetIdToImageIdMap',getWrapper)
rawset(target,'send',wrapped);_G.localRepairReverseJournalDelta1331010reverse=state
import 'AgEventLoop'.afterDelay(2,cleanup)
import 'AgEventLoop'.afterDelay(2400,function()state.restore('sender bound')end)
write('SERVER.txt','INSTALLED exact request='..target.id..' max1000/2400sec acked baseline plus delta; no database writes')
return 'full envelope sender installed'
