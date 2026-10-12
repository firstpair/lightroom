-- Research factory; TEMP journal must already exist on the supplied connection.
local FULL=[[SELECT image, ozAssetId FROM AgLibraryImageOzAssetIds, Adobe_images WHERE AgLibraryImageOzAssetIds.image = Adobe_images.id_local AND ozCatalogId = ? AND UPPER( fileFormat ) != "VIDEO" AND UPPER( fileFormat ) != "UNSET"]]
return function(db,nativeGatherMap)
 nativeGatherMap=nativeGatherMap or db.gatherMap
 local cache={fullReads=0,deltaReads=0,bypasses=0,gapFallbacks=0,state=nil}
 local function clone(map)
  assert(type(map)=='table' and getmetatable(map)==nil)
  local out={}
  for k,v in pairs(map) do assert(type(k)=='number' and type(v)=='string');out[k]=v end
  return out
 end
 local function generation()
  return db:firstRow([[SELECT revision,(SELECT data_version FROM pragma_data_version) AS version,(SELECT schema_version FROM pragma_schema_version) AS schema FROM temp.local_repair_map_revision WHERE singleton=1]])
 end
 local function same(a,b) return a.revision==b.revision and a.version==b.version and a.schema==b.schema end
 local function full(group)
  cache.fullReads=cache.fullReads+1
  local map=nativeGatherMap(db,FULL,group);local count=0;local nullable={}
  for k,v in pairs(map) do assert(type(k)=='number' and type(v)=='string');count=count+1 end
  local nullSQL=FULL:gsub('SELECT image, ozAssetId','SELECT image')..' AND ozAssetId IS NULL'
  for _,id in ipairs(db:gatherArray(nullSQL,group)) do nullable[id]=true;count=count+1 end
  return map,count,nullable
 end
 function cache:refresh(group)
  assert(type(group)=='number' or type(group)=='string')
  if not db:getAutoCommit() then cache.state=nil;cache.bypasses=cache.bypasses+1;return full(group) end
  local before=generation();assert(type(before.revision)=='number' and type(before.version)=='number' and type(before.schema)=='number')
  local old=cache.state;local map,count,nullable
  if not old or old.group~=group or old.gen.version~=before.version or old.gen.schema~=before.schema or old.gen.revision>before.revision then
   map,count,nullable=full(group)
  else
   map=old.map;count=old.count;nullable=old.nullable
   if old.gen.revision<before.revision then
    local distance=before.revision-old.gen.revision
    local coverage=db:firstRow('SELECT COUNT(DISTINCT revision) AS n FROM temp.local_repair_map_journal WHERE revision>? AND revision<=?',old.gen.revision,before.revision).n
    if coverage~=distance or distance>1000 then
     cache.gapFallbacks=cache.gapFallbacks+1;map,count,nullable=full(group)
    else
     local ids=db:gatherArray('SELECT DISTINCT image FROM temp.local_repair_map_journal WHERE revision>? AND revision<=? LIMIT 1001',old.gen.revision,before.revision)
     if #ids>1000 then cache.gapFallbacks=cache.gapFallbacks+1;map,count,nullable=full(group)
     else
      cache.deltaReads=cache.deltaReads+1
      for _,id in ipairs(ids) do
       local row=db:firstRow(FULL..' AND image=?',group,id)
       assert(row.ozAssetId==nil or type(row.ozAssetId)=='string')
       local was=map[id]~=nil or nullable[id]==true
       local present=row.image~=nil
       count=count+(present and 1 or 0)-(was and 1 or 0)
       map[id]=row.ozAssetId
       nullable[id]=(present and row.ozAssetId==nil) and true or nil
      end
     end
    end
   end
  end
  local after=generation()
  if not db:getAutoCommit() or not same(before,after) then cache.state=nil;return full(group) end
  cache.state={group=group,gen=after,map=map,count=count,nullable=nullable}
  return map,count
 end
 function cache:get(group) local map=self:refresh(group);return clone(map) end
 function cache:getCount(group) local _,count=self:refresh(group);return {count} end
 return cache
end
