"""Check the production log formatter/sinks without game or installation writes."""
import json,hashlib
from pathlib import Path
from lupa.lua51 import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
SRC=ROOT/'HD2PhysBoneCompat/src'
def main():
 vm=LuaRuntime(unpack_returned_tuples=True);module=vm.execute((SRC/'native_grip_transfer_test.lua').read_text('utf8'))
 checks=vm.execute(r'''return function(M)
 local t,lines=0,{}
 local log,ctx=M.newLogSink(function(s)lines[#lines+1]=s end,function()return t end,
  {recordSeconds=90,maxBytes=16384,exceptionIntervalSeconds=2})
 log('{"event":"loaded"}');t=1000
 assert(not ctx.started,'ship time spent mission budget')
 log('{"event":"applied","frame":1}');assert(ctx.started==1000)
 t=1091;log('{"event":"applied","frame":2}')
 assert(ctx.stopped and lines[#lines]:find('log_recording_stopped',1,true))
 local before=#lines
 for i=1,1000 do log('{"event":"applied","frame":3}')end
 assert(#lines==before,'duration cap not enforced')
 log('{"event":"mount_skipped","stage":"final_candidate","frame":4}')
 assert(#lines==before+1,'late exception lost')
 for i=1,10000 do log('{"event":"mount_skipped","stage":"final_candidate","frame":5}')end
 assert(#lines==before+1,'repeat error not rate limited')
 t=t+2;log('{"event":"mount_skipped","stage":"final_candidate","frame":6}')
 assert(#lines==before+2,'later exception did not resume')
 log('{"event":"complete"}');assert(lines[#lines]:find('complete',1,true))
 assert(ctx.bytes<=ctx.maxBytes)
 local bytes=0;t=0
 local burst,b=M.newLogSink(function(s)bytes=bytes+#s+40 end,function()return t end,
  {recordSeconds=90,maxBytes=16384,exceptionIntervalSeconds=0})
 for i=1,5000 do t=t+.001;burst('{"event":"mount_skipped","stage":"final_candidate","payload":"'..string.rep('x',1000)..'"}')end
 burst('{"event":"disabled"}');burst('{"event":"complete"}')
 assert(bytes<=16384 and b.suppressed>0,'byte cap not enforced')
 return {duration=true,byteCap=true,lateExceptions=true,exceptionRateLimit=true,shipTimeExcluded=true,shutdownSummary=true}
 end''')(module)
 # Use a real latest-session probe for the measured character reduction.
 log=Path(r'C:\Users\Administrator\AppData\Roaming\Arrowhead\Helldivers2\hd2_grip_b23.log')
 meta=json.loads((OUT/'战斗握点停用-最新日志诊断.json').read_text('utf8'))
 probe=None
 with log.open('rb') as f:
  f.seek(meta['latestSessionOffset'])
  for line in f:
   if b'"event":"sidearm_probe"' in line:probe=json.loads(line[line.index(b'{'):]);break
 assert probe
 original=module.encodeDiagnostic(vm.table_from(probe,recursive=True),False)
 compact=module.encodeDiagnostic(vm.table_from(probe,recursive=True),True)
 obj=json.loads(compact);assert obj['format']=='positions-v1' and len(obj['parts'])==len(probe['parts'])
 assert len(compact)<len(original)*.25,(len(compact),len(original))
 for key,v in obj['hands'].items():
  assert max(abs(a-b) for a,b in zip(v,probe['hands'][key][9:12]))<.0001
 critical=dict(event='mount_skipped',frame=123,time=100.02,distance=.8,sourceWorld=[1]*12,desiredWorld=[2]*12)
 assert json.loads(module.encodeDiagnostic(vm.table_from(critical,recursive=True),True))==critical
 # Extract and execute the unchanged production logger body with mocked IO/clock.
 text=(SRC/'physbone_runtime.lua').read_text('utf8');a=text.index('local function makeLogger(');b=text.index('local function try(',a)
 vm2=LuaRuntime(unpack_returned_tuples=True)
 setup=r'''local t=0;local rows={};local closed=false
 local M={VERSION='2.2.1'};local S={Application={time_since_launch=function()return t end}}
 local io={open=function(path,mode)assert(mode=='w');return {write=function(_,s)rows[#rows+1]=s end,flush=function()end,close=function()closed=true end}end}
 local function defaultLogPath()return 'mock-only-no-disk' end
 '''+text[a:b]+r'''
 local logger,c=makeLogger({logRecordSeconds=90,logMaxBytes=8192})
 t=1000;c.active=true;c.activate();logger('heartbeat')
 t=1091;logger('heartbeat');assert(c.stopped,'physics duration started='..tostring(c.started)..' bytes='..c.bytes)
 local n=#rows;for i=1,10000 do logger('heartbeat')end;assert(#rows==n,'physics post duration')
 logger('[physbone][失败] sample %d',1);assert(#rows==n+1,'physics late/rate errors rows='..#rows..' expected='..(n+1))
 for i=1,10000 do logger('[physbone][失败] sample %d',1)end;assert(#rows==n+1,'physics late/rate errors rows='..#rows..' expected='..(n+1))
 for i=1,1000 do t=t+2;logger('[physbone][失败] %s',string.rep('x',1200))end
 c.close();assert(closed and c.bytes<=8192,'physics close/bytes')
 return {duration=true,byteCap=true,lateErrors=true,errorRateLimit=true,close=true,suppressed=c.suppressed}
 '''
 physics=vm2.execute(setup)
 plain=lambda table:{k:v for k,v in table.items()}
 result=dict(status='PASS',grip=plain(checks),physics=plain(physics),originalProbeCharacters=len(original),compactProbeCharacters=len(compact),reductionPercent=round(100*(1-len(compact)/len(original)),2),criticalFullMatricesPreserved=True,sourceSha256=hashlib.sha256((SRC/'native_grip_transfer_test.lua').read_bytes()).hexdigest(),physicsSourceSha256=hashlib.sha256((SRC/'physbone_runtime.lua').read_bytes()).hexdigest(),gameDeployed=False,managerSynced=False)
 (OUT/'日志缩减-1.0.17-预算与压缩验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
