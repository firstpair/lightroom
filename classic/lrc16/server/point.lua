local request = ...
local logRoot = __LOGROOT__
local now = import 'AgDate'.timeIntervalSinceReferenceDate
local function write(s) local f = io.open(logRoot .. '/native.txt', 'a'); if f then f:write(string.format('%.3f ', now()) .. s .. '\n'); f:close() end end
local sp = request:serverProperty('storeProvider')
assert(sp._mainDbPath == __CATALOG__ and sp.db.path == sp._mainDbPath, 'not Main')
local prior = _G.lrc16PointLookup
local queries0 = import 'AgWFSyncTrackImagesQueries'
if prior and prior.active then
 write('SUPERSEDING prior calls=' .. prior.calls .. ' compared=' .. prior.compared .. ' mismatches=' .. prior.mismatches)
 assert(prior.mismatches == 0, 'prior had mismatches; not superseding')
 prior.restore('superseded by 16b')
 assert(not prior.active, 'prior did not restore')
end
local queries = import 'AgWFSyncTrackImagesQueries'
local current = require 'LrWFSyncStatusCurrentOzCatalogIdQueries'
local original = queries.isImageIdTracked
assert(type(original) == 'function', 'isImageIdTracked missing')
assert(type(current.maybeGetCurrentOzCatalogIdForSession) == 'function', 'maybeGetCurrentOzCatalogIdForSession missing')
local sql = "SELECT ozAssetId FROM AgLibraryImageOzAssetIds JOIN Adobe_images ON AgLibraryImageOzAssetIds.image=Adobe_images.id_local WHERE AgLibraryImageOzAssetIds.image=? AND ozCatalogId=? AND UPPER(fileFormat)!='VIDEO' AND UPPER(fileFormat)!='UNSET'"
local state = { active = true, started = now(), deadline = now() + 21600, calls = 0, compared = 0, mismatches = 0, fallbacks = 0, pointSeconds = 0, oracleSeconds = 0 }
local wrapper
local function status(label)
 return string.format('%s calls=%d compared=%d mismatches=%d fallbacks=%d pointSeconds=%.3f oracleSeconds=%.3f', label, state.calls, state.compared, state.mismatches, state.fallbacks, state.pointSeconds, state.oracleSeconds)
end
local function restore(reason)
 if not state.active then return end
 if rawget(queries, 'isImageIdTracked') == wrapper then rawset(queries, 'isImageIdTracked', original) else write('NOT_RESTORED ownership changed') end
 state.active = false; pcall(write, status('RESTORED reason=' .. reason))
end
state.restore = restore
wrapper = function(session, imageId, ...)
 if not state.active or now() > state.deadline or state.calls >= 2000000 then restore('bound reached'); return original(session, imageId, ...) end
 if select('#', ...) > 0 or type(session) ~= 'table' or session.storeProvider ~= sp or type(imageId) ~= 'number' then
  state.fallbacks = state.fallbacks + 1; return original(session, imageId, ...)
 end
 state.calls = state.calls + 1
 local t0 = now()
 local ok, value = pcall(function()
  local oz = current.maybeGetCurrentOzCatalogIdForSession(session)
  if oz == nil then return nil end
  return sp.db:firstRow(sql, imageId, oz).ozAssetId
 end)
 state.pointSeconds = state.pointSeconds + now() - t0
 if not ok then state.fallbacks = state.fallbacks + 1; write('CANDIDATE_ERROR ' .. tostring(value)); restore('candidate error'); return original(session, imageId) end
 if state.calls <= 10 or state.calls % 5000 == 0 then
  t0 = now(); local expected = original(session, imageId); state.oracleSeconds = state.oracleSeconds + now() - t0
  state.compared = state.compared + 1
  if expected ~= value then state.mismatches = state.mismatches + 1; write('MISMATCH image=' .. imageId .. ' expected=' .. tostring(expected) .. ' got=' .. tostring(value)); restore('oracle mismatch'); return expected end
 end
 if state.calls % 5000 == 0 then pcall(write, status('PROGRESS')) end
 return value
end
rawset(queries, 'isImageIdTracked', wrapper)
_G.lrc16PointLookup = state
write(status('INSTALLED bound=6h/2M calls, oracle first10+every5000, reads only'))
return true
