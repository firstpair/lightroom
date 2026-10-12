-- Research cache. Native getter remains authoritative on ambiguity/gaps.
return function(db,native)
 local cache={state=nil,fullReads=0,deltaReads=0,fallbacks=0}
 local function clone(map)local out={};for k,v in pairs(map)do out[k]=v end;return out end
 local function generation()
  return db:firstRow('SELECT revision,(SELECT data_version FROM pragma_data_version) AS version,(SELECT schema_version FROM pragma_schema_version) AS schema FROM temp.local_repair_map_revision WHERE singleton=1')
 end
 local function same(a,b)return a.revision==b.revision and a.version==b.version and a.schema==b.schema end
 local function full(session,group,reason)
  cache.lastPatch=nil;cache.fullReads=cache.fullReads+1;cache.lastReason=reason
  local before=generation();local map=native(session,group);local own,byImage={},{}
  for asset,image in pairs(map)do
   assert(type(asset)=='string' and type(image)=='number' and image>0 and image==math.floor(image))
   if byImage[image] and byImage[image]~=asset then
    cache.state=nil;cache.lastReason='multiple assets for one image';return map
   end
   own[asset]=image;byImage[image]=asset
  end
  local after=generation()
  if not db:getAutoCommit() or not same(before,after)then cache.state=nil;return map end
  cache.state={group=group,gen=after,map=own,byImage=byImage}
  return clone(own)
 end
 function cache:get(session,group)
  self.lastPatch=nil
  if not db:getAutoCommit()then cache.state=nil;return native(session,group)end
  local before=generation();local old=self.state;local patch={put={},remove={}}
  if not old or old.group~=group or old.gen.version~=before.version or old.gen.schema~=before.schema or old.gen.revision>before.revision then
   return full(session,group,'initial or generation reset')
  end
  if old.gen.revision<before.revision then
   local distance=before.revision-old.gen.revision
   if distance>1000 then self.fallbacks=self.fallbacks+1;return full(session,group,'revision bound')end
   local coverage=db:firstRow('SELECT COUNT(DISTINCT revision) AS n FROM temp.local_repair_map_journal WHERE revision>? AND revision<=?',old.gen.revision,before.revision).n
   if coverage~=distance then self.fallbacks=self.fallbacks+1;return full(session,group,'journal gap')end
   local ids=db:gatherArray('SELECT DISTINCT image FROM temp.local_repair_map_journal WHERE revision>? AND revision<=? LIMIT 1001',old.gen.revision,before.revision)
   if #ids>1000 then self.fallbacks=self.fallbacks+1;return full(session,group,'ID bound')end
   local affected={}
   for _,id in ipairs(ids)do
    assert(type(id)=='number' and id>0 and id==math.floor(id))
    if old.byImage[id]then affected[old.byImage[id]]=true end
    local assets=db:gatherArray('SELECT ozAssetId FROM AgLibraryImageOzAssetIds WHERE image=? AND ozCatalogId=? AND ozAssetId!="pending"',id,group)
    if #assets>1 then self.fallbacks=self.fallbacks+1;return full(session,group,'ambiguous image rows')end
    if assets[1]then assert(type(assets[1])=='string');affected[assets[1]]=true end
   end
   local replacement={}
   for asset in pairs(affected)do
    local rows=db:gatherArray('SELECT image FROM AgLibraryImageOzAssetIds WHERE ozAssetId=? AND ozCatalogId=? AND ozAssetId!="pending"',asset,group)
    if #rows>1 then self.fallbacks=self.fallbacks+1;return full(session,group,'ambiguous asset rows')end
    if rows[1]then
     local id=rows[1];assert(type(id)=='number' and id>0 and id==math.floor(id))
     local previous=old.byImage[id]
     if previous and previous~=asset and not affected[previous]then
      self.fallbacks=self.fallbacks+1;return full(session,group,'image ownership conflict')
     end
     replacement[asset]=id
    end
   end
   for asset in pairs(affected)do if replacement[asset] then patch.put[asset]=replacement[asset] else patch.remove[asset]=true end end
   -- Remove all affected ownership before applying swaps. Outputs are copies.
   for asset in pairs(affected)do local id=old.map[asset];if id then old.byImage[id]=nil end;old.map[asset]=nil end
   for asset,id in pairs(replacement)do old.map[asset]=id;old.byImage[id]=asset end
   self.deltaReads=self.deltaReads+1
  end
  local after=generation()
  if not db:getAutoCommit() or not same(before,after)then self.state=nil;return full(session,group,'unstable generation')end
  local output=clone(old.map)
  self.lastPatch={group=group,from=old.gen,to=after,put=patch.put,remove=patch.remove,output=output}
  old.gen=after
  return output
 end
 return cache
end
