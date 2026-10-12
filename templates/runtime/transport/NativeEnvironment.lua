-- Prepared factory; native environment is created only by an authorized caller.
return function(root,config)
 local lib=import 'AgLibrary';local dirs=import 'LrFileUtils';local loop=import 'AgEventLoop';local date=import 'AgDate';local crypto=require 'WFCrypto'
 dirs.createAllDirectories(root..'/runs')
 local env={}
 env.now=date.timeIntervalSinceReferenceDate
 env.catalog=lib.getActiveCatalogPathIfAvailable
 env.after=function(seconds,callback)loop.afterDelay(seconds,callback)end
 env.exists=function(path)return dirs.exists(path)~=false and dirs.exists(path)~=nil end
 env.mkdir=function(path)dirs.createAllDirectories(path)end
 env.read=function(path)local f=io.open(path,'rb');if not f then return nil end;local s=f:read('*a');f:close();return s end
 env.write=function(path,text)local f=assert(io.open(path,'wb'));f:write(text);f:close()end
 env.digest=function(path)local h=crypto.digestFile(path,'SHA256');assert(type(h)=='string');return string.lower(h)end
 env.compile=function(text)local f=loadstring(text);return f~=nil end
 env.note=function(text)local f=assert(io.open(root..'/events.txt','a'));f:write(tostring(env.now())..' '..text..'\n');f:close()end
 env.dispatch=function(path)assert(loadfile(path))()end
 env.gate=function(job,completion)
  -- Wait for the two exact native UI listeners before any transport dispatch.
  local handle=rawget(lib.activeServer(),'_serverHandle')
  local requests=handle and rawget(handle,'requestMap')
  local callbacks=handle and rawget(handle,'callbacks')
  local ready=type(requests)=='table' and type(callbacks)=='table'
  if ready then
   for _,method in ipairs({'listenForTrackedImageChanges','watchForAssetIdToImageIdChanges'}) do
    local count=0;local selected
    for id,r in pairs(requests) do
     local args=type(r)=='table' and rawget(r,'args')
     if type(args)=='table' and rawget(r,'message')=='_runFuncOnDataServer' and args[1]=='com.adobe.ag.shadowland' and args[2]=='LrWFSyncStatusTrackedImageQueries' and args[3]==method then count=count+1;selected=id end
    end
    if count~=1 or type(callbacks[selected])~='function' then ready=false end
   end
  end
  if not ready then env.after(0,function()completion(false)end);return nil end
  local clientNames={};for _,name in ipairs(config.legacyClientGlobals)do clientNames[#clientNames+1]=name end
  if job then for _,name in ipairs(job.clientGlobals)do clientNames[#clientNames+1]=name end end
  for _,name in ipairs(clientNames)do if _G[name] then env.after(0,function()completion(false)end);return nil end end
  local nativeNames={};for _,name in ipairs(config.legacyNativeGlobals)do nativeNames[#nativeNames+1]=name end
  if job then for _,name in ipairs(job.nativeGlobals)do nativeNames[#nativeNames+1]=name end end
  local literals={};for _,name in ipairs(nativeNames)do assert(name:match('^[%a_][%w_]*$'));literals[#literals+1]=string.format('%q',name)end
  local code=[[local request=...;local sp=request:serverProperty('storeProvider');assert(sp._mainDbPath=='@@CATALOG@@' and not sp.readServer)
if not sp.db:getAutoCommit()then return false end
local guard=_G.localRepairIncrementalMapCountPilot
if not guard or not guard.active or guard.mismatches~=0 or guard.candidateErrors~=0 then return false end
-- Require the 2400-second sender bound plus 300 seconds of drain headroom.
if type(guard.deadline)~='number' or guard.deadline-(import 'AgDate').timeIntervalSinceReferenceDate()<2700 then return false end
for _,name in ipairs({]]..table.concat(literals,',')..[[})do if _G[name]then return false end end
return true]]
  local handle;handle=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={code},callback=function(_,result)if handle then handle:close()end;completion(result==true)end,errorHandler=function(_,actualError)if handle then handle:close()end;completion(false,tostring(actualError))end}
  return handle
 end
 return env
end
