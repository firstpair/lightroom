local request = ...
local logRoot = __LOGROOT__
local now = import 'AgDate'.timeIntervalSinceReferenceDate
local loop = import 'AgEventLoop'
local function write(s) local f = io.open(logRoot .. '/native.txt', 'a'); if f then f:write(string.format('%.3f ', now()) .. s .. '\n'); f:close() end end
local sp = request:serverProperty('storeProvider'); local db = sp.db
assert(sp._mainDbPath == __CATALOG__ and db.path == sp._mainDbPath and not sp.readServer, 'not Main')
local prior = _G.lrc16MapCount
if prior and (prior.active or prior.cleanupPending) then write('ALREADY_ACTIVE'); return 'ALREADY_ACTIVE' end
for _, g in ipairs({ 'lrc16SlowQueryTrace', 'lrc16ImportProfile' }) do local s = _G[g]; assert(not (s and s.active), g .. ' still active') end
assert(rawget(db, 'gatherMap') == nil and rawget(db, 'gatherArray') == nil, 'another wrapper owns gatherMap/gatherArray')
if not db:getAutoCommit() then write('WAIT transaction open'); return 'WAIT_TRANSACTION' end
local factory = assert(loadstring([===[-- Research factory; TEMP journal must already exist on the supplied connection.
local FULL=[[SELECT image, ozAssetId FROM AgLibraryImageOzAssetIds, Adobe_images WHERE AgLibraryImageOzAssetIds.image = Adobe_images.id_local AND ozCatalogId = ? AND UPPER( fileFormat ) != "VIDEO" AND UPPER( fileFormat ) != "UNSET"]]
return function(db,nativeGatherMap)
 nativeGatherMap=nativeGatherMap or db.gatherMap
 local cache={fullReads=0,deltaReads=0,bypasses=0,gapFallbacks=0,state=nil}
 local function clone(map)
  assert(type(map)=='table' and getmetatable(map)==nil)
  local out={}
  for k,v in pairs(map) do assert(type(k)=='number' and type(v)=='string');out[k]=v end
  return out
 end
 local function generation()
  return db:firstRow([[SELECT revision,(SELECT data_version FROM pragma_data_version) AS version,(SELECT schema_version FROM pragma_schema_version) AS schema FROM temp.local_repair_map_revision WHERE singleton=1]])
 end
 local function same(a,b) return a.revision==b.revision and a.version==b.version and a.schema==b.schema end
 local function full(group)
  cache.fullReads=cache.fullReads+1
  local map=nativeGatherMap(db,FULL,group);local count=0;local nullable={}
  for k,v in pairs(map) do assert(type(k)=='number' and type(v)=='string');count=count+1 end
  local nullSQL=FULL:gsub('SELECT image, ozAssetId','SELECT image')..' AND ozAssetId IS NULL'
  for _,id in ipairs(db:gatherArray(nullSQL,group)) do nullable[id]=true;count=count+1 end
  return map,count,nullable
 end
 function cache:refresh(group)
  assert(type(group)=='number' or type(group)=='string')
  if not db:getAutoCommit() then cache.state=nil;cache.bypasses=cache.bypasses+1;return full(group) end
  local before=generation();assert(type(before.revision)=='number' and type(before.version)=='number' and type(before.schema)=='number')
  local old=cache.state;local map,count,nullable
  if not old or old.group~=group or old.gen.version~=before.version or old.gen.schema~=before.schema or old.gen.revision>before.revision then
   map,count,nullable=full(group)
  else
   map=old.map;count=old.count;nullable=old.nullable
   if old.gen.revision<before.revision then
    local distance=before.revision-old.gen.revision
    local coverage=db:firstRow('SELECT COUNT(DISTINCT revision) AS n FROM temp.local_repair_map_journal WHERE revision>? AND revision<=?',old.gen.revision,before.revision).n
    if coverage~=distance or distance>1000 then
     cache.gapFallbacks=cache.gapFallbacks+1;map,count,nullable=full(group)
    else
     local ids=db:gatherArray('SELECT DISTINCT image FROM temp.local_repair_map_journal WHERE revision>? AND revision<=? LIMIT 1001',old.gen.revision,before.revision)
     if #ids>1000 then cache.gapFallbacks=cache.gapFallbacks+1;map,count,nullable=full(group)
     else
      cache.deltaReads=cache.deltaReads+1
      for _,id in ipairs(ids) do
       local row=db:firstRow(FULL..' AND image=?',group,id)
       assert(row.ozAssetId==nil or type(row.ozAssetId)=='string')
       local was=map[id]~=nil or nullable[id]==true
       local present=row.image~=nil
       count=count+(present and 1 or 0)-(was and 1 or 0)
       map[id]=row.ozAssetId
       nullable[id]=(present and row.ozAssetId==nil) and true or nil
      end
     end
    end
   end
  end
  local after=generation()
  if not db:getAutoCommit() or not same(before,after) then cache.state=nil;return full(group) end
  cache.state={group=group,gen=after,map=map,count=count,nullable=nullable}
  return map,count
 end
 function cache:get(group) local map=self:refresh(group);return clone(map) end
 function cache:getCount(group) local _,count=self:refresh(group);return {count} end
 return cache
end
]===], 'IncrementalMapAndCount'))()
local journal = [===[CREATE TEMP TABLE local_repair_map_revision(singleton INTEGER PRIMARY KEY CHECK(singleton=1),revision INTEGER NOT NULL);
INSERT INTO local_repair_map_revision VALUES(1,0);
CREATE TEMP TABLE local_repair_map_journal(revision INTEGER NOT NULL,image INTEGER NOT NULL);
CREATE INDEX temp.local_repair_map_journal_revision ON local_repair_map_journal(revision,image);
CREATE TEMP TRIGGER local_repair_map_insert AFTER INSERT ON main.AgLibraryImageOzAssetIds BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.image FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_map_delete AFTER DELETE ON main.AgLibraryImageOzAssetIds BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.image FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_map_update AFTER UPDATE OF image,ozCatalogId,ozAssetId ON main.AgLibraryImageOzAssetIds
 WHEN OLD.image IS NOT NEW.image OR OLD.ozCatalogId IS NOT NEW.ozCatalogId OR OLD.ozAssetId IS NOT NEW.ozAssetId BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.image FROM local_repair_map_revision;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.image FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_photo_insert AFTER INSERT ON main.Adobe_images BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.id_local FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_photo_delete AFTER DELETE ON main.Adobe_images BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.id_local FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_photo_update AFTER UPDATE OF id_local,fileFormat ON main.Adobe_images
 WHEN OLD.id_local IS NOT NEW.id_local OR OLD.fileFormat IS NOT NEW.fileFormat BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.id_local FROM local_repair_map_revision;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.id_local FROM local_repair_map_revision;
END;
]===]
local triggerNames = { 'local_repair_map_insert', 'local_repair_map_delete', 'local_repair_map_update', 'local_repair_photo_insert', 'local_repair_photo_delete', 'local_repair_photo_update' }
local ownedNames = {}; for _, n in ipairs(triggerNames) do ownedNames[#ownedNames + 1] = n end
for _, n in ipairs({ 'local_repair_map_revision', 'local_repair_map_journal', 'local_repair_map_journal_revision' }) do ownedNames[#ownedNames + 1] = n end
local quoted = {}; for _, n in ipairs(ownedNames) do quoted[#quoted + 1] = "'" .. n .. "'" end
local ownershipSQL = 'SELECT COUNT(*) AS n FROM sqlite_temp_master WHERE name IN (' .. table.concat(quoted, ',') .. ')'
assert(db:firstRow(ownershipSQL).n == 0, 'TEMP name collision')
local native = db.gatherMap; local nativeCount = db.gatherArray
assert(type(native) == 'function' and type(nativeCount) == 'function')
local okTx, errTx = pcall(sp.doInSessionWithTransaction, sp, 'LrC16 incremental map journal', function(session)
 assert(not db:getAutoCommit(), 'savepoint did not open (statements in progress): no change')
 local q = 'SELECT total_changes() AS changes,(SELECT COUNT(*) FROM sqlite_master) AS schemas,(SELECT COUNT(*) FROM Adobe_images) AS images,(SELECT COUNT(*) FROM AgLibraryImageOzAssetIds) AS mappings'
 local before = db:firstRow(q)
 session:_execWithoutMutationCheck(journal)
 local after = db:firstRow(q)
 assert(after.changes == before.changes + 1 and after.schemas == before.schemas and after.images == before.images and after.mappings == before.mappings, 'TEMP-only installation guard failed')
 assert(db:firstRow(ownershipSQL).n == 9, 'TEMP objects not all created')
end)
if not okTx then write('NO_CHANGE ' .. tostring(errTx)); return 'WAIT_TRANSACTION' end
assert(db:firstRow(ownershipSQL).n == 9, 'TEMP objects missing after commit')
write('TEMP_INSTALLED journal triggers=6; persistent schema and photo/mapping counts unchanged')
local core = factory(db, native)
local target = [[SELECT image, ozAssetId FROM AgLibraryImageOzAssetIds, Adobe_images WHERE AgLibraryImageOzAssetIds.image = Adobe_images.id_local AND ozCatalogId = ? AND UPPER( fileFormat ) != "VIDEO" AND UPPER( fileFormat ) != "UNSET"]]
local countTarget = (target:gsub('SELECT image, ozAssetId', 'SELECT COUNT( * )'))
local state = { active = true, cleanupPending = false, busy = false, started = now(), deadline = now() + 21600, calls = 0, mapCalls = 0, countCalls = 0, compared = 0, mismatches = 0, candidateErrors = 0, candidateSeconds = 0, oracleSeconds = 0, core = core }
local function status(label) return string.format('%s calls=%d map=%d count=%d fullReads=%d deltaReads=%d bypasses=%d gapFallbacks=%d compared=%d mismatches=%d errors=%d candidateSeconds=%.3f oracleSeconds=%.3f', label, state.calls, state.mapCalls, state.countCalls, core.fullReads, core.deltaReads, core.bypasses, core.gapFallbacks, state.compared, state.mismatches, state.candidateErrors, state.candidateSeconds, state.oracleSeconds) end
local function cleanup()
 if not db:getAutoCommit() then state.cleanupPending = true; write('CLEANUP_DEFERRED transaction open'); loop.afterDelay(30, function() pcall(cleanup) end); return false end
 for _, name in ipairs(triggerNames) do db:exec('DROP TRIGGER IF EXISTS temp.' .. name) end
 db:exec('DROP TABLE IF EXISTS temp.local_repair_map_journal; DROP TABLE IF EXISTS temp.local_repair_map_revision;')
 assert(db:firstRow(ownershipSQL).n == 0, 'TEMP cleanup incomplete')
 state.cleanupPending = false; write(status('TEMP_CLEANUP_COMPLETE')); return true
end
function state.restore(reason)
 if state.active then
  if rawget(db, 'gatherMap') == state.mapWrapper then rawset(db, 'gatherMap', nil) else write('NOT_RESTORED gatherMap ownership changed') end
  if rawget(db, 'gatherArray') == state.countWrapper then rawset(db, 'gatherArray', nil) else write('NOT_RESTORED gatherArray ownership changed') end
  state.active = false; core.state = nil; pcall(write, status('RESTORED reason=' .. reason))
 end
 local ok, err = pcall(cleanup); if not ok then state.cleanupPending = true; write('CLEANUP_ERROR ' .. tostring(err)) end
end
local function equal(a, b) for k, v in pairs(a) do if b[k] ~= v then return false end end; for k, v in pairs(b) do if a[k] ~= v then return false end end; return true end
local function wrapper(isCount, self, sql, ...)
 local original = isCount and nativeCount or native
 if state.busy or not state.active then return original(self, sql, ...) end
 if self ~= db or type(sql) ~= 'string' or select('#', ...) ~= 1 then return original(self, sql, ...) end
 local expectedSql = isCount and countTarget or target
 if #sql < 150 or sql:gsub('%s+', ' ') ~= expectedSql then return original(self, sql, ...) end
 local group = ...
 if type(group) ~= 'string' and type(group) ~= 'number' then return original(self, sql, ...) end
 if now() > state.deadline or state.calls >= 200000 then state.restore('bound reached'); return original(self, sql, ...) end
 state.calls = state.calls + 1
 if isCount then state.countCalls = state.countCalls + 1 else state.mapCalls = state.mapCalls + 1 end
 local t0 = now(); state.busy = true
 local ok, result = pcall(isCount and core.getCount or core.get, core, group)
 state.busy = false; state.candidateSeconds = state.candidateSeconds + now() - t0
 if not ok then state.candidateErrors = state.candidateErrors + 1; write('CANDIDATE_ERROR ' .. tostring(result)); state.restore('candidate error'); return original(self, sql, ...) end
 local n = isCount and state.countCalls or state.mapCalls
 if n <= 5 or n % 100 == 0 then
  t0 = now(); local expected = original(self, sql, ...); state.oracleSeconds = state.oracleSeconds + now() - t0; state.compared = state.compared + 1
  if type(expected) ~= 'table' or not equal(result, expected) then state.mismatches = state.mismatches + 1; write('MISMATCH isCount=' .. tostring(isCount)); state.restore('native oracle mismatch'); return expected end
 end
 if state.calls % 20 == 0 then pcall(write, status('PROGRESS')) end
 if state.calls % 50 == 0 and db:firstRow('SELECT COUNT(*) AS n FROM temp.local_repair_map_journal').n > 50000 then state.restore('journal limit') end
 return result
end
state.mapWrapper = function(self, sql, ...) return wrapper(false, self, sql, ...) end
state.countWrapper = function(self, sql, ...) return wrapper(true, self, sql, ...) end
rawset(db, 'gatherMap', state.mapWrapper); rawset(db, 'gatherArray', state.countWrapper)
_G.lrc16MapCount = state
loop.afterDelay(21600, function() if state.active then state.restore('timer6h') end end)
write(status('INSTALLED bound=6h/200K calls/50K journal rows; oracle first5+every100 per type; TEMP journal only'))
return true
