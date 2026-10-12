-- Authored adapter for the separately verified folder-resolver remedy.
-- Not loaded by startup. The registration entry point is deliberately disabled
-- until a caller supplies current native-owner and independent preservation proof.
local M={}
local function within(path,root)
 assert(type(root)=='string' and root:sub(1,1)=='/' and root:sub(-1)~='/','Expected exact absolute root without trailing slash')
 assert(type(path)=='string' and path:sub(1,#root+1)==root..'/','Resolved path outside current root')
 for segment in path:gmatch('[^/]+')do assert(segment~='.' and segment~='..','Noncanonical resolved path')end
 return path
end
function M.plan(request,expectedCatalog,expectedRoot)
 local sp=assert(request:serverProperty('storeProvider'))
 assert(sp._mainDbPath==expectedCatalog,'Wrong native catalog owner')
 local archive=import 'AgTableArchiving'
 local dest=require 'LrWFSyncStatusDestPathQueries'
 local folders,last,count={},0,0
 sp:doInReadOnlySession(function(session)
  local custom=dest.getSyncDownloadsRoot(session)
  assert(custom==expectedRoot,'Current Sync download root changed')
  local ended=false
  for chunk=1,100 do
   local rows=session:sqlQuery("SELECT id_local,payload FROM AgPendingOzDocs WHERE id_local>? AND state='needs_binary' ORDER BY id_local LIMIT 1000",last)
   if #rows==0 then ended=true;break end
   for _,row in ipairs(rows)do
    last=row.id_local;count=count+1
    local payload=assert(archive.unarchiveNameAndStringToTable('payload',row.payload))
    -- Use the installed complete resolver. Do not derive dates or rewrite queues.
    local path=assert(dest.getDestPathFromAssetPayload(session,payload,true))
    within(path,expectedRoot)
    local folder=assert(path:match('^(.*)/[^/]+$'))
    folders[folder]=true
   end
  end
  assert(ended,'Finite pending-row cap exceeded: retain evidence, do not replay')
 end)
 local paths={};for path in pairs(folders)do paths[#paths+1]=path end;table.sort(paths)
 return {catalog=expectedCatalog,root=expectedRoot,paths=paths,pendingRows=count,writerExecuted=false}
end
function M.register(request,plan,acceptance)
 -- This starter does not manufacture independent full file/image/settings proof.
 assert(acceptance and acceptance.authorized==true and acceptance.independentBeforeSnapshotAccepted==true,
        'Folder registration disabled: fresh reviewed current plan and independent full preservation snapshot required')
 assert(type(acceptance.verifyFullAfter)=='function','Independent after-verifier callback required')
 assert(plan.writerExecuted==false,'This plan was already dispatched or held: inspect actual completed transactions; never replay')
 local sp=assert(request:serverProperty('storeProvider'))
 assert(sp._mainDbPath==plan.catalog and not sp.readServer and sp.db:getAutoCommit(),'Exact native writer required')
 local service=import 'AgLibraryFileService';local files=import 'AgFileUtils'
 local dest=require 'LrWFSyncStatusDestPathQueries'
 assert(#plan.paths<=4000,'Finite folder cap exceeded')
 for _,path in ipairs(plan.paths)do within(path,plan.root)end
 -- Preserve this plan's genuine attempted state even if a later transaction or
 -- independent verifier fails. A durable, separately owned coordinator must
 -- journal committed batches before any recovery of unfinished scopes.
 plan.writerExecuted=true
 for first=1,#plan.paths,100 do
  sp:doInSessionWithTransaction('Register reviewed Sync destination folders',function(session)
   assert(dest.getSyncDownloadsRoot(session)==plan.root,'Current Sync root changed')
   for i=first,math.min(first+99,#plan.paths)do
    local path=plan.paths[i]
    within(path,plan.root)
    assert(files.ensureDirectoryExists(path),'Native directory creation failed')
    local folder=assert(service.findOrCreateFolder(session,path));assert(folder.id)
    local row=assert(session:sqlQuery('SELECT rt.absolutePath,fo.pathFromRoot FROM AgLibraryFolder fo JOIN AgLibraryRootFolder rt ON rt.id_local=fo.rootFolder WHERE fo.id_local=?',folder.id)[1])
    assert((row.absolutePath..row.pathFromRoot):gsub('/+$','')==path,'Registered folder path mismatch')
   end
  end)
 end
 assert(acceptance.verifyFullAfter(plan)==true,'Completed registration held: external verification only, never repeat registration')
 return true
end
return M
