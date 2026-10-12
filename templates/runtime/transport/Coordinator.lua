-- Prepared controller; loading returns a factory and does not enable anything.
return function(config, env)
 assert(type(config)=='table' and type(env)=='table')
 assert(config.authorized==true and config.catalog=='@@CATALOG@@')
 local state={active=true,checks=0,runs=0,waiting=false,current=nil}
 local function note(s)env.note(s)end
 local function stop(reason)state.active=false;note('STOP '..reason)end
 local function read(path)return env.read(path)end
 local function replaceLiteral(text,from,to)
  local pattern=from:gsub('([^%w])','%%%1')
  return (text:gsub(pattern,function()return to end))
 end
 local function drain(root)
  for _,direction in ipairs({'forward','reverse'})do
   local base=root..'/'..direction..'/'
   local ui=read(base..'UI.txt')or'';local server=read(base..'SERVER.txt')or'';local dispatch=read(base..'DISPATCH.txt')or''
   if ui:find('DECODE_FAILURE',1,true) or server:find('equal=false',1,true) or dispatch:find('actual server error',1,true) then return nil,'native error retained' end
   local final=read(base..'SENDER-FINAL.txt')
   if not final then return false end
   local count=tonumber(final:match('^(%d+)\n$'));if not count or count<0 then return nil,'invalid final receipt' end
   if tonumber(ui:match('RESTORED sender restored and all envelopes drained received=(%d+)'))~=count then return false end
   if count==0 then
    if not server:find('RESTORED [^\n]* sent=0\n') then return false end
    if not server:find('RECOVERY_STATE_RELEASED calls=0 noEnvelopes=true ownedMethodsReleased=true\n',1,true) then return false end
    for _,marker in ipairs({'SEND_INTENT','SEND_RETURN','RECOVERY_FULL_SENT','JOURNAL_DELTA'}) do if server:find(marker,1,true) then return nil,'zero final contradicts sender events' end end
    for _,marker in ipairs({'DECODED','NATIVE_CALLBACK_RETURN','recovery callback','actual recovery error'}) do if ui:find(marker,1,true) then return nil,'zero final contradicts receiver events' end end
    -- Bound matches existing max1000 normal envelopes plus one recovery envelope.
    for i=0,1001 do if read(base..'ACK'..i..'.txt')~=nil then return nil,'zero final has acknowledgement artifact' end end
   else
    if tonumber(server:match('RECOVERY_STATE_RELEASED ack=(%d+)'))~=count then return false end
    for i=1,count do if read(base..'ACK'..i..'.txt')~=tostring(i)..'\n' then return nil,'incomplete acknowledgement coverage' end end
   end
  end
  return true
 end
 local function prepare()
  for path,sha in pairs(config.pins)do assert(env.digest(path)==sha,'sealed dependency changed: '..path)end
  state.runs=state.runs+1
  local tag=string.format('%.6f',env.now()):gsub('%.','')..'r'..state.runs
  local root=config.output..'/run-'..tag
  assert(not env.exists(root),'execution root collision')
  env.mkdir(root)
  local clientGlobals,nativeGlobals={},{}
  for _,direction in ipairs({'forward','reverse'})do
   local src=config.templates..'/'..direction..'/'
   local dst=root..'/'..direction..'/'
   env.mkdir(dst)
   local oldTag='1331010'..direction;local newTag='135'..tag..direction
   local oldEpoch='combined-nativecopy-20261010-133-'..direction;local newEpoch='auto-nativecopy-'..tag..'-'..direction
   for _,name in ipairs({'UI.lua','SERVER-TEMPLATE.lua'})do
    local text=assert(read(src..name),'template missing')
    text=replaceLiteral(text,src,dst);text=replaceLiteral(text,oldTag,newTag);text=replaceLiteral(text,oldEpoch,newEpoch)
    assert(env.compile(text),'generated Lua compile failure');env.write(dst..name,text)
   end
   if direction=='reverse' then env.write(dst..'ReverseDeltaMap-v4.lua',assert(read(src..'ReverseDeltaMap-v4.lua')))end
   clientGlobals[#clientGlobals+1]=(direction=='forward' and 'localRepairJournalReceiver' or 'localRepairReverseJournalReceiver')..newTag
   nativeGlobals[#nativeGlobals+1]=(direction=='forward' and 'localRepairJournalDelta' or 'localRepairReverseJournalDelta')..newTag
  end
  env.write(root..'/PREPARED.txt','hash-bound templates; unique epoch '..tag..'; max1000/2400sec per direction\n')
  return {root=root,clientGlobals=clientGlobals,nativeGlobals=nativeGlobals}
 end
 local tick
 tick=function()
  if not state.active then return end
  state.checks=state.checks+1
  if env.catalog()~=config.catalog then stop('wrong catalog');return end
  if state.waiting then note('WAIT actual gate handle retained');env.after(config.interval,tick);return end
  if state.current then
   local done,err=drain(state.current.root)
   if done==nil then stop(err);return end
   if not done then note('WAIT sender/receiver/ACK drain');env.after(config.interval,tick);return end
   note('DRAINED '..state.current.root)
  end
  if state.runs>=config.maxRuns then stop('controller run bound');return end
  state.waiting=true
  -- env.gate must check exact native owner/guards, no remaining runtime globals,
  -- and both current UI receiver globals before calling result(true).
  state.handle=env.gate(state.current,function(ok,errorText)
   state.waiting=false;state.handle=nil
   if errorText then stop('actual gate error '..errorText);return end
   if not state.active then return end
   if not ok then note('WAIT native ownership/guard readiness');env.after(config.interval,tick);return end
   local preparedOk,job=pcall(prepare)
   if not preparedOk then stop('preparation '..tostring(job));return end
   state.current=job
   -- Dispatch each side once, preserving any installed side on another failure.
   local dispatchOk,dispatchError=pcall(function()
    env.dispatch(job.root..'/forward/UI.lua')
    env.dispatch(job.root..'/reverse/UI.lua')
   end)
   if not dispatchOk then stop('partial dispatch '..tostring(dispatchError));return end
   note('DISPATCHED '..job.root)
   env.after(config.interval,tick)
  end)
 end
 state.tick=tick;state.stop=stop;state.drain=drain
 env.after(config.interval,tick)
 return state
end
