local request = ...
local logRoot = __LOGROOT__
local clock = import 'AgDate'.timeIntervalSinceReferenceDate
local function log(s) local f = assert(io.open(logRoot .. '/native.txt', 'a')); f:write(string.format('%.3f ', clock()) .. s .. '\n'); f:close() end
local function norm(s) return (s:gsub('%s+', ' '):gsub('^ ', ''):gsub(' $', '')) end

local TRIGGERS = {
 { name = 'trigger_AgLibraryImageChangeCounter_update_for_fileModification',
   original = "CREATE TRIGGER trigger_AgLibraryImageChangeCounter_update_for_fileModification AFTER UPDATE OF modTime ON AgLibraryFile FOR EACH ROW BEGIN INSERT INTO update_AgLibraryImageChangeCounter_for_image SELECT id_local FROM Adobe_images WHERE rootFile = OLD.id_local; DELETE FROM AgLibraryImageSyncedAssetData WHERE payloadKey IN ( '/importSource/sha256', '/width', '/height' ) AND image IN( SELECT id_local FROM Adobe_images WHERE rootFile = OLD.id_local ); DELETE FROM AgLibraryFileAssetMetadata WHERE fileId = OLD.id_local; END",
   keys = "'/importSource/sha256','/width','/height'" },
 { name = 'trigger_AgLibraryImageChangeCounter_update_for_fileRename',
   original = "CREATE TRIGGER trigger_AgLibraryImageChangeCounter_update_for_fileRename AFTER UPDATE OF folder, idx_filename ON AgLibraryFile FOR EACH ROW BEGIN INSERT INTO update_AgLibraryImageChangeCounter_for_image SELECT id_local FROM Adobe_images WHERE rootFile = NEW.id_local; DELETE FROM AgLibraryImageSyncedAssetData WHERE image IN (SELECT id_local FROM Adobe_images WHERE rootFile = NEW.id_local ) AND +payloadKey IN ( '/importSource/folder', '/importSource/fileName' ); END",
   keys = "'/importSource/folder','/importSource/fileName'" },
}

-- Replace "SELECT id_local" with "SELECT +id_local" only after the DELETE FROM AgLibraryImageSyncedAssetData; exactly once.
local function correct(sql)
 local at = sql:find('DELETE FROM AgLibraryImageSyncedAssetData', 1, true); assert(at, 'DELETE not found')
 local head, tail = sql:sub(1, at - 1), sql:sub(at)
 local fixed, n = tail:gsub('SELECT id_local FROM Adobe_images', 'SELECT +id_local FROM Adobe_images', 1)
 assert(n == 1, 'subquery not found exactly once')
 assert(not fixed:find('SELECT id_local FROM Adobe_images', 1, true), 'second subquery in DELETE part')
 return head .. fixed
end

local sp = request:serverProperty('storeProvider'); local db = sp.db
assert(sp._mainDbPath == __CATALOG__ and db.path == sp._mainDbPath and not sp.readServer, 'not the Main writer for this catalog')
assert(type(sp.doInSessionWithTransaction) == 'function', 'doInSessionWithTransaction missing in this version')
if not db:getAutoCommit() then log('WAIT another transaction is open; no change'); return 'WAIT_TRANSACTION' end
log('ENTER LrC16 trigger fix')

