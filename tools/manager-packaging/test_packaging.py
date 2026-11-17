"""Regression tests for the installed-manager allowlist packager (no GUI/game writes)."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
INSTALL = ROOT / 'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
TEMP = (ROOT / 'tmp').resolve()
STATIC_VERSION = '生成链版本.txt'
SYNC_TOOL_FILES = ['Package-HD2ModManager.bat', 'Package-Manager.ps1', 'package-manifest.json', 'README.md', '项目许可证.txt', STATIC_VERSION]
HELPERS = ['ManagerPackageSupport.dll', 'ManagerPackageSupport.deps.json', 'ManagerPackageSupport.runtimeconfig.json']

class PackagingTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix='manager-package-test-', dir=TEMP)).resolve()
        self.install = self.work / 'manager'
        self.tools = self.install / '非运行文件/打包工具'
        self.tools.mkdir(parents=True)
        (self.tools / '验证记录').mkdir()
        for name in ['Package-Manager.ps1', '项目许可证.txt']:
            shutil.copy2(TOOL / name, self.tools / name)
        for name in HELPERS:
            shutil.copy2(ROOT / 'tools/ManagerPackageSupport/bin/Release/net10.0' / name, self.tools / name)
        for name in ['HD2ModManager.dll', 'HD2ModCore.dll', 'HD2GameItemAssets.dll']:
            shutil.copy2(INSTALL / name, self.install / name)
        for name in ['HD2ModManager.deps.json', 'hd2mod.deps.json']:
            (self.install / name).write_text('{"targets":{}}', encoding='utf-8')
        (self.install / 'anim_batch_mod').mkdir()
        shutil.copy2(INSTALL / 'anim_batch_mod/build-info.json', self.install / 'anim_batch_mod/build-info.json')
        self.manifest = json.loads((TOOL / 'package-manifest.json').read_text(encoding='utf-8-sig'))
        installed_info = json.loads((self.install / 'anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'))
        self.manifest['physicsRuntimeVersion'] = installed_info['physicsRuntimeVersion']
        self.manifest['physicsCompatVersion'] = installed_info['physicsCompatVersion']
        self.manifest['full'] = self.manifest['startup'] = ['HD2ModManager.dll', 'HD2ModCore.dll', 'HD2GameItemAssets.dll']
        self.write_manifest()

    def tearDown(self):
        # Never recursively delete an unchecked computed path.
        self.assertEqual(self.work.parent, TEMP)
        self.assertTrue(self.work.name.startswith('manager-package-test-'))
        shutil.rmtree(self.work)

    def write_manifest(self):
        (self.tools / 'package-manifest.json').write_text(json.dumps(self.manifest, ensure_ascii=False), encoding='utf-8')

    def run_package(self, *args, ok=True):
        self.write_manifest()
        result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(self.tools / 'Package-Manager.ps1'), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=90)
        self.assertEqual(result.returncode == 0, ok, result.stdout)
        return result

    def zips(self):
        return list((self.install / '非运行文件/打包输出').glob('*.zip'))

    def run_sync(self, *args, script=None, ok=True, include_static=True):
        result = subprocess.run(['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(script or TOOL / 'Sync-ManagerPackaging.ps1'), '-InstallationRoot', str(self.install),
                                 *(['-IncludeStaticSupport'] if include_static else []), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=90)
        self.assertEqual(result.returncode == 0, ok, result.stdout)
        return result

    def tree_snapshot(self):
        return {p.relative_to(self.install).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.install.rglob('*') if p.is_file()}

    def test_full_static_version_has_a_declared_source(self):
        manifest = json.loads((TOOL / 'package-manifest.json').read_text(encoding='utf-8-sig'))
        self.assertIn(STATIC_VERSION, manifest['full'])
        self.assertNotIn(STATIC_VERSION, manifest['startup'])
        self.assertTrue((TOOL / STATIC_VERSION).is_file())
        project = (ROOT / 'HD2ModManager/HD2ModManager.csproj').read_text(encoding='utf-8-sig')
        self.assertIn('manager-packaging\\' + STATIC_VERSION, project)

    def test_static_sync_dry_run_writes_nothing(self):
        before = self.tree_snapshot()
        result = self.run_sync()
        self.assertIn(STATIC_VERSION, result.stdout)
        self.assertEqual(self.tree_snapshot(), before)
        self.assertFalse((self.install / STATIC_VERSION).exists())

    def test_static_sync_fills_missing_files_and_preserves_user_data(self):
        protected = ['config.toml', 'config/attachment-fix.json', 'anim_batch_mod/config.toml',
                     'settings.json', 'test-library/RuntimeCompanions/model-profile.json']
        for name in protected:
            p = self.install / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('custom-user-value:' + name).encode('utf-8'))
        before = {p: value for p, value in self.tree_snapshot().items()
                  if p != '非运行文件/打包工具/package-manifest.json'}
        self.run_sync('-Apply')
        self.assertEqual((self.install / STATIC_VERSION).read_bytes(), (TOOL / STATIC_VERSION).read_bytes())
        self.assertEqual((self.tools / 'README.md').read_bytes(), (TOOL / 'README.md').read_bytes())
        after = self.tree_snapshot()
        self.assertEqual({p: after[p] for p in before}, before)
        second = self.run_sync('-Apply')
        self.assertNotIn('"Action":  "Copy"', second.stdout)
        self.assertEqual(self.tree_snapshot(), after)

    def test_static_sync_backs_up_stale_file_then_is_idempotent(self):
        stale = b'old static version metadata\r\n'
        (self.install / STATIC_VERSION).write_bytes(stale)
        records = self.tools / '验证记录'
        records.mkdir(exist_ok=True)
        self.run_sync('-Apply')
        old_hash = hashlib.sha256(stale).hexdigest().upper()
        backup = records / (STATIC_VERSION + '.before-' + old_hash[:16])
        self.assertEqual(backup.read_bytes(), stale)
        self.assertEqual((self.install / STATIC_VERSION).read_bytes(), (TOOL / STATIC_VERSION).read_bytes())
        before = self.tree_snapshot()
        self.run_sync('-Apply')
        self.assertEqual(self.tree_snapshot(), before)

    def test_missing_static_source_fails_before_any_copy(self):
        # A disjoint source fixture avoids deleting/renaming the real source file.
        source_tool = self.work / 'source/tools/manager-packaging'
        source_tool.mkdir(parents=True)
        for name in SYNC_TOOL_FILES + ['Sync-ManagerPackaging.ps1']:
            if name != STATIC_VERSION:
                shutil.copy2(TOOL / name, source_tool / name)
        built = self.work / 'source/tools/ManagerPackageSupport/bin/Release/net10.0'
        built.mkdir(parents=True)
        for name in HELPERS:
            shutil.copy2(self.tools / name, built / name)
        before = self.tree_snapshot()
        self.run_sync('-Apply', script=source_tool / 'Sync-ManagerPackaging.ps1', ok=False)
        self.assertEqual(self.tree_snapshot(), before)

    def test_static_destination_directory_fails_before_any_copy(self):
        (self.install / STATIC_VERSION).mkdir()
        before = self.tree_snapshot()
        self.run_sync('-Apply', ok=False)
        self.assertEqual(self.tree_snapshot(), before)

    def test_missing_backup_directory_fails_before_any_copy(self):
        (self.tools / '验证记录').rmdir()  # Known empty directory in this isolated fixture.
        before = self.tree_snapshot()
        self.run_sync('-Apply', ok=False)
        self.assertEqual(self.tree_snapshot(), before)

    def test_full_package_contains_static_support_byte_exact(self):
        self.run_sync('-Apply')
        self.manifest['full'].append(STATIC_VERSION)
        self.run_package()
        with zipfile.ZipFile(self.zips()[0]) as z:
            self.assertEqual(z.read('HD2ModManager/' + STATIC_VERSION), (TOOL / STATIC_VERSION).read_bytes())
            self.assertIsNone(z.testzip())

    def test_full_allowlists_the_model_b3_generator_but_not_model_test_zips(self):
        manifest = json.loads((TOOL/'package-manifest.json').read_text(encoding='utf-8-sig'))
        self.assertIn('anim_batch_mod/runtime_companions.py', manifest['full'])
        self.assertNotIn('anim_batch_mod/runtime_companions.py', manifest['startup'])
        self.assertFalse(any('test06' in name or 'grip-b3-options' in name for name in manifest['full']))

    def test_incomplete_b3_bundle_cannot_ship_a_claimed_b3_python_compiler(self):
        # Reference build-info exists, but this fixture omits the matching B3 compiler/policy/calibration dependencies.
        self.manifest['full'].append('anim_batch_mod/runtime_companions.py')
        (self.install/'anim_batch_mod/runtime_companions.py').write_text("VERSION='1.0.18'\n", encoding='utf-8')
        self.run_package('-CheckOnly', ok=False)
        self.assertFalse(self.zips())

    def test_full_has_one_root_deployable_production_physics_zip(self):
        before = {n: hashlib.sha256((self.install / n).read_bytes()).hexdigest() for n in self.manifest['full']}
        self.run_package()
        self.assertEqual(len(self.zips()), 1)
        outer = self.zips()[0]
        with zipfile.ZipFile(outer) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(len(z.namelist()), 7)
            self.assertFalse(any('test06' in n or '测试包' in n for n in z.namelist()))
            artifact = z.read('HD2ModManager/运行时配套/物理运行时.zip')
            with zipfile.ZipFile(io.BytesIO(artifact)) as physics:
                self.assertIsNone(physics.testzip())
                patch = '9ba626afa44a3aa3.patch_0'
                self.assertEqual(set(physics.namelist()), {'manifest.json', patch, patch + '.stream', patch + '.gpu_resources'})
                m = json.loads(physics.read('manifest.json'))
                self.assertEqual(m['Guid'], '7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01')
                self.assertEqual(m['Name'], 'HD2 物理骨骼运行时')
        report = json.loads(Path(str(outer) + '.manifest.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(report['generatedArtifactCount'], 1)
        self.assertEqual(report['payloadCount'], 3)
        proof = report['productionArtifacts'][0]['provenance']
        self.assertEqual(proof['runtimeVersion'], self.manifest['physicsRuntimeVersion'])
        self.assertEqual(proof['compatVersion'], self.manifest['physicsCompatVersion'])
        self.assertEqual(proof['zipSha256'], hashlib.sha256(artifact).hexdigest())
        self.assertEqual(before, {n: hashlib.sha256((self.install / n).read_bytes()).hexdigest() for n in before})
        self.assertFalse(list((self.install / '非运行文件/打包输出').glob('.physics-*')))

    def test_check_only_writes_nothing(self):
        self.run_package('-CheckOnly')
        self.assertFalse((self.install / '非运行文件/打包输出').exists())

    def test_startup_excludes_physics_and_needs_no_helper(self):
        (self.tools / HELPERS[0]).unlink()
        self.run_package('-Mode', 'Startup')
        with zipfile.ZipFile(self.zips()[0]) as z:
            self.assertEqual(len(z.namelist()), 6)
            self.assertFalse(any('物理运行时.zip' in n for n in z.namelist()))

    def test_missing_production_artifact_fails_closed(self):
        self.manifest.pop('productionArtifacts')
        self.run_package('-CheckOnly', ok=False)
        self.assertFalse(self.zips())

    def test_test_artifact_owner_refused(self):
        self.manifest['productionArtifacts'][0]['addonId'] = 'mods/hd2modmanager/test06'
        self.run_package('-CheckOnly', ok=False)

    def test_duplicate_generated_path_refused(self):
        self.manifest['full'].append('运行时配套/物理运行时.zip')
        p = self.install / '运行时配套/物理运行时.zip'; p.parent.mkdir(); p.write_bytes(b'not physics')
        self.run_package('-CheckOnly', ok=False)

    def test_unsafe_paths_refused(self):
        for path in ['../outside.dll', 'C:/Windows/win.ini', 'test-library/secret.json', '非运行文件/测试包/test06.zip']:
            with self.subTest(path=path):
                self.manifest['full'] = ['HD2ModManager.dll', path]
                self.run_package('-CheckOnly', ok=False)
        self.assertFalse(self.zips())

    def test_missing_helper_fails_before_publication(self):
        (self.tools / HELPERS[0]).unlink()
        self.run_package(ok=False)
        self.assertFalse(self.zips())

    def test_companion_dependency_must_also_be_shipped(self):
        self.manifest['full'] = ['HD2ModManager.dll', 'HD2ModCore.dll']
        self.run_package(ok=False)
        self.assertFalse(self.zips())

    def test_invalid_installed_core_fails_before_publication(self):
        (self.install / 'HD2ModCore.dll').write_bytes(b'not a managed assembly')
        self.run_package(ok=False)
        self.assertFalse(self.zips())

    def test_license_is_required(self):
        (self.tools / '项目许可证.txt').unlink()
        self.run_package('-CheckOnly', ok=False)

    def test_duplicate_payload_refused(self):
        self.manifest['full'].append('HD2ModManager.dll')
        self.run_package('-CheckOnly', ok=False)

    def test_legacy_schema_cannot_silently_omit_physics(self):
        self.manifest['schema'] = 1
        self.run_package('-CheckOnly', ok=False)


    def test_stale_manifest_version_fails_full_and_startup_with_actual_version(self):
        actual = self.manifest['managerVersion']
        self.manifest['managerVersion'] = '1.5.15'
        for mode in ['Full', 'Startup']:
            result = self.run_package('-Mode', mode, '-CheckOnly', ok=False)
            self.assertIn('manifest=1.5.15', result.stdout)
            self.assertIn('installed GUI=' + actual, result.stdout)
        self.assertFalse(self.zips())

    def test_default_sync_preserves_existing_generation_description(self):
        custom = b'preserve this installation backend and later user metadata\r\n'
        (self.install / STATIC_VERSION).write_bytes(custom)
        self.run_sync('-Apply', include_static=False)
        self.assertEqual((self.install / STATIC_VERSION).read_bytes(), custom)
        self.assertTrue((self.install / 'Package-HD2ModManager.bat').is_file())
        before = self.tree_snapshot()
        self.run_sync('-Apply', include_static=False)
        self.assertEqual(self.tree_snapshot(), before)

    def test_sync_binds_current_gui_version_not_old_template_version(self):
        source_tool = self.work / 'source/tools/manager-packaging'
        source_tool.mkdir(parents=True)
        for name in SYNC_TOOL_FILES + ['Sync-ManagerPackaging.ps1']:
            shutil.copy2(TOOL / name, source_tool / name)
        template = json.loads((source_tool / 'package-manifest.json').read_text(encoding='utf-8-sig'))
        template['managerVersion'] = '1.5.15'
        (source_tool / 'package-manifest.json').write_text(json.dumps(template), encoding='utf-8')
        built = self.work / 'source/tools/ManagerPackageSupport/bin/Release/net10.0'
        built.mkdir(parents=True)
        for name in HELPERS:
            shutil.copy2(self.tools / name, built / name)
        self.run_sync('-Apply', script=source_tool / 'Sync-ManagerPackaging.ps1', include_static=False)
        generated = json.loads((self.tools / 'package-manifest.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(generated['managerVersion'], self.manifest['managerVersion'])

    def test_sync_does_not_assign_new_direct_backend_to_old_install(self):
        # This is an explicit legacy-metadata fixture, independent of whichever
        # newer backend the real manager installation currently carries.
        path = self.install / 'anim_batch_mod/build-info.json'
        metadata = json.loads(path.read_text(encoding='utf-8-sig'))
        for key in list(metadata):
            if key.startswith(('directPhysics', 'skeletonRepair')) or key in ['physicsRouteVersion', 'physicsRoutingPolicy', 'physicsSourceFiles']:
                del metadata[key]
        metadata['physicsRuntimeVersion'] = '2.3.6'
        metadata['physicsCompatVersion'] = '1.3.6'
        path.write_text(json.dumps(metadata), encoding='utf-8')
        self.run_sync('-Apply', include_static=False)
        generated = json.loads((self.tools / 'package-manifest.json').read_text(encoding='utf-8-sig'))
        self.assertNotIn('physicsRoutingPolicy', generated)
        self.assertNotIn('directPhysicsRuntimeVersion', generated)
        self.assertEqual(generated['physicsRuntimeVersion'], '2.3.6')

    def test_sync_uses_installation_declared_backend_fields(self):
        path = self.install / 'anim_batch_mod/build-info.json'
        metadata = json.loads(path.read_text(encoding='utf-8-sig'))
        metadata.update(directPhysicsRuntimeVersion='2.1.45', directPhysicsCompatVersion='1.0.0',
                        physicsRouteVersion='1.0.0', physicsRoutingPolicy='explicit-route-legacy-local-v1', physicsSourceFiles=[])
        path.write_text(json.dumps(metadata), encoding='utf-8')
        before = path.read_bytes()
        self.run_sync('-Apply', include_static=False)
        generated = json.loads((self.tools / 'package-manifest.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(generated['physicsRoutingPolicy'], metadata['physicsRoutingPolicy'])
        self.assertEqual(generated['directPhysicsRuntimeVersion'], metadata['directPhysicsRuntimeVersion'])
        self.assertEqual(path.read_bytes(), before)

    def test_stale_build_info_prevents_sync_before_any_copy(self):
        path = self.install / 'anim_batch_mod/build-info.json'
        metadata = json.loads(path.read_text(encoding='utf-8-sig')); metadata['managerVersion'] = '1.5.15'
        path.write_text(json.dumps(metadata), encoding='utf-8')
        before = self.tree_snapshot()
        self.run_sync('-Apply', include_static=False, ok=False)
        self.assertEqual(self.tree_snapshot(), before)

    def test_explicit_backup_root_works_without_installation_backup_folder(self):
        (self.tools / '验证记录').rmdir()
        backup = self.work / 'separate backups'; backup.mkdir()
        original = (self.tools / 'package-manifest.json').read_bytes()
        self.run_sync('-Apply', '-BackupRoot', str(backup), include_static=False)
        self.assertFalse((self.tools / '验证记录').exists())
        self.assertTrue(any(p.read_bytes() == original for p in backup.iterdir()))

    def test_bat_launcher_handles_unrelated_cwd_unicode_spaces_and_bang(self):
        other = self.work / '管理器 空间!'; shutil.copytree(self.install, other)
        bat = other / 'Package-HD2ModManager.bat'; shutil.copy2(TOOL / bat.name, bat)
        env = dict(os.environ, HD2_PACKAGE_NO_PAUSE='1')
        result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(bat), '-CheckOnly'],
                                cwd=self.work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding='utf-8', errors='replace', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('No ZIP has been written', result.stdout)
        self.assertFalse((other / '非运行文件/打包输出').exists())

    def test_bat_missing_tool_propagates_error_without_pause(self):
        other = self.work / 'launcher only'; other.mkdir()
        bat = other / 'Package-HD2ModManager.bat'; shutil.copy2(TOOL / bat.name, bat)
        env = dict(os.environ, HD2_PACKAGE_NO_PAUSE='1')
        result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', str(bat)], cwd=self.work, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('Packaging tools are missing', result.stdout)

    def test_explicit_output_keeps_zip_and_private_workspace_outside_installation(self):
        before = {p: h for p, (h, _) in self.tree_snapshot().items()}
        output = self.work / '独立 打包输出'
        self.run_package('-OutputDirectory', str(output))
        self.assertFalse((self.install / '非运行文件/打包输出').exists())
        self.assertEqual(len(list(output.glob('*.zip'))), 1)
        self.assertFalse(list(output.glob('.physics-*')))
        self.assertEqual(before, {p: h for p, (h, _) in self.tree_snapshot().items()})
        report = json.loads(Path(str(next(output.glob('*.zip'))) + '.manifest.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(report['managerVersion'], self.manifest['managerVersion'])
        self.assertEqual(report['buildFlavor'], 'skeleton-test')

    def test_check_only_does_not_create_explicit_output_directory(self):
        output = self.work / 'unused output'
        self.run_package('-CheckOnly', '-OutputDirectory', str(output))
        self.assertFalse(output.exists())

    def test_actual_runtime_version_mismatch_refused(self):
        self.manifest['physicsRuntimeVersion'] = '99.0.0'
        self.assertIn('Installed physics version differs', self.run_package('-CheckOnly', ok=False).stdout)

    def test_actual_compat_version_mismatch_refused(self):
        self.manifest['physicsCompatVersion'] = '99.0.0'
        self.assertIn('Installed physics version differs', self.run_package('-CheckOnly', ok=False).stdout)

    def test_legacy_physics_cannot_be_relabeled_as_repair_build(self):
        path = self.install / 'anim_batch_mod/build-info.json'
        info = json.loads(path.read_text(encoding='utf-8-sig'))
        info['skeletonRepairPhysicsRuntimeVersion'] = '99.0.0'
        info['skeletonRepairPhysicsCompatVersion'] = self.manifest['physicsCompatVersion']
        path.write_text(json.dumps(info), encoding='utf-8')
        self.assertIn('explicit A21 physics source binding', self.run_package('-CheckOnly', ok=False).stdout)

    def test_stale_repair_revision_refused(self):
        self.manifest['skeletonRepairVersion'] = '99.0'
        self.assertIn('Skeleton repair version differs', self.run_package('-CheckOnly', ok=False).stdout)

if __name__ == '__main__':
    unittest.main(verbosity=2)
