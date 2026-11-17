-- Run Classic's own "clear errors and retry sync" (SourceSyncManager catalog model 'clearErrorsAndRetrySync')
-- on the listed cloud asset IDs. Native code makes all changes (new revision, cleared error annotation); this script
-- only constructs the model, logs values and the terminal callback, then disposes its subscription and closes its
-- model. Runs once per Classic process.
local key = __KEY__
local BASE = __RUNROOT__
local now = (import 'AgDate').timeIntervalSinceReferenceDate
local run = BASE .. '/runs/run-' .. string.format('%.3f', now())
import 'LrFileUtils'.createAllDirectories(run)
local function log(s) local f = io.open(run .. '/log.txt', 'a'); if f then f:write(string.format('%.3f ', now()) .. s .. '\n'); f:close() end end
local function ser(v, d)
  d = d or 0
  if type(v) ~= 'table' then return tostring(v) end
  if d > 3 then return '{...}' end
  local o = {}
  for k, x in pairs(v) do o[#o + 1] = tostring(k) .. '=' .. ser(x, d + 1) end
  table.sort(o); return '{' .. table.concat(o, ',') .. '}'
end
log('ENTRY')
if _G[key] then log('ALREADY_RAN_THIS_PROCESS; not repeating'); return end
local active = (import 'AgLibrary').getActiveCatalogPathIfAvailable()
if active ~= __CATALOG__ then log('WRONG_CATALOG ' .. tostring(active)); return end
local asset = import 'LrSourceAssetSynchronizer'
local cid = (import 'LrSourceSynchronizerUtils').getOzCatalogId(asset._dataServer)
if cid ~= __CLOUD_CATALOG__ then log('WRONG_CLOUD_CATALOG ' .. tostring(cid)); return end
local root = (import 'SourceSyncManager').getCatalogModel()
if not root then log('NO_CATALOG_MODEL'); return end
local ids = { __IDS__ }
local state = { values = 0 }
_G[key] = state
local function finish(label)
  if state.finished then return end
  state.finished = true
  if state.sub and state.sub ~= true then local ok, e = pcall(function() state.sub:dispose() end); log('DISPOSE ' .. tostring(ok) .. ' ' .. tostring(e)) end
  local ok, e = pcall(function() state.model:close() end); log('CLOSE ' .. tostring(ok) .. ' ' .. tostring(e))
  log('DONE ' .. label)
end
log('CONSTRUCT clearErrorsAndRetrySync ' .. #ids)
local made, m = pcall(function() return root:subModel('clearErrorsAndRetrySync', ids) end)
if not made then log('ERROR construct ' .. tostring(m)); return end
state.model = m
state.sub = true -- marker until subscribe returns
local ok, h = pcall(function()
  return m:value():subscribe(
    function(value) state.values = state.values + 1; if state.values <= 8 then log('VALUE ' .. state.values .. ' ' .. ser(value)) end end,
    function(err) log('ERROR native ' .. ser(err)); state.terminal = 'error'; if state.sub ~= true then finish('error') end end,
    function() log('COMPLETED values=' .. state.values); state.terminal = 'completed'; if state.sub ~= true then finish('completed') end end)
end)
if not ok then log('ERROR subscribe ' .. tostring(h)); state.sub = nil; return end
state.sub = h
if state.terminal then finish(state.terminal) else log('SUBSCRIBED; waiting for native terminal') end
