on run
    set rootPath to "@@ROOT@@/"
    set responsePath to rootPath & "HELPER-RESPONSE.txt"
    set requestText to read POSIX file (rootPath & "HELPER-REQUEST.txt")
    set fields to paragraphs of requestText
    if (count fields) is not 3 then return
    set expectedPID to (item 1 of fields) as integer
    set nonce to item 2 of fields
    set expiry to (item 3 of fields) as integer
    set epochNow to (do shell script "/bin/date +%s") as integer
    if epochNow > expiry then return
    try
        set sourceText to read POSIX file (rootPath & "Dispatch.applescript")
        set outcome to run script sourceText with parameters {expectedPID as text}
    on error errorText number errorNumber
        set outcome to "ERROR " & errorNumber & " " & errorText
    end try
    set resultText to nonce & linefeed & outcome & linefeed
    set outFile to open for access POSIX file responsePath with write permission
    try
        set eof outFile to 0
        write resultText to outFile as «class utf8»
        close access outFile
    on error
        try
            close access outFile
        end try
    end try
end run
