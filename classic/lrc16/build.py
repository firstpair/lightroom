"""Build APPLY16.lua: one Scripts-menu action that installs the three LrC 16.0 runtime fixes.

Usage: uv run --no-project --with lupa python classic/lrc16/build.py --catalog /path/to/Catalog.lrcat \
           --run-root /path/to/logs --out "/path/to/Scripts/02) Apply performance fixes.lua"

Server bodies live in server/ (trigger.lua, point.lua, mapcount.lua). Each is embedded verbatim except for the
exact, counted replacements below. The catalog path is substituted as a quoted Lua string.
"""
from pathlib import Path
import argparse, hashlib, json, re, sys
from lupa import lua51

HERE = Path(__file__).resolve().parent
SRC = HERE / 'server'
REVISION = 'lrc16-apply-v3'
ap = argparse.ArgumentParser()
ap.add_argument('--catalog', required=True, help='absolute path of the .lrcat this installer may touch')
ap.add_argument('--run-root', required=True, help='directory for run logs (runs/run-<time>/...)')
ap.add_argument('--out', required=True, help='where to write the Scripts-menu file')
A = ap.parse_args()
CATALOG = A.catalog; ROOT = A.run_root.rstrip('/')
def luastr(v): return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
MAX_TERMS = 8  # each term 6 h; renewal only while the term had no mismatch/error

def body(name):
    b = (SRC / name).read_text().rstrip('\n')
    assert b.count('__CATALOG__') == 1, name
    return b.replace('__CATALOG__', luastr(CATALOG))

def sub(text, old, new, count=1):
    n = text.count(old)
    assert n == count, (old[:80], n)
    return text.replace(old, new)

HEADER_OLD = 'local request = ...\nlocal logRoot = __LOGROOT__\n'
HEADER_NEW = 'local request, logRoot = ...\n'

trigger = sub(body('trigger.lua'), HEADER_OLD, HEADER_NEW)

point = sub(body('point.lua'), HEADER_OLD, HEADER_NEW)
point = re.sub(r"if prior and prior\.active then\n write\('SUPERSEDING.*?\nend\n",
               "if prior and prior.active then write('ALREADY_ACTIVE calls=' .. prior.calls); return 'ALREADY_ACTIVE' end\n",
               point, count=1, flags=re.S)
assert "SUPERSEDING" not in point and "ALREADY_ACTIVE calls" in point
point = sub(point, 'fallbacks = 0, pointSeconds = 0, oracleSeconds = 0 }',
            'fallbacks = 0, pointSeconds = 0, oracleSeconds = 0, term = 1, totalCalls = 0 }')
point = sub(point, 'state.restore = restore\n', f'''state.restore = restore
local function renewOrRestore()
 if state.mismatches == 0 and state.term < {MAX_TERMS} then
  state.totalCalls = state.totalCalls + state.calls; state.calls = 0; state.term = state.term + 1; state.deadline = now() + 21600
  pcall(write, status('RENEWED term=' .. state.term .. ' totalCalls=' .. state.totalCalls))
 else restore('bound reached term=' .. state.term) end
end
''')
point = sub(point, " if not state.active or now() > state.deadline or state.calls >= 2000000 then restore('bound reached'); return original(session, imageId, ...) end\n",
            " if state.active and (now() > state.deadline or state.calls >= 2000000) then renewOrRestore() end\n"
            " if not state.active then return original(session, imageId, ...) end\n")
point = sub(point, "INSTALLED bound=6h/2M calls,", f"INSTALLED bound=6h/2M calls per term, up to {MAX_TERMS} clean terms,")

mapc = sub(body('mapcount.lua'), HEADER_OLD, HEADER_NEW)
mapc = sub(mapc, 'candidateSeconds = 0, oracleSeconds = 0, core = core }',
           'candidateSeconds = 0, oracleSeconds = 0, core = core, term = 1, totalCalls = 0 }')
mapc = sub(mapc, 'local function equal(a, b)', f'''local function renewOrRestore()
 if state.mismatches == 0 and state.candidateErrors == 0 and state.term < {MAX_TERMS} then
  state.totalCalls = state.totalCalls + state.calls; state.calls = 0; state.mapCalls = 0; state.countCalls = 0
  state.term = state.term + 1; state.deadline = now() + 21600
  pcall(write, status('RENEWED term=' .. state.term .. ' totalCalls=' .. state.totalCalls)); return true
 end
 state.restore('bound reached term=' .. state.term); return false
end
local function equal(a, b)''')
mapc = sub(mapc, " if now() > state.deadline or state.calls >= 200000 then state.restore('bound reached'); return original(self, sql, ...) end\n",
           " if now() > state.deadline or state.calls >= 200000 then if not renewOrRestore() then return original(self, sql, ...) end end\n")
