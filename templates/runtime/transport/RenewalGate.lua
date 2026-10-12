return function(globals)
 local function current()
  local s=globals.automaticMapTransport178 or globals.mapTransportController173
  if s and s.kind=='startup-release-gate' and s.controller then return s.controller end
  return s
 end
 local api={}
 function api.stopFutureCycles()
  local s=current()
  if s and s.active then assert(type(s.stop)=='function');s.stop('renewal boundary: current native transport drains normally') end
 end
 function api.ready()
  local s=current()
  if s and (s.active or s.waiting or s.handle) then return false end
  local job=s and s.current
  if job then
   if type(s.drain)~='function' then return false end
   local done=s.drain(job.root);if done~=true then return false end
   for _,name in ipairs(job.clientGlobals)do if globals[name] then return false end end
  end
  local names={}
  if job then for _,name in ipairs(job.nativeGlobals)do assert(name:match('^[%a_][%w_]*$'));names[#names+1]=string.format('%q',name)end end
  local prefix=[[local transportReleaseRequest=...;local transportReleaseStore=transportReleaseRequest:serverProperty('storeProvider');assert(transportReleaseStore._mainDbPath=='@@CATALOG@@' and not transportReleaseStore.readServer)
if not transportReleaseStore.db:getAutoCommit()then return 'WAIT_TRANSPORT_RELEASE' end
for _,name in ipairs({]]..table.concat(names,',')..[[})do if _G[name] then return 'WAIT_TRANSPORT_RELEASE' end end
]]
  return true,prefix
 end
 return api
end