-- 1. Read the live triggers and decide what to do.
local todo = {}
for _, t in ipairs(TRIGGERS) do
 local rows = db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE type='trigger' AND name='" .. t.name .. "'")
 assert(#rows == 1, t.name .. ' not present: no change')
 local live = rows[1].sql
 assert(live:sub(1, 15) == 'CREATE TRIGGER ', t.name .. ' unexpected prefix')
 if norm(live) == norm(correct(t.original)) then log('ALREADY_CORRECTED ' .. t.name)
 else
  assert(norm(live) == t.original, t.name .. ' live SQL differs from LrC 16.0 text: no change')
  t.live = live; t.fixed = correct(live); todo[#todo + 1] = t
  log('LIVE_SQL_MATCHES_16.0 ' .. t.name)
 end
end
if #todo == 0 then log('NOTHING_TO_DO'); return true end

-- 2. The change is only safe if every image key is a whole number (no text keys). One pass over the index.
local t0 = clock()
local bad = db:gatherArrayOfTables("SELECT image, typeof(image) AS ty FROM (SELECT DISTINCT image FROM AgLibraryImageSyncedAssetData LIMIT -1 OFFSET 0) WHERE typeof(image) NOT IN ('integer','real') OR image != CAST(image AS INTEGER) LIMIT 1")
assert(#bad == 0, 'non-integer image key found: no change')
log(string.format('ALL_IMAGE_KEYS_WHOLE_NUMBERS %.1fs', clock() - t0))

-- 3. On the 40 newest files, the stock and corrected subqueries must select exactly the same rows.
local ids = {}
for _, r in ipairs(db:gatherArrayOfTables('SELECT id_local FROM AgLibraryFile ORDER BY id_local DESC LIMIT 40')) do ids[#ids + 1] = string.format('%d', r.id_local) end
local idlist = table.concat(ids, ',')
for _, t in ipairs(todo) do
 local function rowsFor(expr, hint)
  local r = db:gatherArrayOfTables('SELECT rowid AS rid, image, payloadKey FROM AgLibraryImageSyncedAssetData ' .. hint ..
   ' WHERE payloadKey IN (' .. t.keys .. ') AND image IN (SELECT ' .. expr .. ' FROM Adobe_images WHERE rootFile IN (' .. idlist .. '))')
  local s = {}; for _, x in ipairs(r) do s[#s + 1] = string.format('%d|%s|%s', x.rid, tostring(x.image), x.payloadKey) end
  table.sort(s); return table.concat(s, '\n'), #r
 end
 local t1 = clock()
 local a, na = rowsFor('id_local', 'INDEXED BY index_AgLibraryImageSyncedAssetData_primaryKey')
 local t2 = clock()
 local b, nb = rowsFor('+id_local', '')
 local t3 = clock()
 assert(a == b, t.name .. ': stock and corrected select different rows: no change')
 log(string.format('SAME_ROWS %s rows=%d stock=%.3fs corrected=%.3fs', t.name, na, t2 - t1, t3 - t2))
 local plan = db:gatherArrayOfTables('EXPLAIN QUERY PLAN DELETE FROM AgLibraryImageSyncedAssetData WHERE payloadKey IN (' .. t.keys .. ') AND image IN (SELECT +id_local FROM Adobe_images WHERE rootFile = 1)')
 local ok = false; for _, p in ipairs(plan) do if tostring(p.detail):find('(image=?', 1, true) then ok = true end end
 assert(ok, t.name .. ': corrected plan is not an indexed lookup: no change')
end

-- 4. Swap the triggers in one transaction (rolled back on any error).
local okTx, errTx = pcall(sp.doInSessionWithTransaction, sp, 'LrC16 trigger affinity fix', function(session)
 assert(type(session._execWithoutMutationCheck) == 'function', '_execWithoutMutationCheck missing')
 assert(not db:getAutoCommit(), 'savepoint did not open (statements in progress): no change')
 for _, t in ipairs(todo) do
  local r = db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE type='trigger' AND name='" .. t.name .. "'")
  assert(#r == 1 and r[1].sql == t.live, t.name .. ' changed during check: no change')
  session:_execWithoutMutationCheck('DROP TRIGGER temp.' .. t.name)
  session:_execWithoutMutationCheck((t.fixed:gsub('^CREATE TRIGGER ', 'CREATE TEMP TRIGGER ', 1)))
  local c = db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE type='trigger' AND name='" .. t.name .. "'")
  assert(#c == 1 and c[1].sql == t.fixed, t.name .. ' install verification failed')
 end
end)
if not okTx then log('NO_CHANGE ' .. tostring(errTx)); return 'WAIT_TRANSACTION' end
for _, t in ipairs(todo) do log('CORRECTED ' .. t.name) end
_G.lrc16TriggerFix = { installed = clock(), names = { todo[1].name, todo[2] and todo[2].name } }
log('DONE; lasts until Classic quits')
return true
