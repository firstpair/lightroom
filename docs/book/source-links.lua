-- Project-owned export adapter. Canonical manuscript links stay unchanged.
local root=assert(os.getenv('LIGHTROOM_REPO_ROOT'),'Expected source repository root')
local commit=pandoc.system.with_working_directory(root,function()
 return pandoc.pipe('git',{'rev-parse','HEAD'},''):gsub('%s+$','')
end)
assert(commit:match('^[0-9a-f]+$') and #commit==40,'Expected exact source commit')
local source='https://github.com/firstpair/lightroom/'
function Link(link)
 if link.target:sub(1,3)=='../' then
  local path=link.target:sub(4)
  assert(path~='' and not path:find('..',1,true),'Unexpected relative source link')
  local kind=path=='templates/runtime' and 'tree/' or 'blob/'
  link.target=source..kind..commit..'/'..path
 end
 return link
end