JOURNAL_COUNT = "db:firstRow('SELECT COUNT(*) AS n FROM temp.local_repair_map_journal').n"
mapc = sub(mapc, f" if state.calls % 50 == 0 and {JOURNAL_COUNT} > 50000 then state.restore('journal limit') end\n",
           f""" if state.calls % 50 == 0 and {JOURNAL_COUNT} > 50000 then
  -- Rows at or below the cached revision are never read again (deltas only read revision > cached).
  local trimmed = false
  if core.state and db:getAutoCommit() then trimmed = pcall(db.exec, db, string.format('DELETE FROM temp.local_repair_map_journal WHERE revision <= %d', core.state.gen.revision)) end
  if not trimmed or {JOURNAL_COUNT} > 50000 then state.restore('journal limit') else pcall(write, status('JOURNAL_TRIMMED')) end
 end
""")
mapc = sub(mapc, "loop.afterDelay(21600, function() if state.active then state.restore('timer6h') end end)",
           f"loop.afterDelay(21600 * {MAX_TERMS} + 60, function() if state.active then state.restore('final timer') end end)")
# v2: copy the cached map with the built-in C table.shallowcopy (measured 1.51x on the live 827,800-entry map,
# identical and isolated). The cache only ever holds number->string entries checked on full and delta reads.
mapc = sub(mapc, " function cache:get(group) local map=self:refresh(group);return clone(map) end",
           " local cCopy=(type(table.shallowcopy)=='function' and debug and debug.getinfo and debug.getinfo(table.shallowcopy,'S').what=='C') and table.shallowcopy or nil\n"
           " cache.cCopy=cCopy~=nil\n"
           " function cache:get(group) local map=self:refresh(group);if cCopy then return cCopy(map) end;return clone(map) end")
mapc = sub(mapc, "INSTALLED bound=6h/200K calls/50K journal rows;", f"INSTALLED bound=6h/200K calls per term, up to {MAX_TERMS} clean terms, 50K journal rows (trimmed);")
mapc = sub(mapc, "write(status('INSTALLED bound=", "write(status('INSTALLED cCopy=' .. tostring(core.cCopy) .. ' bound=")

# v3 (2026-11-17): when Classic is busy the savepoint cannot open (statements in progress) and v2 returned
# WAIT_TRANSACTION forever. Now install in autocommit mode too (TEMP objects only), with immediate undo on failure,
# and treat a body that finished as installed even if Classic's RELEASE then fails.
trigger = sub(trigger, " assert(not db:getAutoCommit(), 'savepoint did not open (statements in progress): no change')\n",
 " _G.lrc16TriggerBodyDone = nil; local auto = db:getAutoCommit()\n"
 " if auto then log('AUTOCOMMIT savepoint not open (statements in progress); per-trigger install with restore on failure') end\n")
trigger = sub(trigger, "  session:_execWithoutMutationCheck((t.fixed:gsub('^CREATE TRIGGER ', 'CREATE TEMP TRIGGER ', 1)))\n",
 "  local okc, ec = pcall(session._execWithoutMutationCheck, session, (t.fixed:gsub('^CREATE TRIGGER ', 'CREATE TEMP TRIGGER ', 1)))\n"
 "  if not okc then if auto then session:_execWithoutMutationCheck((t.live:gsub('^CREATE TRIGGER ', 'CREATE TEMP TRIGGER ', 1))); log('RESTORED_ORIGINAL ' .. t.name) end; error(ec) end\n")
trigger = sub(trigger, "  assert(#c == 1 and c[1].sql == t.fixed, t.name .. ' install verification failed')\n end\nend)\n",
 "  assert(#c == 1 and c[1].sql == t.fixed, t.name .. ' install verification failed')\n end\n _G.lrc16TriggerBodyDone = true\nend)\n"
 "if not okTx and _G.lrc16TriggerBodyDone then log('BODY_DONE_RELEASE_ERROR ' .. tostring(errTx)); okTx = true end\n")
mapc = sub(mapc, " assert(not db:getAutoCommit(), 'savepoint did not open (statements in progress): no change')\n",
 " _G.lrc16MapBodyDone = nil; local auto = db:getAutoCommit()\n if auto then write('AUTOCOMMIT savepoint not open (statements in progress); TEMP install with drop on failure') end\n"
 " local okb, eb = pcall(function()\n")
