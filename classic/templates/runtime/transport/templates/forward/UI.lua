local lib=import 'AgLibrary';assert(lib.getActiveCatalogPathIfAvailable()=='@@CATALOG@@')
assert(not _G.localRepairJournalReceiver1331010forward)
local root="@@ROOT@@/runtime/transport/templates/forward/";local now=import 'AgDate'.timeIntervalSinceReferenceDate;local loop=import 'AgEventLoop'
local function write(name,s)local f=assert(io.open(root..name,'a'));f:write(s..'\n');f:close()end
local function read(name)local f=io.open(root..name,'r');if not f then return nil end;local s=f:read('*a');f:close();return s end
local h=assert(rawget(lib.activeServer(),'_serverHandle'));local requests=assert(rawget(h,'requestMap'));local callbacks=assert(rawget(h,'callbacks'));local id,req;local n=0
for k,r in pairs(requests)do local a=type(r)=='table'and rawget(r,'args');if type(a)=='table'and rawget(r,'message')=='_runFuncOnDataServer'and a[1]=='com.adobe.ag.shadowland'and a[2]=='LrWFSyncStatusTrackedImageQueries'and a[3]=='listenForTrackedImageChanges'then id=k;req=r;n=n+1 end end
assert(n==1 and type(rawget(callbacks,id))=='function')
assert(string.lower((require 'WFCrypto').digestFile("@@ROOT@@/runtime/codec/DeltaMap.lua",'SHA256'))=='f9c918923bbf55bffbd24ca3f23303549c2edb2f190b98d77cd16c3c52c2ce5e')
local nativeCopy=assert(table.shallowcopy);assert(debug.getinfo(nativeCopy,'S').what=='C');local codec=assert(loadfile("@@ROOT@@/runtime/codec/DeltaMap.lua"))()("combined-nativecopy-20261010-133-forward",nativeCopy);local prior=rawget(callbacks,id);local state={received=0,active=true};local wrapped
function state.restore(reason)
 if not state.active then return end;state.active=false
 if rawget(callbacks,id)==wrapped then rawset(callbacks,id,prior)end
 _G.localRepairJournalReceiver1331010forward=nil;write('UI.txt','RESTORED '..reason..' received='..state.received)
end
wrapped=function(r,data)
 local env=type(data)=='table'and data.n==1 and data[1]
 if type(env)~='table'or env.protocol~='local-tracking-delta-v1'or env.epoch~="combined-nativecopy-20261010-133-forward" then return prior(r,data)end
 -- Every message in this pilot independently retains its complete native map.
 local ok,result=pcall(function()
  assert(rawget(requests,id)==req and (env.kind=='full'or env.kind=='delta'))
  if env.kind=='full' and state.received==0 then
    local copyOk,copyError=pcall(function()
    local totalLua,totalC=0,0
    for trial=1,3 do
     local t=now();local slow={};for k,v in pairs(env.map)do slow[k]=v end;totalLua=totalLua+now()-t
     t=now();local fast=nativeCopy(env.map);totalC=totalC+now()-t
     assert(fast~=env.map and fast~=slow and getmetatable(fast)==nil)
     local n,m=0,0;for k,v in pairs(slow)do assert(fast[k]==v);n=n+1 end;for k,v in pairs(fast)do assert(slow[k]==v);m=m+1 end;assert(n==m)
     local k=next(fast);if k then local value=fast[k];fast[k]='owned-copy-test';assert(env.map[k]==value and slow[k]==value);fast[k]=value end
     write('UI.txt','NATIVE_C_COPY_ORACLE trial='..trial..' entries='..n..' equal=true isolated=true')
    end
    assert(totalLua>totalC*1.2,'native copy benefit insufficient')
    write('UI.txt','NATIVE_C_COPY_BENCHMARK luaSeconds='..totalLua..' cSeconds='..totalC..' ratio='..totalLua/totalC)
    end)
    if not copyOk then codec=assert(loadfile('@@ROOT@@/runtime/codec/DeltaMap.lua'))()('combined-nativecopy-20261010-133-forward');write('UI.txt','NATIVE_C_COPY_DISABLED '..tostring(copyError))end
   end
   local decodeStart=now();local rebuilt=codec:accept(env);local decodeSeconds=now()-decodeStart;local entries=0
  if env.kind=='full'then for k,v in pairs(rebuilt)do entries=entries+1 end end
  if env.kind=='full'then
   for k,v in pairs(env.map)do assert(rebuilt[k]==v)end
   for k,v in pairs(rebuilt)do assert(env.map[k]==v)end
  end
  write('UI.txt','DECODED sequence='..env.sequence..' countedFullEntries='..entries..' kind='..env.kind..' validatedCodec=true decodeSeconds='..decodeSeconds)
  return rebuilt
 end)
 if not ok then
  write('UI.txt','DECODE_FAILURE '..tostring(result))
  local code="local r=...;local s=assert(_G.localRepairJournalDelta1331010forward,'retained recovery state absent');s.recover()"
  local recovery;recovery=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={code},callback=function()write('UI.txt','recovery callback');if recovery then recovery:close()end end,errorHandler=function(_,e)write('UI.txt','actual recovery error '..tostring(e));if recovery then recovery:close()end end}
  state.recovery=recovery;return
 end
 local packed={};for k,v in pairs(data)do packed[k]=v end;packed[1]=result
 local callbackStart=now();prior(r,packed);write('UI.txt','CALLBACK_BODY sequence='..env.sequence..' seconds='..(now()-callbackStart));state.received=env.sequence
 write('UI.txt','NATIVE_CALLBACK_RETURN sequence='..env.sequence);write('ACK'..env.sequence..'.txt',tostring(env.sequence))
end
rawset(callbacks,id,wrapped);_G.localRepairJournalReceiver1331010forward=state
local tick;tick=function()
 if not state.active then return end
 local contents=read('SENDER-FINAL.txt')or'';local final=tonumber(contents:match('(%d+)%s*$'))
 if final and final==state.received then state.restore('sender restored and all envelopes drained');return end
 if read('SERVER-NEVER-INSTALLED.txt')and state.received==0 then state.restore('sender preflight failed');return end
 loop.afterDelay(2,tick)
end
loop.afterDelay(2,tick)
write('UI.txt','INSTALLED exact request='..id..' receiver retains decoder until sender restored and all envelopes drained')
local source=assert(read('SERVER-TEMPLATE.lua')):gsub('EXPECTED',tostring(id));local handle
handle=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={source},callback=function()write('DISPATCH.txt','server callback received');if handle then handle:close()end end,errorHandler=function(_,err)write('DISPATCH.txt','actual server error '..tostring(err));if not read('SERVER.txt')then write('SERVER-NEVER-INSTALLED.txt','preflight failure')end;if handle then handle:close()end end}
state.handle=handle;write('DISPATCH.txt','submitted exact owner acked-delta pilot')
