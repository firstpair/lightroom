-- Native Main owner; installs a bounded no-op guard, never rewrites date rows.
return function(request, logRoot)
 local sp=request:serverProperty('storeProvider')
 assert(sp._mainDbPath=='@@CATALOG@@' and not sp.readServer)
 local crypto=require 'WFCrypto'
 local root='@@ROOT@@/runtime/date'
 assert(string.lower(crypto.digestFile('@@APP@@/Contents/Frameworks/LibraryToolkit.agtoolkit/Contents/Resources/AgLibraryDates.lua','SHA256'))=='4387ea4954494d987c17d25583463b4e856d6a051097a25a1425a905046a6e96')
 assert(string.lower(crypto.digestFile(root..'/Predicate.lua','SHA256'))=='e139d881462a701d62b757b8bd60d01e1052fc47099f18559899844fe9aecf49')
 local predicate=assert(loadfile(root..'/Predicate.lua'))()
 local dates=import 'AgLibraryDates';local parser=(import 'AgMetadata').XMPDateToTimeStamp
 local now=(import 'AgDate').timeIntervalSinceReferenceDate;local loop=import 'AgEventLoop'
 local function note(s)local f=assert(io.open(logRoot..'/capture-date-guard.txt','a'));f:write(string.format('%.6f ',now())..s..'\n');f:close()end
 local current=_G.captureDateEquivalenceGuard241
 local original=dates.setCaptureDate
 if current and current.active then assert(dates.setCaptureDate==current.wrapper,'guard ownership changed');original=current.original end
 assert(type(original)=='function' and type(parser)=='function')
 -- Detached native controls prove initialization and genuine changes retain native behavior.
 local base='2012-04-08T10:42:59';local timestamp=assert(parser(base))
 local function image()return {captureTime=base,originalCaptureTime=base,extendedMetadata={dateTimeOriginal=base,dateCreated=base,dateTime=base}}end
 local same=image();assert(predicate(same,timestamp,parser));original(same,timestamp);assert(same.captureTime~=base and parser(same.captureTime)==timestamp)
 local changed=image();assert(not predicate(changed,timestamp+1,parser));original(changed,timestamp+1);assert(parser(changed.captureTime)==timestamp+1)
 local missingOriginal=image();missingOriginal.originalCaptureTime=nil;assert(not predicate(missingOriginal,timestamp,parser));original(missingOriginal,timestamp);assert(missingOriginal.originalCaptureTime==base)
 local missingDateTime=image();missingDateTime.extendedMetadata.dateTime=nil;assert(not predicate(missingDateTime,timestamp,parser));original(missingDateTime,timestamp);assert(missingDateTime.extendedMetadata.dateTime)
 local fractional=image();fractional.captureTime=base..'.001';assert(not predicate(fractional,timestamp,parser))
 for _,zone in ipairs({'-08:00','+05:30','+14:00','-00:00'})do
 local v=image();v.extendedMetadata.dateTimeOriginal=base..zone;v.extendedMetadata.dateCreated=base..zone;assert(predicate(v,timestamp,parser));original(v,timestamp);assert(v.extendedMetadata.dateTimeOriginal==base..'.000'..zone and v.extendedMetadata.dateCreated==base..'.000'..zone);assert(parser(v.captureTime)==timestamp)
 local mismatch=image();mismatch.extendedMetadata.dateTimeOriginal=base..zone;assert(not predicate(mismatch,timestamp,parser))
 local zulu=image();zulu.extendedMetadata.dateTimeOriginal=base..'Z';zulu.extendedMetadata.dateCreated=base..'Z';assert(not predicate(zulu,timestamp,parser))
end
 note('DETACHED_NATIVE_CONTROLS passed including stable offsets; Z native fallback; no catalog entities touched')
 if current and current.active then
  if current.revision=='date-v2-offset' then current.expires=now()+7200;note('RENEWED owned offset guard');return true end
  assert(current.revision=='date-v1');current.restore('validated offset successor');assert(dates.setCaptureDate==original,'restoration ownership changed')
 end
 local priorRaw=rawget(dates,'setCaptureDate')
 local state={active=true,original=original,calls=0,skips=0,expires=now()+7200,revision='date-v2-offset'}
 function state.restore(reason)
  if not state.active then return end
  state.active=false
  if rawget(dates,'setCaptureDate')==state.wrapper then rawset(dates,'setCaptureDate',priorRaw);note('RESTORED '..reason)else note('FOREIGN_OWNER_RETAINED '..reason)end
 end
 state.wrapper=function(image,stamp,...)
  if not state.active then return original(image,stamp,...)end
  if now()>=state.expires then state.restore('deadline');return original(image,stamp,...)end
  state.calls=state.calls+1
  local ok,equivalent=pcall(predicate,image,stamp,parser)
  if not ok then state.restore('predicate error fallback');return original(image,stamp,...)end
  if equivalent then
   state.skips=state.skips+1
   if state.skips<=32 then pcall(note,'SKIP unchanged whole-second timestamp; no date assignments')end
   return -- native setter returns no values; no capture/XMP/touch/counter mutation
  end
  return original(image,stamp,...)
 end
 rawset(dates,'setCaptureDate',state.wrapper);_G.captureDateEquivalenceGuard241=state
 local expire;expire=function()if not state.active then return end;local remaining=state.expires-now();if remaining<=0 then state.restore('timer')else loop.afterDelay(remaining,expire)end end
 loop.afterDelay(7200,expire)
 note('INSTALLED bounded7200s; exact timestamp/date equivalence only; native fallback retained')
 return true
end
