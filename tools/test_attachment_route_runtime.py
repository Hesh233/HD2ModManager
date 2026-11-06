"""Existing runtime regression suite plus disabled/subset policy tests (Lua 5.1)."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
W=ROOT/'outputs/attachment-routes-20261106'
old=ROOT/'outputs/native-v34-b23-integrated-20261105'
profile=json.loads((old/'B23-profile.json').read_text(encoding='utf-8-sig'));fixture=json.loads((old/'runtime-fixture.json').read_text(encoding='utf-8-sig'))
harness=(ROOT/'HD2PhysBoneCompat/test/native_grip_transfer_harness.lua').read_text(encoding='utf-8-sig').replace('-- STRICT_ID_FIXTURE',(ROOT/'HD2PhysBoneCompat/test/strict_id32_fixture.lua').read_text(encoding='utf-8-sig'))
tail=harness.rindex('\nreturn {integratedCases=')
extra='''
integratedProfile.rightAttachmentEnabled=false
integratedProfile.leftGrip.enabled=false
integratedProfile.bodySync.enabled=false
integratedProfile.attachments={}
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r');refresh_all()
local untouched=copy(A.locals)
step(runtime,'render',9000,900)
check(not runtime.disabled and runtime.stats.writes==0 and runtime.stats.leftWrites==0 and runtime.stats.attachmentWrites==0,'disabled settings still write')
for i=1,A.count do check(near(A.locals[i],untouched[i]),'disabled mount/body changed') end
runtime:stop()
integratedProfile.attachments={}
for _,row in ipairs(fullProfile.attachments or {}) do if row.node.name=='pistol' then integratedProfile.attachments[1]=row end end
-- fullProfile was stripped by the original harness; use the saved integrated row.
local pistol
for _,row in ipairs(originalConfig.attachments or {}) do if row.node.name=='pistol' then pistol=row end end
integratedProfile.attachments={pistol}
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r');refresh_all()
local rightBefore=copy(A.locals[integratedProfile.target.index+1])
step(runtime,'render',9001,900.02)
check(not runtime.disabled and runtime.stats.writes==0 and runtime.stats.attachmentWrites==1,'subset did not isolate pistol')
check(near(rightBefore,A.locals[integratedProfile.target.index+1]),'disabled right-hand mount modified')
runtime:stop()
-- Exercise the new Source-mount world-read branch with deterministic source-node
-- stand-ins; compiled real profiles separately verify dedicated helper hashes/parents.
integratedProfile=copy(originalConfig)
integratedProfile.bodySync.enabled=false;integratedProfile.leftGrip.enabled=false
integratedProfile.sourceRightMount=copy(integratedProfile.sourceRight)
for _,row in ipairs(integratedProfile.attachments) do row.sourceMount=copy(row.source) end
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r');refresh_all()
local rightBasis=copy(A.cache[integratedProfile.target.index+1])
step(runtime,'render',9002,900.04)
check(not runtime.disabled and runtime.stats.writes==1 and runtime.stats.attachmentWrites==#integratedProfile.attachments,'Source mount world-read path failed')
local actual=A.cache[integratedProfile.target.index+1];local wanted=A.cache[integratedProfile.sourceRight.index+1]
for i=1,9 do check(math.abs(actual[i]-rightBasis[i])<1e-7,'native aim basis changed by Source mount') end
for i=10,12 do check(math.abs(actual[i]-wanted[i])<1e-7,'right mount did not use Source world') end
for _,row in ipairs(integratedProfile.attachments) do
 local a,b=A.cache[row.node.index+1],A.cache[row.source.index+1]
 for i=10,12 do check(math.abs(a[i]-b[i])<1e-7,'attachment ignored its Source mount') end
end
runtime:stop()
return {status='PASS',checks=checks,disabledPolicyPreservesAllNodes=true,subsetWritesOnlySelectedMount=true,sourceMountWorldReadBranch=true,gameTested=false}
'''
from prepare_native_v31_b23 import lua
harness=harness[:tail]+'\nlocal originalConfig='+lua(profile)+'\n'+extra
result=plain(run_harness(profile,fixture,harness));W.mkdir(exist_ok=True);(W/'lua-route-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
