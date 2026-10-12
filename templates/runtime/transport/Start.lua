local root="@@ROOT@@/runtime/transport"
local lib=import 'AgLibrary';assert(lib.getActiveCatalogPathIfAvailable()=='@@CATALOG@@')
local crypto=require 'WFCrypto'
local pins={["@@ROOT@@/runtime/transport/NativeEnvironment.lua"]="aa4c7efec4085cb81b3d41d58881f2a17fad84dd795f9aaa28312f9c615b668a",["@@ROOT@@/runtime/transport/OwnershipBootstrap.lua"]="ffb2847eacbeec6f60e926c82b0449fca8aebfa2cfe52dfc74513a4418438946",["@@ROOT@@/runtime/transport/Coordinator.lua"]="1097c3caff816af12f7d650036149bbb119e941a9b07f19d3e2ba1b7f6f2dabf",["@@ROOT@@/runtime/transport/Config.lua"]="ef01a5c7ff79304bcae8ff00ec6356a24c38e5582b1564d47b61d8a1d196397e"}
for path,sha in pairs(pins)do assert(string.lower(crypto.digestFile(path,'SHA256'))==sha,'transport dependency changed: '..path)end
local config=assert(loadfile("@@ROOT@@/runtime/transport/Config.lua"))();assert(config.authorized==false);config.authorized=true;config.maxRuns=1;config.output=root..'/runs'
local env=assert(loadfile(root..'/NativeEnvironment.lua'))()(root,config)
local make=assert(loadfile("@@ROOT@@/runtime/transport/Coordinator.lua"))()
local bootstrap=assert(loadfile(root..'/OwnershipBootstrap.lua'))()
local previous=_G.automaticMapTransport178 or _G.mapTransportController173
_G.automaticMapTransport178=bootstrap(config,env,make,previous,env.note)
env.note('STARTUP_HOOK zero-event-v1 bounded1run; native owner/listener/exact-positive-ACK gates; normal fallbacks retained')
return true
