-- Re-register each photo's EXISTING local Smart Preview with Lightroom's own setOriginalAndProxyInfo (proxy-only:
-- filePath/fileSize omitted, so the original's record is untouched). Native code hashes the file and records its
-- current volume/path; bytes are not changed. Fixes pending proxy uploads whose record points to a volume that is gone.
local key = __KEY__
local BASE = __RUNROOT__
local now = (import 'AgDate').timeIntervalSinceReferenceDate
local run = BASE .. '/runs/run-' .. string.format('%.3f', now())
local fu = import 'LrFileUtils'
fu.createAllDirectories(run)
local function log(s) local f = io.open(run .. '/log.txt', 'a'); if f then f:write(string.format('%.3f ', now()) .. s .. '\n'); f:close() end end
local function ser(v, d) d = d or 0; if type(v) ~= 'table' then return tostring(v) end; if d > 3 then return '{...}' end
  local o = {}; for k, x in pairs(v) do o[#o + 1] = tostring(k) .. '=' .. ser(x, d + 1) end; table.sort(o); return '{' .. table.concat(o, ',') .. '}' end
log('ENTRY')
if _G[key] then log('ALREADY_RAN_THIS_PROCESS; not repeating'); return end
local active = (import 'AgLibrary').getActiveCatalogPathIfAvailable()
if active ~= __CATALOG__ then log('WRONG_CATALOG ' .. tostring(active)); return end
local asset = import 'LrSourceAssetSynchronizer'
local cid = (import 'LrSourceSynchronizerUtils').getOzCatalogId(asset._dataServer)
if cid ~= __CLOUD_CATALOG__ then log('WRONG_CLOUD_CATALOG ' .. tostring(cid)); return end
local root = (import 'SourceSyncManager').getCatalogModel()
if not root then log('NO_CATALOG_MODEL'); return end
local items = {
__ITEMS__
}
for _, it in ipairs(items) do
  if not fu.exists(it.path) or fu.fileAttributes(it.path).fileSize ~= it.size then log('SOURCE_CHANGED ' .. it.id); return end
end
local state = { pending = #items, items = {} }
_G[key] = state
local function finishOne(it, label)
  local s = state.items[it.id]; if s.finished then return end; s.finished = true
  if s.sub and s.sub ~= true then pcall(function() s.sub:dispose() end) end
  local ok, e = pcall(function() s.model:close() end)
  log('DONE_ONE ' .. it.id .. ' ' .. label .. ' close=' .. tostring(ok) .. ' ' .. tostring(e))
  state.pending = state.pending - 1
  if state.pending == 0 then log('DONE all') end
end
for _, it in ipairs(items) do
  local s = { values = 0 }; state.items[it.id] = s
  log('CONSTRUCT ' .. it.id .. ' ' .. it.path .. ' ' .. it.size)
  local made, m = pcall(function() return root:subModel('setOriginalAndProxyInfo', it.id, { proxyFilePath = it.path, proxyFileSize = it.size }) end)
  if not made then log('ERROR construct ' .. it.id .. ' ' .. tostring(m)); state.pending = state.pending - 1
  else
    s.model = m; s.sub = true
    local ok, h = pcall(function()
      return m:value():subscribe(
        function(v) s.values = s.values + 1; if s.values <= 3 then log('VALUE ' .. it.id .. ' ' .. ser(v)) end end,
        function(err) log('ERROR native ' .. it.id .. ' ' .. ser(err)); s.terminal = 'error'; if s.sub ~= true then finishOne(it, 'error') end end,
        function() s.terminal = 'completed'; if s.sub ~= true then finishOne(it, 'completed') end end)
    end)
    if not ok then log('ERROR subscribe ' .. it.id .. ' ' .. tostring(h)); s.sub = nil; state.pending = state.pending - 1
    else s.sub = h; if s.terminal then finishOne(it, s.terminal) end end
  end
end
if state.pending == 0 then log('DONE all') end
log('SUBMITTED')
