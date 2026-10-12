-- Dedicated native user script: verified bounded guards only, no queue edits.
local lib=import 'AgLibrary'
assert(lib.getActiveCatalogPathIfAvailable()=='@@CATALOG@@','Wrong catalog: no changes')
assert(not _G.firstpairPersistentPerformanceRequest,'Previous request pending; inspect callback, never repeat')
local now=import 'AgDate'.timeIntervalSinceReferenceDate
local logRoot='@@ROOT@@/runs/run-'..string.format('%.6f',now())
import 'LrFileUtils'.createAllDirectories(logRoot)
local function log(s)local f=assert(io.open(logRoot..'/UI.txt','a'));f:write(s..'\n');f:close()end
-- Date no-op prevention has its own owner-bound request; transport drain does not postpone it.
if not _G.captureDateGuardInstaller241Request then
 local dateHandle
 local dateCode=[====[local request=...;local path='@@ROOT@@/runtime/date/Install.lua';assert(string.lower((require 'WFCrypto').digestFile(path,'SHA256'))=='a1509a5bbf480005f7e1a49554ccca5c51073603ef24290d11d68c52f32140e3');return assert(loadfile(path))()(request,"__DATE_LOGROOT__")]====]
 dateCode=dateCode:gsub('"__DATE_LOGROOT__"',function()return string.format('%q',logRoot)end)
 dateHandle=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={dateCode},callback=function(_,result)log('date guard callback '..tostring(result));if dateHandle then dateHandle:close()end;_G.captureDateGuardInstaller241Request=nil end,errorHandler=function(_,e)log('date guard actual error '..tostring(e));if dateHandle then dateHandle:close()end;_G.captureDateGuardInstaller241Request=nil end}
 _G.captureDateGuardInstaller241Request=dateHandle;log('date guard owner request submitted')