mapc = sub(mapc, " assert(db:firstRow(ownershipSQL).n == 9, 'TEMP objects not all created')\nend)\n",
 " assert(db:firstRow(ownershipSQL).n == 9, 'TEMP objects not all created')\n end)\n"
 " if not okb then\n  if auto then for _, r in ipairs(db:gatherArrayOfTables('SELECT type, name FROM sqlite_temp_master WHERE name IN (' .. table.concat(quoted, ',') .. ') ORDER BY type DESC')) do"
 " pcall(session._execWithoutMutationCheck, session, 'DROP ' .. string.upper(r.type) .. ' IF EXISTS temp.' .. r.name) end; write('DROPPED_PARTIAL') end\n  error(eb)\n end\n"
 " _G.lrc16MapBodyDone = true\nend)\n"
 "if not okTx and _G.lrc16MapBodyDone and db:firstRow(ownershipSQL).n == 9 then write('BODY_DONE_RELEASE_ERROR ' .. tostring(errTx)); okTx = true end\n")

for name, b in (('trigger', trigger), ('point', point), ('mapcount', mapc)):
    assert '[=====[' not in b and ']=====]' not in b and '[======[' not in b, name

SERVER = f'''local request = ...
local runRoot = __RUNROOT__
local now = import 'AgDate'.timeIntervalSinceReferenceDate
local function summary(s) local f = io.open(runRoot .. '/native.txt', 'a'); if f then f:write(string.format('%.3f ', now()) .. s .. '\\n'); f:close() end end
local chunks = {{
 {{ 'trigger', [=====[
{trigger}
]=====] }},
 {{ 'point', [=====[
{point}
]=====] }},
 {{ 'mapcount', [=====[
{mapc}
]=====] }},
}}
summary('ENTER {REVISION}')
local all = true
for _, c in ipairs(chunks) do
 local f, err = loadstring(c[2], 'lrc16-' .. c[1])
 local ok, res
 if f then ok, res = pcall(f, request, runRoot .. '/' .. c[1]) else ok, res = false, err end
 summary(string.format('PHASE %s ok=%s result=%s', c[1], tostring(ok), tostring(res)))
 if not ok then all = false end
end
summary('DONE')
return all
'''

UI = f'''-- LrC 16.0: install the three verified runtime performance fixes ({REVISION}). Built by
-- classic/lrc16/build.py from server/trigger.lua, point.lua, mapcount.lua (github.com/firstpair/lightroom).
-- 1 trigger: the two slow file TEMP triggers use SELECT +id_local (TEMP only, until Classic quits).
-- 2 point: isImageIdTracked answered by one indexed row (reads only).
-- 3 mapcount: incremental image->asset map and COUNT from a TEMP journal (reads + TEMP only).
-- Each phase is idempotent (already active/corrected = no change) and checks itself against Adobe's original.
local lib = import 'AgLibrary'
local now = import 'AgDate'.timeIntervalSinceReferenceDate
local runRoot = {luastr(ROOT + '/runs/run-')} .. string.format('%.3f', now())
local fu = import 'LrFileUtils'
for _, d in ipairs({{ '', '/trigger', '/point', '/mapcount' }}) do fu.createAllDirectories(runRoot .. d) end
local function uilog(s) local f = assert(io.open(runRoot .. '/UI.txt', 'a')); f:write(string.format('%.3f ', now()) .. s .. '\\n'); f:close() end
local active = lib.getActiveCatalogPathIfAvailable()
if active ~= {luastr(CATALOG)} then uilog('WRONG_CATALOG ' .. tostring(active)); return end
if _G.lrc16ApplyRequest then uilog('PREVIOUS_REQUEST_PENDING'); return end
local code = [======[
{SERVER}]======]
code = code:gsub('__RUNROOT__', function() return string.format('%q', runRoot) end)
local handle
handle = lib.activeServer():asapRequest{{
 namespace = 'AgServerUtils', message = 'runOnServer', args = {{ code }},
 callback = function(_, result) uilog('native callback result=' .. tostring(result)); if handle then handle:close() end; _G.lrc16ApplyRequest = nil end,
 errorHandler = function(_, err) uilog('actual server error=' .. tostring(err)); if handle then handle:close() end; _G.lrc16ApplyRequest = nil end,
}}
_G.lrc16ApplyRequest = handle
uilog('submitted {REVISION}')
'''

L = lua51.LuaRuntime()
check = L.eval('function(s, n) local f, e = loadstring(s, n); if not f then error(e) end; return true end')
check(UI, 'ui')
inner = re.search(r'local code = \[======\[\n(.*?)\]======\]', UI, re.S).group(1)
assert inner == SERVER
check(inner.replace('__RUNROOT__', '"/tmp/x"'), 'server')
for name, b in (('trigger', trigger), ('point', point), ('mapcount', mapc)):
    check(b, name)
out = Path(A.out)
out.write_text(UI)
print(json.dumps({'revision': REVISION, 'bytes': len(UI), 'sha256': hashlib.sha256(UI.encode()).hexdigest()}))
