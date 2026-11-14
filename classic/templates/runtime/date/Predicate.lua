-- Candidate only. Does not install a hook or modify any object.
-- Caller supplies the original native AgMetadata.XMPDateToTimeStamp function.
local function wholeSecond(s)
    if type(s) ~= 'string' then return nil end
    local zone = s:match('([+-]%d%d:%d%d)$')
    if zone then
        local hh, mm = zone:match('[+-](%d%d):(%d%d)')
        hh, mm = tonumber(hh), tonumber(mm)
        if hh > 14 or mm > 59 or (hh == 14 and mm ~= 0) then return nil end
        s = s:sub(1, #s - #zone)
    elseif s:sub(-1) == 'Z' then return nil end
    if s:match('^%d%d%d%d%-%d%d%-%d%dT%d%d:%d%d:%d%d$') then return s, zone end
    local base, fraction = s:match('^(%d%d%d%d%-%d%d%-%d%dT%d%d:%d%d:%d%d)%.(%d+)$')
    if base and #fraction <= 9 and fraction:match('^0+$') then return base, zone end
    return nil
end

return function(image, timestamp, nativeParser)
    if type(timestamp) ~= 'number' or timestamp ~= timestamp
        or timestamp == math.huge or timestamp == -math.huge
        or type(nativeParser) ~= 'function' then return false end
    -- Preserve the setter's initialization work rather than bypass it.
    if not image or not image.originalCaptureTime then return false end
    local metadata = image.extendedMetadata
    if not metadata or not metadata.dateTime then return false end
    local capture, captureZone = wholeSecond(image.captureTime)
    if captureZone then return false end
    local originalBase, originalZone = wholeSecond(metadata.dateTimeOriginal)
    local createdBase, createdZone = wholeSecond(metadata.dateCreated)
    if not capture or originalBase ~= capture or createdBase ~= capture
        or originalZone ~= createdZone then return false end
    local ok, currentTimestamp = pcall(nativeParser, image.captureTime)
    if not ok or type(currentTimestamp) ~= 'number' then return false end
    return currentTimestamp == timestamp
end
