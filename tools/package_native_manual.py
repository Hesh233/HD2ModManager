"""Package the verified local test run; --refresh updates delivery without rebuilding animations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--refresh',action='store_true')
refresh=parser.parse_args().refresh
release=ROOT/'outputs/native-manual-20261103'
project=release/'project'
fixed_model_root=project/'models-o3'
target_file=fixed_model_root/'test01-O3/replacement-target.json'
fixed_target=json.loads(target_file.read_text(encoding='utf-8')) if target_file.exists() else None
model_root=fixed_model_root if fixed_target else project/'models'
animations=ROOT/'outputs/native-test01-v3/animations'
report=json.loads((animations/'build-report.json').read_text(encoding='utf-8'))
assert report['status']=='complete' and len(report['animations'])==report['expected_animations']==3180
assert not list((release/'manager').rglob('anim_batch_mod.exe')), 'Retired PyInstaller executable must not ship'
old=json.loads((animations/'source-skeleton.json').read_text(encoding='utf-8-sig'))
new=json.loads((project/'models/test01/source-skeleton.json').read_text(encoding='utf-8-sig'))
assert old==new, 'Model and animation manifests differ'
for path in ['source','reports','animations']:
    (project/path).mkdir(exist_ok=True)
shutil.copy2(ROOT/'testVPK/test01.vpk',project/'source/test01.vpk')
shutil.copy2(animations/'config.toml',project/'config.toml')
shutil.copy2(animations/'source-skeleton.json',project/'source-skeleton.json')
shutil.copy2(animations/'build-report.json',project/'animations/build-report.json')
shutil.copy2(release/'conversion.json',project/'reports/conversion.json')
for name in ['native-source-audit.json','native-complete-audit.json','native-official-python-audit.json',
             'native-final-runtime-smoke.json','native-python-tests.log','native-model-serialized-audit.json',
             'native-published-import.json']:
    shutil.copy2(ROOT/'outputs'/name,project/'reports'/name)
shutil.copy2(ROOT/'outputs/native-import-tests/native-import-tests.trx',project/'reports/native-import-tests.trx')
shutil.copy2(ROOT/'docs/native-source-skeleton-20261103.md',release/'转换原理与验证.md')
readme='''原生骨架人工测试版 · 2026-11-03

入口：manager/HD2ModManager.exe。程序需要 .NET 10 Windows Desktop Runtime，本机已安装。
动画构建随附官方 CPython 运行时和源码，无需安装 Python。此包没有 PyInstaller 启动器。

先在管理器设置中选择自己的 Mod 库，并设置游戏 data：
E:\\Steam\\steamapps\\common\\Helldivers 2\\data
在“设置与资产”建立/重建资产索引。

直接测试已生成结果：
1. 导入 test01-模型材质.zip；程序会自动登记 test01 素体，再到护甲映射选择本次测试护甲。
2. 导入 test01-配套动画.zip，与模型一起启用；全部动画补丁都要保留。
3. 关闭其他骨架/动画替换包，一次仅测试此原生骨架角色。
4. 启动游戏，检查待机、走跑、冲刺、蹲伏、趴下、瞄准、换弹、手指、脚底与接缝。
5. 测试后模型和配套动画成套停用。

测试界面转换按钮：
导入 project/source/test01.vpk；打开该 VPK 的详情 → VPK 动作 → 原生骨架转换。
先修改管理器旁的 config.toml，或在该 Mod 根目录放配置（优先级更高）。
工程输出到设置中的默认导出目录/NativeSkeleton；完成后会有模型材质.zip 和配套动画.zip。
native-button.png 仅为使用真实视图渲染的布局示意，示例角色名不是本次替换目标。

已有工程在 project；源 VPK、配置、骨架、模型文件和验证报告均已保存。
配套动画原始数据共约 3.06 GB。若要在工程中展开，将 test01-配套动画.zip 解压到
project/animations/runtime。project/Rebuild-Animations.ps1 可用随附运行时重新构建动画。

验证：七部位，89 根 Source 骨，3,180 动画（187 个附加动画），3,182 个唯一运行时资源。
Python 回归 83 项、C# 骨架相关 15 项、导入/登记/规划回归 50 项通过；已用发布的 CLI
在独立测试库完成模型 ZIP 的规划、校验、导入及七部位素体登记。
骨架名称/父链/bind 已离线核对；权重有 half 量化，动画有时间采样，并非文件逐位无损。
本方案覆盖共享第三人称动画；Source jiggle 动力学、第一人称手臂、游戏 IK 和程序化动作
尚未通过实机验收。当前包是人工测试版，未声称游戏内通过。

反馈时请附动作、装备名称、是否只开这一套，以及错位/拉伸/持枪/脚底的具体现象。
'''
if fixed_target:
    readme=readme.replace(
        '1. 导入 test01-模型材质.zip；程序会自动登记 test01 素体，再到护甲映射选择本次测试护甲。',
        '1. 先停用旧 test01 模型包，再导入新版 test01-模型材质.zip；本包已固定替换 O-3“自由之魂”护甲及头盔，无需再设护甲映射。')
    readme=readme.replace('4. 启动游戏，检查', '4. 启动游戏，穿上 O-3“自由之魂”护甲和同名头盔（健壮/苗条均支持），检查')
    readme += '\nO-3 更新：护甲 f9ced2d898787705，头盔 a2999407862595df。七部位映射到 11 个目标 Unit，另 6 个原版 Unit 隐藏。\n模型 TOC/GPU/stream 与原生来源逐字节一致；材质和配套动画保持原版内容。\nproject/models 保留未指定护甲的原始素体；project/models-o3 是本次固定替换结果。\n旧 ZIP 备份在 backups/before-o3；本次验证见 project/reports/native-o3-audit.json 和 native-o3-import.json。\n'
(release/'先读我-人工测试.txt').write_text(readme,encoding='utf-8-sig')
(project/'Rebuild-Animations.ps1').write_text('''param(
    [string] $GameData = 'E:\\Steam\\steamapps\\common\\Helldivers 2\\data',
    [string] $Output = (Join-Path $PSScriptRoot ('animations-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
)
$manager = Join-Path (Split-Path -Parent $PSScriptRoot) 'manager'
& (Join-Path $manager 'anim_batch_mod\\runtime\\python.exe') -X utf8 (Join-Path $manager 'anim_batch_mod\\main.py') native-project --manifest (Join-Path $PSScriptRoot 'source-skeleton.json') --config (Join-Path $PSScriptRoot 'config.toml') --game-data $GameData --output $Output
exit $LASTEXITCODE
''',encoding='utf-8-sig')

def archive(directory, name, prefix=''):
    destination=release/name
    staging=destination.with_name(destination.name+'.pending') if refresh else destination
    with zipfile.ZipFile(staging,'x',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        for file in sorted(directory.rglob('*')):
            if not file.is_file() or '__pycache__' in file.parts or file.suffix in ('.pdb','.pyc'):
                continue
            z.write(file, prefix+file.relative_to(directory).as_posix())
    with zipfile.ZipFile(staging) as z:
        assert z.testzip() is None, name
        files=len(z.infolist())
    if refresh:
        staging.replace(destination)
    result=dict(path=name,bytes=destination.stat().st_size,files=files,
                sha256=hashlib.file_digest(destination.open('rb'),'sha256').hexdigest(),crc='PASS')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def animation_archive():
    name='test01-配套动画.zip'
    if not refresh:
        return archive(animations/'runtime',name)
    previous=json.loads((release/'package-report.json').read_text(encoding='utf-8'))
    entry=next(item for item in previous['packages'] if item['path']==name)
    destination=release/name
    with destination.open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==entry['sha256'], 'Animation ZIP changed'
    # Re-read every member against the completed build report; no recompression.
    expected={item['path'].removeprefix('runtime/'):item for item in report['files']}
    with zipfile.ZipFile(destination) as z:
        assert set(z.namelist())==set(expected) and len(z.infolist())==len(expected)
        for member in z.infolist():
            item=expected[member.filename]
            assert member.file_size==item['bytes']
            with z.open(member) as stream:
                assert hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256'], member.filename
    print('Existing full animation ZIP verified against build report',flush=True)
    return entry

packages=[archive(model_root,'test01-模型材质.zip'),
          animation_archive(),
          archive(project,'test01-源工程.zip','project/'),
          archive(release/'manager','HD2ModManager-原生骨架测试版.zip','manager/')]
(release/'package-report.json').write_text(json.dumps(dict(status='complete',gameTested=False,replacementTarget=fixed_target,packages=packages),
    ensure_ascii=False,indent=2),encoding='utf-8')
print('PACKAGING COMPLETE',flush=True)
