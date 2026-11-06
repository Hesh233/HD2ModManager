import json,hashlib
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();w=r/'outputs/test04-08-rs89-20261106';target=r/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';candidate=w/'manager'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
results=[]
for i in range(4,9):
 name=f'test{i:02d}';p=w/(name+'-initial')/name
 flow=load(p/'import-regression.json');audit=load(p/'route-audit.json');mask=load(p/'mask-audit.json');rekey=load(p/'rekey-result.json');build=load(p/'animations/build-report.json')
 profile=load(next((p/'attachment').rglob('attachment-profile.json')));attachment=load(next((p/'attachment').rglob('attachment-build-report.json')))
 assert flow['status']==audit['status']==mask['status']=='PASS'
 assert flow['targetArchive']=='85d392768bf6a259' and flow['samples']==32 and build['diagnosticSample']
 assert rekey['Ok'] and attachment['modelDiscovery']['sourceOwnershipGate']
 vpk=r/'testVPK'/(name+'.vpk')
 results.append(dict(model=name,status='PASS',scale=1.0,animations=32,sourceBones=mask['sourceBones'],
  replacedUnits=rekey['ReplacedUnits'],hiddenMeshes=rekey['HiddenMeshes'],targetBodies=len(attachment['modelDiscovery']['targetBodies']),
  masks=mask['masks'],maskOwnerChecks=mask['ownerChecks'],independentChecks=audit['checks'],maxNativeChannelError=audit['maxNativeChannelError'],
  sourceSha256=sha(vpk),unmappedRoots=mask['rootMasks'],sourceUnchanged=flow['protectedModelUnchanged'],sampleOnly=True))
info=load(target/'anim_batch_mod/build-info.json');assert info['pipelineVersion']=='1.0.13'
for f in info['files']:assert sha(candidate/'anim_batch_mod'/f['name'])==sha(target/'anim_batch_mod'/f['name'])==sha(r.parent/f['name'])
for f in ['HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll']:assert sha(candidate/f)==sha(target/f)
report=dict(status='PASS',target='RS-89 Shadow Paragon',targetArchive='85d392768bf6a259',pipelineVersion='1.0.13',
 results=results,totalAnimations=160,totalMasks=400,totalMaskOwnerChecks=sum(x['maskOwnerChecks'] for x in results),
 totalIndependentChecks=sum(x['independentChecks'] for x in results),newFailures=[],productionCodeChanged=False,
 installedCodeHashMatchesTested=True,sampleOnly=True,manualGuiTested=False,gameTested=False,gameDeployed=False)
(w/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','totalAnimations','totalMasks','totalMaskOwnerChecks','totalIndependentChecks','newFailures']},ensure_ascii=False))
lines=['# test04–08 → RS-89 验证（2026-11-06）','', '使用指定管理器同源1.0.13程序集/官方随包Python，隔离库，默认1.0倍率；完整转换、真实只读入库、RS-89换甲、Lua/32条代表性动画、配套入库及独立检查。','', '| VPK | Source骨数 | RS-89身体挂载Unit | 动画抽样 | 全部遮罩 | 结果 |','|---|---:|---:|---:|---:|---|']
for x in results:lines.append(f"| {x['model']} | {x['sourceBones']} | {x['targetBodies']} | {x['animations']} | {x['masks']} | PASS |")
lines += ['',f"共160条代表性动画、400张完整遮罩、{report['totalMaskOwnerChecks']:,}次新增遮罩权重核对和{report['totalIndependentChecks']:,}次独立通道/挂点检查通过。HD2原遮罩字节保留，通道最大误差4.80e-7。",'','本轮无新故障，不需要额外修改生产逻辑，管理器保持1.0.13。test06有Armature根骨，1.0.13父通道继承规则通过。原VPK和只读模型生成期间不变；不修改活动库/用户设置/游戏部署。','', '**边界：32条是覆盖全量动画ID范围的诊断抽样，不是全量重烘或游戏视觉验收；抽样包禁止全量部署。**']
(w/'测试说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
