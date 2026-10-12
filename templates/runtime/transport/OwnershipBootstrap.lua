-- Factory only: caller must have a successful verified native performance callback.
return function(config,env,makeController,prior,record)
 assert(config.authorized==true)
 if prior and prior.kind=='startup-release-gate' and prior.controller then prior=prior.controller end
 if prior then
  if prior.active then record('ALREADY_ACTIVE');return prior end
  if prior.waiting or prior.handle then record('WAIT prior actual gate retained');return prior end
  if prior.current then
   local drained,err=prior.drain(prior.current.root)
   if drained~=true then record('STOP prior epoch not independently drained: '..tostring(err));return prior end
  end
 end
 local state={active=false,waiting=true,current=prior and prior.current or nil,drain=prior and prior.drain or nil,kind='startup-release-gate'}
 local h=env.gate(state.current,function(ok,err)
  state.waiting=false;state.handle=nil
  if err or not ok then record('WAIT prior native ownership release: '..tostring(err));return end
  local created,controller=pcall(makeController,config,env)
  if not created then record('STOP controller creation '..tostring(controller));return end
  state.controller=controller;record('CONTROLLER_CREATED')
 end)
 if state.waiting then state.handle=h end
 return state
end