end
local code=[====[local request=...
local logRoot=__LOGROOT__
local function log(s)local f=assert(io.open(logRoot..'/native.txt','a'));f:write(s..'\n');f:close()end
local function phase0(request)
 if not @@SCHEMA@@ then return 'schema index creation disabled; native SHA lookup retained' end
 local sp=request:serverProperty('storeProvider');local db=sp.db
 assert(sp._mainDbPath=='@@CATALOG@@' and db.path==sp._mainDbPath and not sp.readServer)
 local definition="CREATE INDEX local_repair_upper_sha256_lookup ON AgLibraryFileAssetMetadata(UPPER(sha256))"
 local existing=db:firstRow("SELECT sql FROM sqlite_master WHERE type='index' AND name='local_repair_upper_sha256_lookup'")
 local created=false
 if existing.sql then assert(existing.sql==definition,'Index ownership changed')else
  assert(@@SCHEMA@@, 'Schema index creation disabled; independently preserve catalog family first')
  assert(db:getAutoCommit()==true,'Refuse nested index schema transaction')
  sp:doInSessionWithTransaction('Restore verified SHA expression index',function()
   local before=db:firstRow("SELECT total_changes() AS changes,(SELECT COUNT(*) FROM sqlite_master) AS schemaCount,(SELECT COUNT(*) FROM AgLibraryFileAssetMetadata) AS metadataCount")
   db:exec(definition);created=true
   local after=db:firstRow("SELECT total_changes() AS changes,(SELECT COUNT(*) FROM sqlite_master) AS schemaCount,(SELECT COUNT(*) FROM AgLibraryFileAssetMetadata) AS metadataCount")
   assert(before.changes==after.changes and before.metadataCount==after.metadataCount and after.schemaCount==before.schemaCount+1,'Unexpected schema-only changes')
   assert(db:firstRow("PRAGMA integrity_check('AgLibraryFileAssetMetadata')").integrity_check=='ok','Target index integrity failed')
  end)
  assert(db:getAutoCommit()==true,'Index transaction did not finish')
 end
 local rows=db:gatherArrayOfTables("EXPLAIN QUERY PLAN SELECT fileId,sha256 FROM AgLibraryFileAssetMetadata WHERE UPPER(sha256)='LOCAL_REPAIR_ABSENT_PROBE'");local used=false
 for _,r in ipairs(rows)do if tostring(r.detail):find('local_repair_upper_sha256_lookup',1,true)then used=true end end
 assert(used,'SHA index query plan not indexed');return created and 'created schema-only' or 'existing indexed'
end
local ok0,result0=pcall(phase0,request);log('PHASE 0 ok='..tostring(ok0)..' result='..tostring(result0));if not ok0 then return false end
local function phase1(...)
local priorState=_G.localRepairIncrementalMapCountPilot
if priorState and priorState.active then
 local current=(import 'AgDate').timeIntervalSinceReferenceDate()
 if not priorState.db or (current<priorState.deadline-600 and priorState.calls<24000) then return 'already active' end
 assert(rawget(priorState.db,'gatherMap')==priorState.mapWrapper and rawget(priorState.db,'gatherArray')==priorState.countWrapper,'Map method ownership changed')
 assert(priorState.db:getAutoCommit(),'Do not refresh within another transaction')
 local copyState=_G.localRepairCMapCopyOptimization;if copyState and copyState.active then copyState.restore('map owner guarded refresh')end
 priorState.restore('guarded refresh before bound');assert(not _G.localRepairIncrementalMapCountPilot,'Map cleanup pending; no duplicate owner')
end

local request=...
local sp=request:serverProperty('storeProvider')
local path='@@CATALOG@@'
assert(sp._mainDbPath==path and sp.db.path==path and not sp.readServer)
assert(@@BACKUP@@, 'Installation requires operator backup assurance')
if _G.localRepairIncrementalMapCountPilot then _G.localRepairIncrementalMapCountPilot.restore('superseded by guarded combined continuation');assert(not _G.localRepairIncrementalMapCountPilot,'Cleanup deferred') end
if _G.localRepairIncrementalMapCountPilot then local prior=_G.localRepairIncrementalMapCountPilot;assert(type(prior.restore)=='function');prior.restore('fresh guarded session restoration');assert(not _G.localRepairIncrementalMapCountPilot,'Prior TEMP cleanup deferred') end
local db=sp.db;assert(db:getAutoCommit())
local root='@@ROOT@@/runtime/'
local crypto=require 'WFCrypto'
assert(string.lower(crypto.digestFile(root..'incremental/MapAndCount.lua','SHA256'))=='bc020a99ce9e77a19c1e9af6f567030c31ed8096cd950e4a2b24e68a65bd7ff9','Map/count source changed')
assert(string.lower(crypto.digestFile(root..'incremental/journal.sql','SHA256'))=='54be14655f972b7a2ce56fbc2c07c5e5a46dfca69abffb4dd4632ac7d3024824','Map/count journal source changed')
local factory=assert(loadfile(root..'incremental/MapAndCount.lua'))()
local f=assert(io.open(root..'incremental/journal.sql','r'));local journal=f:read('*a');f:close()
local output=logRoot.."/phase1.txt"
local now=import 'AgDate'.timeIntervalSinceReferenceDate
local function write(s) local f=io.open(output,'a');if f then f:write(s..'\n');f:close() end end
local triggerNames={'local_repair_map_insert','local_repair_map_delete','local_repair_map_update','local_repair_photo_insert','local_repair_photo_delete','local_repair_photo_update'}
local ownedNames={};for _,n in ipairs(triggerNames) do ownedNames[#ownedNames+1]=n end
for _,n in ipairs({'local_repair_map_revision','local_repair_map_journal','local_repair_map_journal_revision'}) do ownedNames[#ownedNames+1]=n end
local quoted={};for _,n in ipairs(ownedNames) do quoted[#quoted+1]="'"..n.."'" end
local ownershipSQL='SELECT COUNT(*) AS n FROM sqlite_temp_master WHERE name IN ('..table.concat(quoted,',')..')'
local definitionSQL='SELECT name,type,tbl_name,sql FROM sqlite_temp_master WHERE name IN ('..table.concat(quoted,',')..') ORDER BY name'
local installedDefinitions
if _G.localRepairIncrementalMapPilot then _G.localRepairIncrementalMapPilot.restore('superseded by combined map/count pilot');assert(not _G.localRepairIncrementalMapPilot,'Prior TEMP cleanup deferred') end
if _G.localRepairSharedMapPilot then _G.localRepairSharedMapPilot.restore('superseded by combined map/count pilot') end
if _G.localRepairCountPilot then _G.localRepairCountPilot.restore('superseded by combined map/count pilot') end
assert(db:firstRow(ownershipSQL).n==0,'TEMP name collision')
local native=db.gatherMap
local nativeCount=db.gatherArray
assert(type(native)=='function')
sp:doInSessionWithTransaction('Temporary incremental mapping query pilot',function(session)
 local before=db:firstRow('SELECT total_changes() AS changes,(SELECT COUNT(*) FROM sqlite_master) AS schemas,(SELECT COUNT(*) FROM Adobe_images) AS images,(SELECT COUNT(*) FROM AgLibraryImageOzAssetIds) AS mappings')
 session:_execWithoutMutationCheck(journal)
 local after=db:firstRow('SELECT total_changes() AS changes,(SELECT COUNT(*) FROM sqlite_master) AS schemas,(SELECT COUNT(*) FROM Adobe_images) AS images,(SELECT COUNT(*) FROM AgLibraryImageOzAssetIds) AS mappings')
 assert(after.changes==before.changes+1 and after.schemas==before.schemas and after.images==before.images and after.mappings==before.mappings,'TEMP-only installation guard failed')
 assert(db:firstRow(ownershipSQL).n==9)
 installedDefinitions=db:gatherArrayOfTables(definitionSQL);assert(#installedDefinitions==9,'Installed TEMP definitions missing')
 for _,row in ipairs(installedDefinitions)do assert(type(row.name)=='string' and type(row.type)=='string' and type(row.tbl_name)=='string' and type(row.sql)=='string','Incomplete installed TEMP definition')end
 write('TEMP_INSTALL_GUARDS persistentSchemaUnchanged=true photoAndMappingCountsUnchanged=true totalChangesDelta=1 (TEMP revision seed only)')
end)
assert(db:getAutoCommit())
if _G.localRepairSharedMapPilot then _G.localRepairSharedMapPilot.restore('replaced by bounded incremental pilot') end
local previous=rawget(db,'gatherMap')
local previousCount=rawget(db,'gatherArray')
local core=factory(db,native)
local target=[[SELECT image, ozAssetId FROM AgLibraryImageOzAssetIds, Adobe_images WHERE AgLibraryImageOzAssetIds.image = Adobe_images.id_local AND ozCatalogId = ? AND UPPER( fileFormat ) != "VIDEO" AND UPPER( fileFormat ) != "UNSET"]]
local countTarget=target:gsub('SELECT image, ozAssetId','SELECT COUNT( * )')
local state={nativeMap=native,nativeCount=nativeCount,mapCalls=0,countCalls=0,comparedMap=0,comparedCount=0,busy=false,started=now(),deadline=now()+7200,calls=0,compared=0,mismatches=0,candidateErrors=0,candidateSeconds=0,oracleSeconds=0,core=core,active=true,cleanupPending=false,tempDefinitions=installedDefinitions}
local function status(label) return label..' calls='..state.calls..' mapCalls='..state.mapCalls..' countCalls='..state.countCalls..' comparedMap='..state.comparedMap..' comparedCount='..state.comparedCount..' fullReads='..core.fullReads..' deltaReads='..core.deltaReads..' bypasses='..core.bypasses..' gapFallbacks='..core.gapFallbacks..' compared='..state.compared..' mismatches='..state.mismatches..' candidateErrors='..state.candidateErrors..' candidateSeconds='..state.candidateSeconds..' oracleSeconds='..state.oracleSeconds..' elapsed='..(now()-state.started) end
local function ownsDefinitions()
 local current=db:gatherArrayOfTables(definitionSQL)
 if #current~=#installedDefinitions then return false end
 for i,row in ipairs(current)do local expected=installedDefinitions[i];if row.name~=expected.name or row.type~=expected.type or row.tbl_name~=expected.tbl_name or row.sql~=expected.sql then return false end end
 return true
end
local function holdRestoration(reason)
 state.restorationHeld=true;state.active=false;state.cleanupPending=true
 write(status('HELD_RESTORATION '..reason..'; foreign methods/TEMP definitions retained; owned global retained'))
 return false
end
function state.cleanup()
 if state.restorationHeld then return false end
 if rawget(_G,'localRepairIncrementalMapCountPilot')~=state then return holdRestoration('global owner changed') end
 if rawget(db,'gatherMap')~=previous or rawget(db,'gatherArray')~=previousCount then return holdRestoration('method owner changed before cleanup') end
 if not db:getAutoCommit() then state.cleanupPending=true;write('CLEANUP_DEFERRED active transaction');return false end
 if not ownsDefinitions() then return holdRestoration('TEMP definitions changed before cleanup') end
 sp:doInSessionWithTransaction('Remove exact owned temporary mapping journal',function(session)
  assert(rawget(_G,'localRepairIncrementalMapCountPilot')==state and rawget(db,'gatherMap')==previous and rawget(db,'gatherArray')==previousCount,'Cleanup ownership changed; no DROP')
  assert(ownsDefinitions(),'Cleanup TEMP definitions changed; no DROP')
  for _,name in ipairs(triggerNames)do session:_execWithoutMutationCheck('DROP TRIGGER temp.'..name)end
  session:_execWithoutMutationCheck('DROP TABLE temp.local_repair_map_journal;DROP TABLE temp.local_repair_map_revision;')
  assert(db:firstRow(ownershipSQL).n==0,'TEMP cleanup incomplete')
 end)
 assert(rawget(_G,'localRepairIncrementalMapCountPilot')==state,'Cleanup global ownership changed; no clear')
 state.cleanupPending=false;_G.localRepairIncrementalMapCountPilot=nil;write(status('TEMP_CLEANUP_COMPLETE'));return true
end
function state.restore(reason)
 if state.restorationHeld then return false end
 if state.active then
  if rawget(_G,'localRepairIncrementalMapCountPilot')~=state or rawget(db,'gatherMap')~=state.mapWrapper or rawget(db,'gatherArray')~=state.countWrapper then return holdRestoration('map/count wrapper ownership changed before restore') end
  if not ownsDefinitions() then return holdRestoration('TEMP definitions changed before restore') end
  rawset(db,'gatherMap',previous);rawset(db,'gatherArray',previousCount);state.active=false;core.state=nil;write(status('RESTORED reason='..reason))
 end
 local ok,err=pcall(state.cleanup)
 if not ok then state.cleanupPending=true;write('CLEANUP_ERROR '..tostring(err)) end
 return ok and not state.cleanupPending
end
local function equal(a,b) for k,v in pairs(a) do if b[k]~=v then return false end end;for k,v in pairs(b) do if a[k]~=v then return false end end;return true end
local function wrapper(isCount,self,sql,...)
 local original=isCount and nativeCount or native
 if not state.active or state.restorationHeld then return original(self,sql,...) end
 if state.busy then return original(self,sql,...) end
 if now()>state.deadline or state.calls>=30000 then state.restore('bounded pilot complete');return original(self,sql,...) end
 local group=select(1,...)
 local expectedSql=isCount and countTarget or target
 if self~=db or type(sql)~='string' or sql:gsub('%s+',' ')~=expectedSql or select('#',...)~=1 or (type(group)~='string' and type(group)~='number') then return original(self,sql,...) end
 state.calls=state.calls+1
 if isCount then state.countCalls=state.countCalls+1 else state.mapCalls=state.mapCalls+1 end
 local start=now();state.busy=true
 local ok,result=pcall(isCount and core.getCount or core.get,core,group)
 state.busy=false;state.candidateSeconds=state.candidateSeconds+now()-start
 if not ok then state.candidateErrors=state.candidateErrors+1;write('CANDIDATE_ERROR '..tostring(result));state.restore('candidate error');return original(self,sql,...) end
 local typeCalls=isCount and state.countCalls or state.mapCalls
 if typeCalls<=5 or typeCalls%100==0 then
  start=now();local expected=original(self,sql,...);state.oracleSeconds=state.oracleSeconds+now()-start;state.compared=state.compared+1
  if isCount then state.comparedCount=state.comparedCount+1 else state.comparedMap=state.comparedMap+1 end
  if type(expected)~='table' or not equal(result,expected) then state.mismatches=state.mismatches+1;state.restore('full native oracle mismatch');return expected end
 end
 if state.calls%5==0 then write(status('PROGRESS')) end
 if db:firstRow('SELECT COUNT(*) AS n FROM temp.local_repair_map_journal').n>50000 then state.restore('bounded journal limit') end
 return result
end
state.db=db;state.mapWrapper=function(self,sql,...)return wrapper(false,self,sql,...)end;state.countWrapper=function(self,sql,...)return wrapper(true,self,sql,...)end
rawset(db,'gatherMap',state.mapWrapper)
rawset(db,'gatherArray',state.countWrapper)
_G.localRepairIncrementalMapCountPilot=state
write(status('INSTALLED boundedSeconds=7200 maxCalls=30000 maxJournalRows=50000; first5/every100 of each type native oracle; NULL-valued mapping eligibility retained; TEMP journal only; catalog rows unchanged'))
return 'bounded incremental map pilot installed' 

end
local ok1,result1=pcall(phase1,request);log('PHASE 1 ok='..tostring(ok1)..' result='..tostring(result1));if not ok1 then return false end
local function phase2(...)
local copyState=_G.localRepairCMapCopyOptimization
if copyState and copyState.active then
 local current=(import 'AgDate').timeIntervalSinceReferenceDate()
 local currentOwner=_G.localRepairIncrementalMapCountPilot
 if copyState.owner==currentOwner and currentOwner and currentOwner.active then
  assert(rawget(currentOwner.core,'get')==copyState.wrapper,'Copy method ownership changed')
  if current-copyState.started<6600 and copyState.calls<24000 then return 'already active' end
 end
 copyState.restore('revalidate current owner or refresh before bound');assert(not _G.localRepairCMapCopyOptimization)
end
local request=...;local sp=request:serverProperty('storeProvider');assert(sp._mainDbPath=='@@CATALOG@@')
assert(not _G.localRepairCMapCopyOptimization)
local owner=assert(_G.localRepairIncrementalMapCountPilot);assert(owner.active)
local core=owner.core; if not core.state then local rows=sp.db:gatherArrayOfTables('SELECT DISTINCT ozCatalogId FROM AgLibraryImageOzAssetIds WHERE ozCatalogId IS NOT NULL'); assert(#rows==1 and rows[1].ozCatalogId,'Ambiguous cloud catalog: wait for native map initialization'); core:get(rows[1].ozCatalogId) end;assert(core.state);local group=core.state.group
local native=assert(table.shallowcopy);assert(debug.getinfo(native,'S').what=='C')
local sample={[42]='a',[99]='b'};local copy=native(sample);assert(type(copy)=='table' and copy~=sample and copy[42]=='a' and copy[99]=='b');copy[42]='changed';assert(sample[42]=='a')
local prior=core.get;local priorRaw=rawget(core,'get');local now=import 'AgDate'.timeIntervalSinceReferenceDate;local loop=import 'AgEventLoop'
local function write(s)local f=assert(io.open(logRoot.."/phase2.txt",'a'));f:write(tostring(now())..' '..s..'\n');f:close()end
local function equal(a,b)local n=0;for k,v in pairs(a)do assert(b[k]==v,'Map value mismatch');n=n+1 end;local m=0;for k in pairs(b)do assert(a[k]~=nil,'Map key mismatch');m=m+1 end;assert(n==m);return n end
local refreshSeconds,copySeconds,oracleSeconds=0,0,0
local function fast(self,g)local t=now();local map=self:refresh(g);refreshSeconds=refreshSeconds+now()-t;assert(type(map)=='table' and getmetatable(map)==nil);t=now();local out=native(map);copySeconds=copySeconds+now()-t;assert(type(out)=='table' and out~=map and getmetatable(out)==nil);return out end
local target=[[SELECT image, ozAssetId FROM AgLibraryImageOzAssetIds, Adobe_images WHERE AgLibraryImageOzAssetIds.image = Adobe_images.id_local AND ozCatalogId = ? AND UPPER( fileFormat ) != "VIDEO" AND UPPER( fileFormat ) != "UNSET"]]
local oldTime,newTime=0,0
for i=1,3 do
 local t=now();local baseline=prior(core,group);local old=now()-t
 t=now();local candidate=fast(core,group);local new=now()-t
 local expected=owner.nativeMap(sp.db,target,group);local n=equal(candidate,expected);equal(candidate,baseline)
 local key=next(candidate);if key then local value=candidate[key];candidate[key]='owned diagnostic mutation';assert(core.state.map[key]==value);candidate[key]=value end
 equal(candidate,expected);oldTime=oldTime+old;newTime=newTime+new
 write('BENCHMARK '..i..' rows='..n..' priorSeconds='..old..' candidateSeconds='..new..' nativeOracleEqual=true sourceMutationIsolated=true')
end
if not(oldTime>newTime*1.2)then write('SKIPPED_COPY_OPTIMIZATION priorSeconds='..oldTime..' candidateSeconds='..newTime..' requiredSpeedup=1.2 ordinaryGetterRetained=true');return 'copy optimization skipped; ordinary getter retained' end
refreshSeconds,copySeconds,oracleSeconds=0,0,0 -- Exclude startup benchmarks from serving intervals.
local state={active=true,calls=0,started=now(),seconds=0,owner=owner};local wrapped
local function restore(reason)
 if not state.active then return end;state.active=false
 if rawget(core,'get')==wrapped then rawset(core,'get',priorRaw)end
 _G.localRepairCMapCopyOptimization=nil;write('RESTORED '..reason..' calls='..state.calls..' seconds='..state.seconds)
end
wrapped=function(self,g)
 if not state.active then return prior(self,g)end
 if self~=core or g~=group or not owner.active or now()-state.started>7200 or state.calls>=30000 then restore('bound');return prior(self,g)end
 state.calls=state.calls+1;local t=now()
 local ok,result=pcall(fast,self,g)
 if not ok then write('CANDIDATE_ERROR '..tostring(result));restore('native copy error');return prior(self,g)end
 if state.calls<=5 or state.calls%100==0 then
  local oracleStarted=now();local expected=owner.nativeMap(sp.db,target,g);local same,why=pcall(equal,result,expected);oracleSeconds=oracleSeconds+now()-oracleStarted
  if not same then write('MISMATCH '..tostring(why));restore('oracle mismatch');return prior(self,g)end
  write('NATIVE_ORACLE calls='..state.calls..' fullMapEqual=true')
 end
 state.seconds=state.seconds+now()-t
 if state.calls%50==0 then write('PROGRESS calls='..state.calls..' seconds='..state.seconds..' refreshSeconds='..refreshSeconds..' copySeconds='..copySeconds..' oracleSeconds='..oracleSeconds)end
 return result
end
state.restore=restore
state.wrapper=wrapped;rawset(core,'get',wrapped);_G.localRepairCMapCopyOptimization=state;loop.afterDelay(7200,function()restore('timer')end)
write('INSTALLED max30000calls/7200seconds; nativeC table.shallowcopy; source isolation/full native oracles preserved; no SQL changes; copyBenchmarkSpeedup='..oldTime/newTime)
return true

end
local ok2,result2=pcall(phase2,request);log('PHASE 2 ok='..tostring(ok2)..' result='..tostring(result2));if not ok2 then return false end
local function phase3(...)
local trackingState=_G.localRepairPointTrackingPilot
if trackingState then
 assert(not trackingState.restorationHeld,'Point restoration held; ownership retained; no fresh installation')
 assert(trackingState.active==true and trackingState.wrapper and rawget(trackingState.module,'isImageIdTracked')==trackingState.wrapper,'Point method ownership changed; no fresh installation')
 local current=(import 'AgDate').timeIntervalSinceReferenceDate()
 if not trackingState.wrapper or (current<trackingState.deadline-600 and trackingState.calls<720000) then return 'already active' end
 assert(trackingState.module.isImageIdTracked==trackingState.wrapper,'Point method ownership changed')
 trackingState.restore('guarded refresh before bound');assert(not _G.localRepairPointTrackingPilot)
end

local request=...
local sp=request:serverProperty("storeProvider")
assert(sp._mainDbPath=="@@CATALOG@@")
local queries=import 'AgWFSyncTrackImagesQueries'
local current=require 'LrWFSyncStatusCurrentOzCatalogIdQueries'
assert(not _G.localRepairPointTrackingPilot,"Pilot already installed")
local original=queries.isImageIdTracked
local originalRaw=rawget(queries,'isImageIdTracked')
assert(type(original)=="function")
local now=import 'AgDate'.timeIntervalSinceReferenceDate
local sql="SELECT ozAssetId FROM AgLibraryImageOzAssetIds JOIN Adobe_images ON AgLibraryImageOzAssetIds.image=Adobe_images.id_local WHERE AgLibraryImageOzAssetIds.image=? AND ozCatalogId=? AND UPPER(fileFormat)!='VIDEO' AND UPPER(fileFormat)!='UNSET'"
local out=logRoot.."/phase3.txt"
local function write(text)
 local f=io.open(out,"a");if f then f:write(text.."\n");f:close() end
end
local state={active=true,started=now(),deadline=now()+7200,calls=0,compared=0,mismatches=0,fallbacks=0,pointSeconds=0,oracleSeconds=0,original=original,module=queries}
local wrapper
local function status(label)
 return label.." calls="..state.calls.." compared="..state.compared.." mismatches="..state.mismatches.." fallbacks="..state.fallbacks.." pointSeconds="..state.pointSeconds.." oracleSeconds="..state.oracleSeconds.." elapsed="..(now()-state.started)
end
local function restore(reason)
 if not state.active then return not state.restorationHeld end
 if rawget(_G,'localRepairPointTrackingPilot')~=state or rawget(queries,'isImageIdTracked')~=wrapper then
  state.restorationHeld=true;state.active=false;pcall(write,status('HELD_RESTORATION point wrapper/global owner changed; foreign method and global retained'));return false
 end
 rawset(queries,"isImageIdTracked",originalRaw);state.active=false
 _G.localRepairPointTrackingPilot=nil
 pcall(write,status("RESTORED reason="..reason))
 return true
end
state.restore=restore
wrapper=function(session,imageId)
 if not state.active then return original(session,imageId) end
 if now()>state.deadline or state.calls>=900000 then restore("bounded pilot complete");return original(session,imageId) end
 if type(session)~="table" or session.storeProvider~=sp or type(imageId)~="number" then state.fallbacks=state.fallbacks+1;return original(session,imageId) end
 state.calls=state.calls+1
 local start=now()
 local ok,value=pcall(function()
  local oz=current.maybeGetCurrentOzCatalogIdForSession(session)
  if oz==nil then return nil end
  return sp.db:firstRow(sql,imageId,oz).ozAssetId
 end)
 state.pointSeconds=state.pointSeconds+now()-start
 if not ok then state.fallbacks=state.fallbacks+1;restore("candidate error");return original(session,imageId) end
 if state.calls<=10 or state.calls%100==0 then
  start=now();local expected=original(session,imageId);state.oracleSeconds=state.oracleSeconds+now()-start
  state.compared=state.compared+1
  if expected~=value then state.mismatches=state.mismatches+1;restore("oracle mismatch");return expected end
 end
 if state.calls%100==0 then pcall(write,status("PROGRESS")) end
 return value
end
state.wrapper=wrapper;rawset(queries,"isImageIdTracked",wrapper)
_G.localRepairPointTrackingPilot=state
write(status("INSTALLED boundedSeconds=7200 maxCalls=900000 first10AndEvery100OracleComparisons; query results only; no DB writes"))
return "bounded direct tracking lookup pilot installed"

end
local ok3,result3=pcall(phase3,request);log('PHASE 3 ok='..tostring(ok3)..' result='..tostring(result3));if not ok3 then return false end
local function phase4(...)
if not @@AFFINITY@@ then log('AFFINITY_DISABLED_PUBLIC_STARTER');return 'disabled until native qualification' end
local request=...;local sp=request:serverProperty('storeProvider');assert(sp._mainDbPath=='@@CATALOG@@' and not sp.readServer);local db=sp.db;assert(db:getAutoCommit(),'do not take existing transaction');
local now=import 'AgDate'.timeIntervalSinceReferenceDate;local loop=import 'AgEventLoop';local original="CREATE TRIGGER trigger_AgLibraryImageChangeCounter_update_for_fileModification\n\tAFTER UPDATE OF modTime ON AgLibraryFile\n\tFOR EACH ROW\n\tBEGIN\n\t\n\t\tINSERT INTO update_AgLibraryImageChangeCounter_for_image\n\t\t\tSELECT id_local FROM Adobe_images\n\t\t\tWHERE rootFile = OLD.id_local;\n\t\t\n\t\tDELETE FROM AgLibraryImageSyncedAssetData\n\t\t\tWHERE payloadKey IN ( '/importSource/sha256', \n\t\t\t\t\t\t\t\t  '/width', '/height' )\n\t\t\t\tAND image IN(\n\t\t\t\t\tSELECT id_local FROM Adobe_images\n\t\t\t\t\tWHERE rootFile = OLD.id_local );\n\t\t\t\t\t\n\t\tDELETE FROM AgLibraryFileAssetMetadata\n\t\t\tWHERE fileId = OLD.id_local;\n\t\t\t\n\t\t\n\t\n\tEND";local corrected="CREATE TRIGGER trigger_AgLibraryImageChangeCounter_update_for_fileModification\n\tAFTER UPDATE OF modTime ON AgLibraryFile\n\tFOR EACH ROW\n\tBEGIN\n\t\n\t\tINSERT INTO update_AgLibraryImageChangeCounter_for_image\n\t\t\tSELECT id_local FROM Adobe_images\n\t\t\tWHERE rootFile = OLD.id_local;\n\t\t\n\t\tDELETE FROM AgLibraryImageSyncedAssetData\n\t\t\tWHERE payloadKey IN ( '/importSource/sha256', \n\t\t\t\t\t\t\t\t  '/width', '/height' )\n\t\t\t\tAND image IN(\n\t\t\t\t\tSELECT +id_local FROM Adobe_images\n\t\t\t\t\tWHERE rootFile = OLD.id_local );\n\t\t\t\t\t\n\t\tDELETE FROM AgLibraryFileAssetMetadata\n\t\t\tWHERE fileId = OLD.id_local;\n\t\t\t\n\t\t\n\t\n\tEND";local name="trigger_AgLibraryImageChangeCounter_update_for_fileModification"
local function log(s)local f=assert(io.open(logRoot..'/phase4.txt','a'));f:write(tostring(now())..' '..s..'\n');f:close()end
local prior=_G.metadataLiveAffinity005
if prior then
 local row=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#row==1,'Metadata trigger absent')
 if prior.active then
  assert(row[1].sql==corrected and prior.corrected==corrected and prior.original==original,'Active metadata owner/SQL changed')
  if now()<prior.expires-600 then log('ALREADY_ACTIVE expires='..prior.expires);return true end
  prior.restore();assert(not prior.active,'Original metadata restoration pending')
  row=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#row==1,'Restored metadata trigger absent')
 end
 assert(row[1].sql==original,'Inactive metadata owner not restored');_G.metadataLiveAffinityPrevious=prior;_G.metadataLiveAffinity005=nil
end
log('ENTER user-authorized live native TEMP correction bound7200seconds')
local globals=db:gatherArrayOfTables("SELECT image,typeof(image) AS image_type FROM (SELECT DISTINCT image FROM AgLibraryImageSyncedAssetData LIMIT -1 OFFSET 0) WHERE typeof(image) NOT IN ('integer','real') OR image != CAST(image AS INTEGER) LIMIT 1");assert(#globals==0,'unsupported global image key; no mutation');log('GLOBAL_NUMERIC_INTEGRAL_KEYS_VERIFIED')
local function selectRows(expr)return db:gatherArrayOfTables("SELECT rowid AS row_id,image,typeof(image) AS image_type,payloadKey "..(expr=="id_local" and "FROM AgLibraryImageSyncedAssetData INDEXED BY index_AgLibraryImageSyncedAssetData_primaryKey WHERE likelihood(payloadKey IN ('/importSource/sha256','/width','/height'),0.5)" or "FROM AgLibraryImageSyncedAssetData WHERE payloadKey IN ('/importSource/sha256','/width','/height')").." AND image IN (SELECT "..expr.." FROM Adobe_images WHERE rootFile IN (SELECT DISTINCT rootFile FROM Adobe_images WHERE rootFile IS NOT NULL ORDER BY rootFile LIMIT 20)) ORDER BY rowid")end
sp:doInSessionWithTransaction('Apply bounded native metadata index affinity correction',function(session)
 local triggers=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#triggers==1 and triggers[1].sql==original,'exact native TEMP SQL changed')
 local a=selectRows('id_local');local b=selectRows('+id_local');assert(#a>0,'Empty selected metadata scope; no mutation');assert(#a==#b,'selected counts differ');for i,x in ipairs(a)do local y=b[i];assert(x.row_id==y.row_id and x.image==y.image and x.image_type==y.image_type and x.payloadKey==y.payloadKey,'selected rows differ');assert((x.image_type=='integer' or x.image_type=='real') and x.image==math.floor(x.image),'nonintegral image')end;log('SELECTED_ROWS_EQUAL dynamicScope20 rows='..#a)
 local plans=db:gatherArrayOfTables("EXPLAIN QUERY PLAN SELECT image FROM AgLibraryImageSyncedAssetData WHERE payloadKey IN ('/importSource/sha256','/width','/height') AND image IN (SELECT +id_local FROM Adobe_images WHERE rootFile=(SELECT MIN(rootFile) FROM Adobe_images WHERE rootFile IS NOT NULL))");local good=false;for _,q in ipairs(plans)do if q.detail:find('image=? AND payloadKey=?',1,true) then good=true end end;assert(good,'indexed plan missing')
 session:_execWithoutMutationCheck('DROP TRIGGER temp.'..name);session:_execWithoutMutationCheck((corrected:gsub('CREATE TRIGGER','CREATE TEMP TRIGGER',1)));local check=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#check==1 and check[1].sql==corrected);log('CORRECTED_TRIGGER_INSTALLED_ONLY_DELETE_RHS_CHANGED')
end)
local state={active=true,expires=now()+7200,original=original,corrected=corrected};_G.metadataLiveAffinity005=state
local function restore()
 if not state.active then return end
 if not db:getAutoCommit() then loop.afterDelay(1,restore);return end
 local ok,err=pcall(function()sp:doInSessionWithTransaction('Restore native metadata affinity trigger',function(session)local r=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#r==1 and r[1].sql==corrected,'trigger ownership changed; no overwrite');session:_execWithoutMutationCheck('DROP TRIGGER temp.'..name);session:_execWithoutMutationCheck((original:gsub('CREATE TRIGGER','CREATE TEMP TRIGGER',1)))end)end)
 if ok then state.active=false;log('ORIGINAL_TRIGGER_RESTORED')else log('RESTORATION_ERROR '..tostring(err))end
end
state.restore=restore;loop.afterDelay(7200,restore);log('LIVE_INSTALLED deadline='..state.expires..' native counters and all deletion statements retained');return true

end
local ok4,result4=pcall(phase4,request);log('PHASE 4 ok='..tostring(ok4)..' result='..tostring(result4));if not ok4 then return false end

local function phase6(request)
if not @@AFFINITY@@ then log('FOLDER_AFFINITY_DISABLED_PUBLIC_STARTER');return 'disabled until native qualification' end
 local path="@@ROOT@@/runtime/affinity/FolderRename.lua"
 assert(string.lower((require "WFCrypto").digestFile(path,"SHA256"))=="8eca621eb101237aa571c7c817e6018d1e368acf1c6e4630bffd3ad868ccd433","Folder affinity source changed")
 return assert(loadfile(path))()(request,logRoot)
end
local ok6,result6=pcall(phase6,request);log("PHASE 6 ok="..tostring(ok6).." result="..tostring(result6));if not ok6 then return false end
local function phase5(request)
 local path='@@ROOT@@/runtime/date/Install.lua'
 assert(string.lower((require 'WFCrypto').digestFile(path,'SHA256'))=='a1509a5bbf480005f7e1a49554ccca5c51073603ef24290d11d68c52f32140e3','date guard installer changed')
 return assert(loadfile(path))()(request,logRoot)
end
local ok5,result5=pcall(phase5,request);log('PHASE 5 ok='..tostring(ok5)..' result='..tostring(result5));if not ok5 then return false end
return true
]====]
local sealedTemplate=code
code=code:gsub('__LOGROOT__',function()return string.format('%q',logRoot)end)
local transportGatePath="@@ROOT@@/runtime/transport/RenewalGate.lua"
assert(string.lower((require 'WFCrypto').digestFile(transportGatePath,'SHA256'))=="badaf56b3e667cd082e3cb70380cad6e9674d79ad096b0ba6fadf8b68b878bd1",'renewal gate changed')
local transportGate=assert(loadfile(transportGatePath))()(_G)
transportGate.stopFutureCycles() -- only UI coordinator; current native sender is never interrupted
local function startMapTransport()
 local ok,err=pcall(function()
  local crypto=require 'WFCrypto'
  assert(string.lower(crypto.digestFile("@@ROOT@@/runtime/transport/Start.lua",'SHA256'))=="8c96750da0b12d5e7a3ee97f1fcf55b906fb4a0001f9234c0490ce6f09ffde30",'startup transport source changed')
  assert(loadfile("@@ROOT@@/runtime/transport/Start.lua"))()
 end)
 log('transport startup hook ok='..tostring(ok)..' actualError='..tostring(err))
end
local transportReady,releaseCode=transportGate.ready()
if transportReady then
local handle
handle=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={releaseCode..code},callback=function(request,result)log('native callback result='..tostring(result));if handle then handle:close()end;_G.firstpairPersistentPerformanceRequest=nil;if result==true then startMapTransport()end end,errorHandler=function(_,err)log('actual server error='..tostring(err));if handle then handle:close()end;_G.firstpairPersistentPerformanceRequest=nil end}
_G.firstpairPersistentPerformanceRequest=handle
log('submitted; callback and phase/native-oracle receipts required')
else log('WAIT transport drain; no native phase renewal submitted') end

-- Dormant until explicit authorization; every renewal uses the unchanged bounded/oracle-gated native installer.
local authorizationPath="@@ROOT@@"..'/AUTOMATIC-RENEWAL-AUTHORIZED'
local function renewalAuthorized()
 local paused=io.open("@@ROOT@@"..'/PAUSED','r');if paused then paused:close();return false end
 local auth=io.open(authorizationPath,'r');local authorized=auth and auth:read('*a')=='FirstPair authorized bounded per-invocation renewal\n';if auth then auth:close()end
 return authorized
end
local authorized=renewalAuthorized()
if authorized and _G.firstpairPerformanceAutomaticRenewal and _G.firstpairPerformanceAutomaticRenewal.revision~='sha-phase0-transport-zero-event-v1-split-folder-rename-v3-date-v1' then _G.firstpairPerformanceAutomaticRenewal.active=false;_G.firstpairPerformanceAutomaticRenewalPrevious=_G.firstpairPerformanceAutomaticRenewal;_G.firstpairPerformanceAutomaticRenewal=nil end
if authorized and _G.firstpairPerformanceAutomaticRenewal and not _G.firstpairPerformanceAutomaticRenewal.active then _G.firstpairPerformanceAutomaticRenewalPrevious=_G.firstpairPerformanceAutomaticRenewal;_G.firstpairPerformanceAutomaticRenewal=nil end
if authorized and not _G.firstpairPerformanceAutomaticRenewal then
 local state={active=true,checks=0,interval=300,revision='sha-phase0-transport-zero-event-v1-split-folder-rename-v3-date-v1'};_G.firstpairPerformanceAutomaticRenewal=state
 local loop=import 'AgEventLoop';local dirs=import 'LrFileUtils';dirs.createAllDirectories("@@ROOT@@"..'/maintenance')
 local function note(s)local f=assert(io.open("@@ROOT@@"..'/maintenance/events.txt','a'));f:write(tostring(now())..' '..s..'\n');f:close()end
 local tick
 tick=function()
  if not state.active then return end
  if not renewalAuthorized() then state.active=false;note('STOP operator disabled future renewal; existing native requests retained');return end
  if lib.getActiveCatalogPathIfAvailable()~='@@CATALOG@@' then state.active=false;note('STOP wrong catalog; no queue or Sync action');return end
  if _G.firstpairPersistentPerformanceRequest then note('WAIT actual native request retained; no duplicate submission');loop.afterDelay(state.interval,tick);return end
  if not _G.captureDateGuardInstaller241Request then
   local dh
   dh=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={[====[local request=...;local path='@@ROOT@@/runtime/date/Install.lua';assert(string.lower((require 'WFCrypto').digestFile(path,'SHA256'))=='a1509a5bbf480005f7e1a49554ccca5c51073603ef24290d11d68c52f32140e3');return assert(loadfile(path))()(request,'@@ROOT@@/maintenance')]====]},callback=function(_,result)note('DATE_GUARD_RENEWAL '..tostring(result));if dh then dh:close()end;_G.captureDateGuardInstaller241Request=nil end,errorHandler=function(_,e)note('DATE_GUARD_RENEWAL_ERROR '..tostring(e));if dh then dh:close()end;_G.captureDateGuardInstaller241Request=nil;state.active=false end}
   _G.captureDateGuardInstaller241Request=dh
  end
  local ready,releaseCode=transportGate.ready();if not ready then note('WAIT transport drain; native fixes untouched');loop.afterDelay(state.interval,tick);return end
  state.checks=state.checks+1
  local root="@@ROOT@@"..'/runs/run-'..string.format('%.6f',now());dirs.createAllDirectories(root)
  local nativeCode,replacements=sealedTemplate:gsub('__LOGROOT__',function()return string.format('%q',root)end);assert(replacements==1,'renewal logRoot binding failed');assert(not nativeCode:find('__LOGROOT__',1,true))
  local function event(s)local f=assert(io.open(root..'/UI.txt','a'));f:write(s..'\n');f:close()end
  local h;h=lib.activeServer():asapRequest{namespace='AgServerUtils',message='runOnServer',args={releaseCode..nativeCode},callback=function(request,result)event('native callback result='..tostring(result));if h then h:close()end;_G.firstpairPersistentPerformanceRequest=nil;if result=='WAIT_TRANSPORT_RELEASE' then note('WAIT native transport ownership release; fixes untouched')elseif result~=true then state.active=false;note('STOP native phase failed; retained evidence; no automatic retry')else startMapTransport()end end,errorHandler=function(request,err)event('actual server error='..tostring(err));if h then h:close()end;_G.firstpairPersistentPerformanceRequest=nil;state.active=false;note('STOP actual native error; no automatic retry')end}
  _G.firstpairPersistentPerformanceRequest=h;event('automatic guarded renewal check submitted; unchanged bounded native phases')
  loop.afterDelay(state.interval,tick)
 end
 note('AUTHORIZED_BACKGROUND_CHECKS installed300seconds; per-invocation safety bounds retained; callback failure stops maintenance')
 loop.afterDelay(state.interval,tick)
end
