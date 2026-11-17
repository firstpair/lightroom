-- Develop re-save: for each listed photo, nudge exposure by +0.01 and restore the exact original value through the
-- SDK. Classic regenerates and uploads the develop XMP (and re-sends the Smart Preview when its link is missing).
-- Final settings are identical; each photo gains two history steps. Logs before/after settings per photo.
local items = {
__ITEMS__
}
local key = __KEY__
local BASE = __RUNROOT__
local LrTasks = import 'LrTasks'
local now = (import 'AgDate').timeIntervalSinceReferenceDate
local run = BASE .. '/runs/run-' .. string.format('%.3f', now())
import 'LrFileUtils'.createAllDirectories(run)
local function log(s) local f = io.open(run .. '/log.txt', 'a'); if f then f:write(string.format('%.3f ', now()) .. tostring(s) .. '\n'); f:close() end end
local function dump(name, t) local f = io.open(run .. '/' .. name, 'w'); local ks = {}; for k in pairs(t) do ks[#ks+1] = k end; table.sort(ks); for _, k in ipairs(ks) do f:write(k .. '\t' .. tostring(t[k]) .. '\n') end; f:close() end
log('ENTRY')
if _G[key] then log('ALREADY_RAN_THIS_PROCESS'); return end
_G[key] = true
LrTasks.startAsyncTask(function()
  local cat = import 'LrApplication'.activeCatalog()
  if cat:getPath() ~= __CATALOG__ then log('WRONG_CATALOG'); return end
  for i, it in ipairs(items) do
    local ok, err = LrTasks.pcall(function()
      local photo = cat:getPhotoByLocalId(it[1])
      if not photo or photo:getRawMetadata('path') ~= it[2] then log(i .. ' WRONG_PHOTO ' .. it[1]); return end
      local before = photo:getDevelopSettings(); dump('before-' .. it[1] .. '.tsv', before)
      local k = type(before.Exposure2012) == 'number' and 'Exposure2012' or (type(before.Exposure) == 'number' and 'Exposure' or nil)
      if not k then log(i .. ' NO_EXPOSURE ' .. it[1]); return end
      local e = before[k]
      cat:withWriteAccessDo('Sync resave nudge', function() photo:applyDevelopSettings({ [k] = e + 0.01 }) end, { timeout = 60 })
      cat:withWriteAccessDo('Sync resave restore', function() photo:applyDevelopSettings({ [k] = e }) end, { timeout = 60 })
      local after = photo:getDevelopSettings(); dump('after-' .. it[1] .. '.tsv', after)
      local diff = {}
      for kk, v in pairs(before) do if type(v) ~= 'table' and tostring(after[kk]) ~= tostring(v) then diff[#diff+1] = kk end end
      log(i .. ' OK ' .. it[1] .. ' ' .. k .. '=' .. tostring(after[k]) .. ' scalarDiffs=' .. table.concat(diff, ','))
    end)
    if not ok then log(i .. ' ERROR ' .. it[1] .. ' ' .. tostring(err)) end
  end
  log('DONE')
end)
log('TASK_STARTED')
