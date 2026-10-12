-- Invoked only after explicit authorization of macOS menu automation.
-- Brings the exact Classic process forward only for the configured menu action.
-- No private SDK imports, catalog access, Sync changes, or quit.
on run argv
    set expectedPID to (item 1 of argv) as integer
    tell application "System Events"
        if not UI elements enabled then return "ACCESSIBILITY_REQUIRED"
        set matches to application processes whose unix id is expectedPID
        if (count matches) is not 1 then return "PROCESS_GONE"
        set lr to item 1 of matches
        if bundle identifier of lr is not "com.adobe.LightroomClassicCC7" then return "WRONG_APP"
        tell lr
            if not (exists menu bar 1) then return "WAIT_FOR_UI"
            set mainPresent to false
            repeat with w in windows
                if name of w contains "@@CATALOG_NAME@@ - Adobe Photoshop Lightroom Classic" then set mainPresent to true
            end repeat
            if not mainPresent then return "WAIT_FOR_MAIN_CATALOG"
            if not frontmost then set frontmost to true
            if not (exists menu bar item "Scripts" of menu bar 1) then return "WAIT_FOR_SCRIPTS"
            click menu bar item "Scripts" of menu bar 1
            set itemsFound to {}
            repeat with mi in menu items of menu 1 of menu bar item "Scripts" of menu bar 1
                if name of mi contains "Apply FirstPair performance fixes" then set end of itemsFound to mi
            end repeat
            if (count itemsFound) is not 1 then
                key code 53
                return "MENU_TARGET_NOT_UNIQUE"
            end if
            if not enabled of item 1 of itemsFound then
                key code 53
                return "WAIT_FOR_ENABLED_MENU"
            end if
            click item 1 of itemsFound
            return "CLICK_SUBMITTED"
        end tell
    end tell
end run
