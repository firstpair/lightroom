-- Private protocol model. Not installed in Lightroom.
local function validId(k)
 return type(k)=='number' and k>0 and k==math.floor(k) and k<9007199254740992
end
local function copy(map)
 assert(type(map)=='table' and getmetatable(map)==nil,'plain map required')
 local out={}
 for k,v in pairs(map)do
  assert(type(k)=='string' and #k>0 and validId(v),'invalid map entry')
  out[k]=v
 end
 return out
end
local function copyValidated(map)
 local out={}
 for k,v in pairs(map)do out[k]=v end
 return out
end
return function(epoch,nativeCopy)
 local fallback=copyValidated
 assert(nativeCopy==nil or type(nativeCopy)=='function')
 local function copyValidated(map)if not nativeCopy then return fallback(map)end;local out=nativeCopy(map);assert(type(out)=='table' and getmetatable(out)==nil and out~=map,'isolated copy required');return out end
 assert(type(epoch)=='string' and #epoch>0)
 local state={epoch=epoch,sequence=0,map=nil}
 function state:accept(e)
  assert(type(e)=='table' and getmetatable(e)==nil,'plain envelope required')
  assert(e.protocol=='local-reverse-delta-v1' and e.epoch==self.epoch,'protocol or epoch mismatch')
  assert(validId(e.sequence),'invalid sequence')
  local nextMap
  if e.kind=='full' then
   assert(e.sequence>self.sequence,'stale full snapshot')
   nextMap=copy(e.map)
  else
   assert(e.kind=='delta' and self.map and not self.invalid,'valid full snapshot required')
   assert(e.sequence==self.sequence+1 and e.base==self.sequence,'sequence gap')
   assert(type(e.put)=='table' and getmetatable(e.put)==nil,'plain updates required')
   assert(type(e.remove)=='table' and getmetatable(e.remove)==nil,'plain removals required')
   for k,v in pairs(e.put)do assert(type(k)=='string' and #k>0 and validId(v),'invalid update')end
   for k,v in pairs(e.remove)do
    assert(type(k)=='string' and #k>0 and v==true and e.put[k]==nil,'invalid or conflicting removal')
   end
   nextMap=copyValidated(self.map)
   for k in pairs(e.remove)do nextMap[k]=nil end
   for k,v in pairs(e.put)do nextMap[k]=v end
  end
  -- The native receiver gets a separate table; neither its old maps nor its
  -- newly returned map can mutate protocol state or future notifications.
  local nativeMap
  if e.kind=='full'then
   nativeMap=copyValidated(nextMap);self.map=nextMap;self.invalid=false
  else
   -- nextMap is already the isolated native output. Validate and build it
   -- before touching private state. An interrupted private commit forces
   -- full resynchronization; no later delta can use a partial private map.
   nativeMap=nextMap;self.invalid=true
   for k in pairs(e.remove)do self.map[k]=nil end
   for k,v in pairs(e.put)do self.map[k]=v end
   self.invalid=false
  end
  self.sequence=e.sequence
  return nativeMap
 end
 return state
end
