return function(request,logRoot)
local sp=request:serverProperty('storeProvider');assert(sp._mainDbPath=='@@CATALOG@@' and not sp.readServer);local db=sp.db;assert(db:getAutoCommit(),'do not take existing transaction');
local now=import 'AgDate'.timeIntervalSinceReferenceDate;local loop=import 'AgEventLoop';local original="CREATE TRIGGER trigger_AgLibraryImageChangeCounter_update_for_fileRename\n\tAFTER UPDATE OF folder, idx_filename ON AgLibraryFile\n\tFOR EACH ROW\n\tBEGIN\n\t\tINSERT INTO update_AgLibraryImageChangeCounter_for_image\n\t\t\tSELECT id_local FROM Adobe_images\n\t\t\tWHERE rootFile = NEW.id_local;\n\t\tDELETE FROM AgLibraryImageSyncedAssetData\n\t\t\tWHERE image IN (SELECT id_local FROM Adobe_images\n\t\t\t\tWHERE rootFile = NEW.id_local ) \n\t\t\t\tAND +payloadKey IN ( '/importSource/folder', '/importSource/fileName' );\n\tEND";local corrected="CREATE TRIGGER trigger_AgLibraryImageChangeCounter_update_for_fileRename\n\tAFTER UPDATE OF folder, idx_filename ON AgLibraryFile\n\tFOR EACH ROW\n\tBEGIN\n\t\tINSERT INTO update_AgLibraryImageChangeCounter_for_image\n\t\t\tSELECT id_local FROM Adobe_images\n\t\t\tWHERE rootFile = NEW.id_local;\n\t\tDELETE FROM AgLibraryImageSyncedAssetData\n\t\t\tWHERE image IN (SELECT +id_local FROM Adobe_images\n\t\t\t\tWHERE rootFile = NEW.id_local ) \n\t\t\t\tAND +payloadKey IN ( '/importSource/folder', '/importSource/fileName' );\n\tEND";local name="trigger_AgLibraryImageChangeCounter_update_for_fileRename"
local function log(s)local f=assert(io.open(logRoot..'/phase6.txt','a'));f:write(tostring(now())..' '..s..'\n');f:close()end
local prior=_G.folderRenameAffinity515
if prior then
 local row=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#row==1,'Metadata trigger absent')
 if prior.active then
  assert(row[1].sql==corrected and prior.corrected==corrected and prior.original==original,'Active metadata owner/SQL changed')
  if now()<prior.expires-600 then log('ALREADY_ACTIVE expires='..prior.expires);return true end
  prior.restore();assert(not prior.active,'Original metadata restoration pending')
  row=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#row==1,'Restored metadata trigger absent')
 end
 assert(row[1].sql==original,'Inactive metadata owner not restored');_G.folderRenameAffinity515Previous=prior;_G.folderRenameAffinity515=nil
end
log('ENTER user-authorized live native TEMP correction bound7200seconds')
local globals=db:gatherArrayOfTables("SELECT image,typeof(image) AS image_type FROM (SELECT DISTINCT image FROM AgLibraryImageSyncedAssetData LIMIT -1 OFFSET 0) WHERE typeof(image) NOT IN ('integer','real') OR image != CAST(image AS INTEGER) LIMIT 1");assert(#globals==0,'unsupported global image key; no mutation');log('GLOBAL_NUMERIC_INTEGRAL_KEYS_VERIFIED')
local function selectRows(expr)return db:gatherArrayOfTables("SELECT rowid AS row_id,image,typeof(image) AS image_type,payloadKey FROM AgLibraryImageSyncedAssetData INDEXED BY index_AgLibraryImageSyncedAssetData_primaryKey WHERE +payloadKey IN ('/importSource/folder','/importSource/fileName') AND image IN (SELECT "..expr.." FROM Adobe_images WHERE rootFile IN (SELECT DISTINCT rootFile FROM Adobe_images WHERE rootFile IS NOT NULL ORDER BY rootFile LIMIT 20) ) ORDER BY rowid")end
local metadata=assert(_G.metadataLiveAffinity005,'metadata renewal owner missing');assert(metadata.active and metadata.expires>now()+600,'metadata renewal deadline too near');
sp:doInSessionWithTransaction('Apply bounded native metadata index affinity correction',function(session)
 local triggers=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#triggers==1 and triggers[1].sql==original,'exact native TEMP SQL changed')
 local a=selectRows('id_local');local b=selectRows('+id_local');assert(#a>0 and #a==#b,'selected counts empty or differ');for i,x in ipairs(a)do local y=b[i];assert(x.row_id==y.row_id and x.image==y.image and x.image_type==y.image_type and x.payloadKey==y.payloadKey,'selected rows differ');assert((x.image_type=='integer' or x.image_type=='real') and x.image==math.floor(x.image),'nonintegral image')end;log('SELECTED_ROWS_EQUAL scope20 rows='..#a)
 local plans=db:gatherArrayOfTables("EXPLAIN QUERY PLAN SELECT image FROM AgLibraryImageSyncedAssetData WHERE +payloadKey IN ('/importSource/folder','/importSource/fileName') AND image IN (SELECT +id_local FROM Adobe_images WHERE rootFile=(SELECT MIN(rootFile) FROM Adobe_images WHERE rootFile IS NOT NULL))");local good=false;for _,q in ipairs(plans)do if q.detail:find('index_AgLibraryImageSyncedAssetData_primaryKey',1,true) then good=true end end;assert(good,'indexed plan missing')
 session:_execWithoutMutationCheck('DROP TRIGGER temp.'..name);session:_execWithoutMutationCheck((corrected:gsub('CREATE TRIGGER','CREATE TEMP TRIGGER',1)));local check=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#check==1 and check[1].sql==corrected);log('CORRECTED_TRIGGER_INSTALLED_ONLY_DELETE_RHS_CHANGED')
end)
local state={active=true,expires=math.min(now()+7200,metadata.expires),original=original,corrected=corrected};_G.folderRenameAffinity515=state
local function restore()
 if not state.active then return end
 if not db:getAutoCommit() then loop.afterDelay(1,restore);return end
 local ok,err=pcall(function()sp:doInSessionWithTransaction('Restore native metadata affinity trigger',function(session)local r=db:gatherArrayOfTables("SELECT sql FROM sqlite_temp_master WHERE name='"..name.."'");assert(#r==1 and r[1].sql==corrected,'trigger ownership changed; no overwrite');session:_execWithoutMutationCheck('DROP TRIGGER temp.'..name);session:_execWithoutMutationCheck((original:gsub('CREATE TRIGGER','CREATE TEMP TRIGGER',1)))end)end)
 if ok then state.active=false;log('ORIGINAL_TRIGGER_RESTORED')else log('RESTORATION_ERROR '..tostring(err))end
end
state.restore=restore;loop.afterDelay(state.expires-now(),restore);log('LIVE_INSTALLED deadline='..state.expires..' native counters and all deletion statements retained');return true
end
