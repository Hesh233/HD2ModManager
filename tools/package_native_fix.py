"""Prepare and package the O-3 native-rig correction; never writes game data."""
import argparse,hashlib,json,re,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,STATE_MACHINE_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID

def patch(path):
    return TocArchive.parse_parts(path.read_bytes(),*(Path(str(path)+s).read_bytes() if Path(str(path)+s).exists() else b'' for s in ('.gpu_resources','.stream')))

def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-model',action='store_true')
    parser.add_argument('--work',type=Path,default=ROOT/'outputs/native-fix-20261103')
    args=parser.parse_args(); work=args.work.resolve(); project=work/'project'
    source=project/'models/test01'; model=project/'models-o3/test01-O3'
    if args.prepare_model:
        if model.exists(): raise FileExistsError(model)
        model.mkdir(parents=True)
        result=json.loads((work/'rekey-result.json').read_text(encoding='utf-8-sig'))
        output=Path(result['outputPatch'])
        for p in (output,Path(str(output)+'.gpu_resources'),output.parent/'sections.json',
                  source/'9ba626afa44a3aa3.patch_1',source/'9ba626afa44a3aa3.patch_1.gpu_resources',
                  source/'source-skeleton.json',source/'physbone-rig.bin'):
            shutil.copy2(p,model/p.name)
        for i in (0,1): (model/f'9ba626afa44a3aa3.patch_{i}.stream').write_bytes(b'')
        shutil.copy2(work/'conversion.json',model/'vpk2patch.json')
        shutil.copy2(project/'config.toml',model/'config.toml')
        target={'armor':'O-3 自由之魂','armorArchive':'f9ced2d898787705','helmetArchive':'a2999407862595df',
                'bodyTypes':['Slim','Stocky'],'modelScale':1.2,'gameTested':False}
        (model/'replacement-target.json').write_text(json.dumps(target,ensure_ascii=False,indent=2),encoding='utf-8')
        print(model); return
    build=json.loads((project/'animations/build-report.json').read_text(encoding='utf-8'))
    assert build['status']=='complete' and len(build['animations'])==build['expected_animations']==3180
    assert build['model_scale']==1.2 and build['blend_masks_extended']==80
    assert json.loads((project/'animations/source-skeleton.json').read_text())==json.loads((source/'source-skeleton.json').read_text())
    keys=set(); models=[]
    for p in model.glob('*.patch_*'):
        if p.suffix in ('.stream','.gpu_resources'): continue
        ar=patch(p); assert not list(ar.entries_of_type(STATE_MACHINE_TYPE_ID))
        for key in ar.entries: assert key not in keys; keys.add(key)
        models.extend(ar.entries_of_type(UNIT_TYPE_ID))
        assert Path(str(p)+'.stream').exists() and Path(str(p)+'.gpu_resources').exists()
    assert len(models)==17
    assert b'HD2PBFT1' in (model/'9ba626afa44a3aa3.patch_0.gpu_resources').read_bytes()[-56:]
    # Material bytes come exclusively from the original test01 conversion.
    for suffix in ('','.gpu_resources'):
        name='9ba626afa44a3aa3.patch_1'+suffix
        old=ROOT/'outputs/native-manual-20261103/project/models/test01'/name
        assert digest(model/name)==digest(old),(name,'material changed')
    runtime=project/'animations/runtime'; runtime_counts={}; animation_ids=set()
    for p in sorted(runtime.glob('*.patch_*')):
        if p.suffix in ('.stream','.gpu_resources'): continue
        ar=patch(p)
        for key in ar.entries:
            assert key not in keys,key; keys.add(key)
            runtime_counts[key[1]]=runtime_counts.get(key[1],0)+1
            if key[1]==ANIMATION_TYPE_ID: animation_ids.add(key[0])
        assert Path(str(p)+'.stream').exists() and Path(str(p)+'.gpu_resources').exists()
    assert runtime_counts=={UNIT_TYPE_ID:1,BONE_TYPE_ID:1,STATE_MACHINE_TYPE_ID:1,ANIMATION_TYPE_ID:3180},runtime_counts
    for entry in build['files']:
        p=project/'animations'/entry['path']; assert p.stat().st_size==entry['bytes'] and digest(p)==entry['sha256']
    reference=patch(ROOT.parent/'output/9ba626afa44a3aa3.patch_0')
    assert animation_ids=={e.file_id for e in reference.entries_of_type(ANIMATION_TYPE_ID)}
    physics=project/'physics-runtime/patch版'
    next_index=max(int(p.name.split('.patch_')[1]) for p in runtime.glob('*.patch_*') if p.suffix not in ('.stream','.gpu_resources'))+1
    for suffix in ('','.gpu_resources','.stream'):
        old=physics/('9ba626afa44a3aa3.patch_0'+suffix)
        new=physics/(f'9ba626afa44a3aa3.patch_{next_index}'+suffix)
        if old.exists(): old.rename(new)
        assert new.exists()
    (project/'source').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'testVPK/test01.vpk',project/'source/test01.vpk')
    shutil.copy2(source/'source-skeleton.json',project/'source-skeleton.json')
    for name in ('conversion.json','reference-structure.json','rekey-result.json','motion-audit.json','physics-audit.json','physics-test.log','physics-embed.json'):
        shutil.copy2(work/name,project/'reports'/name)
    readme='''test01 · O-3 自由之魂 · 模型倍率 1.2

这是重新生成的游戏测试包，尚未完成游戏内验收。模型、骨架和动画需要成套更新。

1. 停用旧 test01 模型及配套动画，导入本目录的 test01-模型材质.zip 和 test01-配套动画.zip。
2. 穿上 O-3“自由之魂”护甲和同名头盔；支持健壮、苗条两种体型，无需再做映射。
3. 物理任选一种入口：使用附带新版管理器的内置 Lua 物理功能；或使用已有外置 Lua 加载器并导入 test01-物理运行时.zip。不要同时加载两个入口。
   外置运行时包是 addon，不能单独充当 Lua 加载器。管理器入口：manager/HD2ModManager.exe。
4. 进入游戏检查待机收臂、走路腰部、瞄准/换弹、蹲伏/趴下，以及头发、飘带、裙摆；本次离线检查不代替这些实机检查。

格式：模型/材质在 patch_0、1，骨架 Unit/Bones 在 patch_2（不含 StateMachine），
新增 179 通道的混合遮罩单独位于配套动画的 patch_3，全部 3,180 条动画位于 patch_4～53。
模型包不含任何 StateMachine；模型材质沿用 test01，未采用参考包材质。
全部补丁使用 9ba626afa44a3aa3 文件名前缀并附齐 GPU/stream 文件；空 sidecar 也请保留。
可选外置物理运行时为 patch_54。通过管理器安装时，管理器会统一重编号。

GUI 拖入来源 VPK 后，可输入模型大小倍率，默认 1；支持大于 0 且不超过 10 的数值。
倍率随转换记录保存，重建会沿用。当前工程 project/config.toml 中 model_scale = 1.2。
修改工程倍率后必须重新转换模型并重建配套动画，不能只改动画配置。
project/models 保存可重新映射的原始素体；project/models-o3 为固定 O-3 成品。
本工程保留 89 根 Source 骨，追加到 107 节点 avatar 中；一次只启用一套此类共享骨架/动画替换。
第一人称手臂、持握 IK、程序化动作与放大后的脚底接触仍需游戏测试。

离线记录在 project/reports：部位覆盖、骨架参考方向、混合遮罩、缩放和物理模拟。
17 根物理骨组成 12 条链，已在 Lua 5.1 下每链模拟 600 帧，全部找到来源父骨锚点。
'''
    (work/'先读我-修复测试.txt').write_text(readme,encoding='utf-8-sig')
    (project/'Rebuild-Animations.ps1').write_text('''param(
    [string] $GameData = 'E:\\Steam\\steamapps\\common\\Helldivers 2\\data',
    [string] $Output = (Join-Path $PSScriptRoot ('animations-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
)
$manager = Join-Path (Split-Path -Parent $PSScriptRoot) 'manager'
& (Join-Path $manager 'anim_batch_mod\\runtime\\python.exe') -X utf8 (Join-Path $manager 'anim_batch_mod\\main.py') native-project --manifest (Join-Path $PSScriptRoot 'source-skeleton.json') --config (Join-Path $PSScriptRoot 'config.toml') --game-data $GameData --output $Output
exit $LASTEXITCODE
''',encoding='utf-8-sig')
    def archive(directory,name,skip_runtime=False):
        target=work/name
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(directory.rglob('*')):
                if p.is_file():
                    rel=p.relative_to(directory)
                    if skip_runtime and (rel.parts[:2]==('animations','runtime') or p.suffix=='.sqlite3'): continue
                    z.write(p,rel.as_posix())
        with zipfile.ZipFile(target) as z: assert z.testzip() is None
        return {'name':name,'bytes':target.stat().st_size,'sha256':digest(target)}
    files=[archive(project/'models-o3','test01-模型材质.zip'),archive(runtime,'test01-配套动画.zip'),
           archive(physics,'test01-物理运行时.zip'),archive(project,'test01-源工程.zip',True)]
    report={'status':'PASS','gameTested':False,'modelScale':1.2,'modelUnits':17,'modelStateMachines':0,
            'runtimeResources':sum(runtime_counts.values()),'animations':len(animation_ids),'files':files}
    (work/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
