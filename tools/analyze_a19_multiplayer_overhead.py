"""Structural 1/4-player A19 comparison in a real-model fake-engine Chef fixture. NOT FPS."""
from pathlib import Path
import argparse, collections, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-single-loader-size-fix-20261117'
OUT=ROOT/'outputs/physics-A19-one-vs-four-analysis-20261117'
TEST=ROOT/'HD2PhysBoneCompat/test/single-consumer-runtime-test.py'

def main():
    global OUT
    args=argparse.ArgumentParser();args.add_argument('--identity-watch',action='store_true');parsed=args.parse_args()
    if parsed.identity_watch: OUT=OUT.with_name(OUT.name+'-identity-watch')
    require= lambda ok,msg: None if ok else (_ for _ in ()).throw(AssertionError(msg))
    require(not OUT.exists(),'Never overwrite analysis evidence')
    OUT.mkdir()
    fixture=OUT/'fixture'
    prefix=TEST.read_text('utf-8-sig').split("rows=[s for s in state.sessions.values()]",1)[0]
    prefix=prefix.replace(' return S\n\ne.api=wrap(api)',' instrument_api(S)\n return S\n\ne.api=wrap(api)',1)
    api_counts=None
    def instrument_api(S):
        nonlocal api_counts
        lua=env['lua']
        if api_counts is None:api_counts=lua.table()
        lua.eval('''function(S,c)
          for _,g in ipairs({'Unit','World','Application'})do
            for name,fn in pairs(S[g] or {})do
              if type(fn)=='function' then
                local key=g..'.'..name
                S[g][name]=function(...)c[key]=(c[key]or 0)+1;return fn(...)end
              end
            end
          end
        end''')(S,api_counts)
    env={'__file__':str(TEST),'__name__':'isolated_fixture','instrument_api':instrument_api}
    sys.argv=[str(TEST),'--source',str(LAB/'release-candidate/A-extracted'),'--output',str(fixture),'--vm','lua51','--chef-bit',str(LAB/'actual-chef-bit-shim.lua'),'--chef-patch',str(LAB/'release-candidate/A-export/physics-runtime.zip'),'--chef-core',str(LAB/'actual-chef-core-1.lua')]
    exec(compile(prefix,str(TEST),'exec'),env)
    lua,e,state,R,av= [env[k]for k in ['lua','e','state','R','av']]
    same=lua.eval('function(a,b)return a==b end')
    if parsed.identity_watch:R.setOptions(lua.table_from({'identityWatch':True}))
    e.levels=900;e.advance(e,40);e.fp=True;e.advance(e,140)
    require(same(state.singleState.selfUnit,av),'Local first ADS latch missing')
    e.advance(e,360)
    rows=[]
    def sample(label,players):
        require(state.consumerContext.done,'Do not measure pending proof work as steady-state')
        env['updates'].clear();env['writes'].clear()
        for k in list(api_counts.keys()):api_counts[k]=0
        fp_before=e.fpCalls;attach_before=dict(env['attachCounts'])
        lua.execute('instructionSamples=0;debug.sethook(function()instructionSamples=instructionSamples+1 end,"",1000)')
        e.advance(e,600,0.01)
        lua.execute('debug.sethook()')
        samples=int(lua.globals().instructionSamples)
        sessions=list(state.sessions.values());own=[s for s in sessions if same(s.owner,av)];remote=[s for s in sessions if not same(s.owner,av)]
        evidence=[]
        for s in sessions:
            uid=int(s.unit.id)
            evidence.append({'unitId':uid,'localOwner':bool(same(s.owner,av)),'resource':str(s.unit.realRid),'consumerMode':s.consumerMode,'retainedChains':len(s.sessions),'excluded':bool(s.singleRemotePhysicsExcluded),'solverCalls':env['updates'][uid],'successfulBoneWrites':env['writes'][uid]})
        require(len(state.avatars)==players and len(sessions)==players*7,'Unexpected roster/session count')
        require(all(s.singleRemotePhysicsExcluded for s in remote),'Remote exclusion not applied')
        require(all(x['solverCalls']==0 and x['successfulBoneWrites']==0 for x in evidence if not x['localOwner']),'Remote solver or write leakage')
        require(all(x['solverCalls']==600 for x in evidence if x['localOwner'] and x['consumerMode']!='empty'),'Local solver cadence changed')
        require(e.fpCalls==fp_before,'ADS identity polling restarted')
        require(dict(env['attachCounts'])==attach_before,'Stable roster repeatedly reattached')
        row={'label':label,'players':players,'frames':600,'sessions':len(sessions),'activeLocalSessions':sum(s.consumerMode!='empty'for s in own),'excludedRemoteSessions':len(remote),'retainedAllChains':sum(len(s.sessions)for s in sessions),'localSolverCalls':sum(x['solverCalls']for x in evidence if x['localOwner']),'remoteSolverCalls':sum(x['solverCalls']for x in evidence if not x['localOwner']),'remoteSuccessfulBoneWrites':sum(x['successfulBoneWrites']for x in evidence if not x['localOwner']),'fpQueryDelta':int(e.fpCalls-fp_before),'consumerProofDone':True,'luaInstructionHookSamplesEvery1000':samples,'apiCalls':{str(k):int(v)for k,v in sorted(api_counts.items())},'units':evidence}
        rows.append(row)
        print(label,json.dumps({k:v for k,v in row.items() if k not in ['apiCalls','units']},ensure_ascii=False),flush=True)
    sample('one-player-stable',1)
    for i in range(1,4):env['player']('remote'+str(i),20*i)
    e.advance(e,660);env['wait_for_proof']('joined-4')
    sample('four-players-stable',4)
    remote_parts=env['parts'][1:]
    for i,us in enumerate(remote_parts):
        for u in us:e.remove(e,u)
        e.remove(e,env['avatars'][i+1])
    e.advance(e,660)
    sample('one-player-after-remotes-leave',1)
    R.uninstall()
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    result={'status':'PASS_A19_REAL_MODEL_CHEF_ONE_FOUR_ONE_STRUCTURAL_COMPARISON_NOT_FPS','actualRuntimeVersion':'2.3.19','compatVersion':'1.3.13','luaVm':'Lua5.1 + actual Chef pure Lua bit','actualChefPatchSha256':sha(LAB/'release-candidate/A-export/physics-runtime.zip'),'runtimeSha256':sha(LAB/'release-candidate/A-extracted/physbone_runtime.lua'),'fixtureSourceSha256':sha(TEST),'analysisScriptSha256':sha(Path(__file__)),'renderAndGpuContentShaForbidden':True,'sourceModel':'test01 real bind/rig/Unit payload','sameRetainedLocalSolverCadence':True,'remoteSolverAndSuccessfulWritesZero':True,'notActualGameOrFpsMeasurement':True,'previewIdentityWatchEnabled':parsed.identity_watch,'instructionCountsIncludeFakeEngineAndInstrumentation':True,'phases':rows}
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'],flush=True)
if __name__=='__main__':main()
