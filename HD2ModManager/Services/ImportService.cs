using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;
using HD2ModCore.Application;
using HD2ModManager.ViewModels;

namespace HD2ModManager.Services
{
    // 作用：将 UI 导入请求转交给 HD2ModCore，并补充 manager 层标签/图片元数据。
    public class ImportService
    {
        private static readonly HashSet<string> ArchiveExtensions = new(StringComparer.OrdinalIgnoreCase) { ".zip", ".rar", ".7z" };
        private readonly ModLibraryService _library;
        private readonly Action<string>? _onInfo;
        private readonly Action<string>? _onError;
        private readonly Action<string, double?>? _onProgress;
        private readonly StoragePaths _paths;
        private readonly HD2ModCore.Application.IModInformationCenter _informationCenter;

        // The most recent import's complete content-impact set (new and overwritten nodes).
        // Batch orchestration uses this to schedule derived data once after all file commits.
        public IReadOnlyList<ModNodeId> LastAffectedNodeIds { get; private set; } = Array.Empty<ModNodeId>();
		public bool LastImportHasOptionPathConflicts { get; private set; }

        /// <summary>
        /// 这次导入如果是 VPK 来源，这里就是转换报告（每个 VPK 转了/跳过了/为什么）。
        /// <c>null</c> 表示这次导入与 VPK 无关。
        /// </summary>
        public VpkImportReport? LastVpkImportReport { get; private set; }

        public ImportService(ModLibraryService library, Action<string>? onInfo = null, Action<string>? onError = null, IModInformationCenter? informationCenter = null, Action<string, double?>? onProgress = null)
        {
            _library = library;
            _onInfo = onInfo;
            _onError = onError;
            _onProgress = onProgress;
            _paths = SettingsService.CreateStoragePaths();
            _informationCenter = informationCenter ?? throw new ArgumentNullException(nameof(informationCenter), "ImportService requires the shared IModInformationCenter.");
        }

        public Task EnqueueImportsAsync(IEnumerable<string> paths, CancellationToken ct = default)
        {
            return ImportSequentiallyAsync(paths, ct);
        }

        private async Task ImportSequentiallyAsync(IEnumerable<string> paths, CancellationToken ct)
        {
            foreach (var path in paths)
            {
                ct.ThrowIfCancellationRequested();
                await ImportPathAsync(path, ct).ConfigureAwait(false);
            }
        }

        public async Task<List<string>> ImportPathAsync(
            string path,
            CancellationToken ct,
            bool notifyLibraryChanged = true,
            bool refreshDerivedData = true,
            bool allowVpkConversion = true)
        {
            // VPK 来源走自己的路：一个 VPK = 一个 Mod 文件夹，文件夹里的 vpk2patch/ 放实际生效的 patch。
            // 判定失败（不是 VPK 来源）就原样往下走，行为与以前完全一致。
            //
            // 转换产出的目录必须传 allowVpkConversion: false：它根上有来源 VPK 原件，
            // 不挡住就会"产出目录 → 再当来源转换 → 又产出"，永远建不出 Mod。
            if (allowVpkConversion)
            {
                var vpkSource = await TryPrepareVpkSourceAsync(path, ct).ConfigureAwait(false);
                if (vpkSource is not null)
                    return await ImportVpkSourceAsync(vpkSource, ct, notifyLibraryChanged, refreshDerivedData).ConfigureAwait(false);
            }

            try
            {
				UiPerformanceDiagnostics.RecordBurst(
					"Import.Path",
					$"source={Path.GetFileName(path)}; kind={(Directory.Exists(path) ? "folder" : "file")}",
					threshold: 8);
				using var totalPerf = UiPerformanceDiagnostics.Measure(
					"Import.Path",
					thresholdMilliseconds: 100,
					details: () => $"source={Path.GetFileName(path)}; notify={notifyLibraryChanged}; refreshDerived={refreshDerivedData}");
				var importer = CoreServices.CreateModLibraryImporter(_paths, _informationCenter, _library.InformationReader);
                var before = _library.Snapshot.Nodes.ToDictionary(pair => pair.Key, pair => pair.Value);
                ImportResult result;
                using (UiPerformanceDiagnostics.Measure(
					"Import.ScanAndStore",
					thresholdMilliseconds: 100,
					details: () => $"source={Path.GetFileName(path)}; archive={File.Exists(path) && ArchiveExtensions.Contains(Path.GetExtension(path))}"))
                {
                    if (Directory.Exists(path))
					{
						result = await importer.ImportFolderAsync(path, ct).ConfigureAwait(false);
					}
					else if (File.Exists(path) && ArchiveExtensions.Contains(Path.GetExtension(path)))
					{
						result = await importer.ImportArchiveAsync(path, ct).ConfigureAwait(false);
					}
					else if (File.Exists(path))
					{
						var dir = Path.GetDirectoryName(path) ?? throw new DirectoryNotFoundException(path);
						result = await importer.ImportFolderAsync(dir, ct).ConfigureAwait(false);
					}
					else
					{
						throw new FileNotFoundException("Import source not found.", path);
					}
                }

				List<string> importedGuids;
				ModNodeId[] affectedNodeIds;
				using (UiPerformanceDiagnostics.Measure(
					"Import.CommitSnapshot",
					thresholdMilliseconds: 50,
					details: () => $"source={Path.GetFileName(path)}; nodes={result.Snapshot.Nodes.Count}"))
				{
					_library.ReplaceSnapshot(result.Snapshot, buildDerivedData: false);
					importedGuids = _library.Snapshot.Nodes.Values
						.Where(node => !before.ContainsKey(node.Id))
						.Select(node => node.Id.Value.ToString("N"))
						.ToList();
					var changedExistingNodeIds = _library.Snapshot.Nodes.Values
						.Where(node => before.TryGetValue(node.Id, out var previous)
							&& !ModNodeSemanticComparer.AreEqual(previous, node))
						.Select(node => node.Id)
						.ToArray();
					affectedNodeIds = importedGuids
						.Select(guid => Guid.TryParse(guid, out var value) ? new ModNodeId(value) : (ModNodeId?)null)
						.Concat(changedExistingNodeIds.Select(id => (ModNodeId?)id))
						.Where(id => id.HasValue)
						.Select(id => id!.Value)
						.Distinct()
						.ToArray();
					await _library.InitializeDefaultOptionActivationsAsync(
						affectedNodeIds.Select(id => id.Value.ToString("N")),
						// The importer marks only conflicted logical parents. Do not
						// suppress defaults for every unrelated Mod in this batch.
						enableDefaults: true,
						ct).ConfigureAwait(false);
					LastAffectedNodeIds = affectedNodeIds;
					LastImportHasOptionPathConflicts = result.HasOptionPathConflicts;
					foreach (var nodeId in affectedNodeIds)
					{
						await _library.InvalidateContentNodeAsync(nodeId, ct).ConfigureAwait(false);
					}
				}
                if (refreshDerivedData)
                {
					using var derivedPerf = UiPerformanceDiagnostics.Measure(
						"Import.RefreshDerived",
						thresholdMilliseconds: 100,
						details: () => $"source={Path.GetFileName(path)}; affected={affectedNodeIds.Length}");
					await _library.RefreshCommittedContentAsync(
						affectedNodeIds,
						ModContentChangeKind.Changed,
						alreadyInvalidated: true,
						cancellationToken: ct).ConfigureAwait(false);
                }
                if (notifyLibraryChanged) _library.NotifyImportCompleted();
                var identityNote = result.ConflictRemappedNodeIds.Count == 0
                    ? string.Empty
                    : $"；检测到 {result.ConflictRemappedNodeIds.Count} 个 GUID 冲突，已生成新的库 GUID";
                _onInfo?.Invoke($"Imported {result.SourceDisplayName}{identityNote}");
                return importedGuids.Where(g => _library.Get(g) != null).ToList();
            }
            catch (Exception ex)
            {
                _onError?.Invoke(ex.Message);
                throw;
            }
        }

        /// <summary>
        /// 这个来源里有没有 VPK。有就摊开到临时目录并返回；没有返回 <c>null</c>。
        /// <para>
        /// 注意：<b>不能</b>只看扩展名。用户的包通常是"一个压缩包，里面 8 个模型 VPK + 一堆材质 VPK"，
        /// 所以压缩包要先看一眼目录区（<c>7z l</c>，不解压）。
        /// </para>
        /// </summary>
        private async Task<VpkImportSource?> TryPrepareVpkSourceAsync(string path, CancellationToken ct)
        {
            try
            {
                var service = new VpkImportService(_paths, SettingsService.GetGameDataFolder());
                return await service.TryPrepareAsync(path, ct, stage => _onProgress?.Invoke(stage, null)).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception exception) when (exception is IOException or InvalidDataException or UnauthorizedAccessException)
            {
                // 摊不开就当普通来源处理：原来的导入路径会给出更贴合的错误。
                _onError?.Invoke(exception.Message);
                return null;
            }
        }

        private async Task<List<string>> ImportVpkSourceAsync(
            VpkImportSource source,
            CancellationToken ct,
            bool notifyLibraryChanged,
            bool refreshDerivedData)
        {
            try
            {
                var service = new VpkImportService(_paths, SettingsService.GetGameDataFolder());
                // 进度：CLI 报的是"这一批里的第几个包"与"这个包里第几个材质/Unit"两层计数，
                // 合成一个百分比只能在知道队列总数之后做——所以 queue 那一条要记下来当分母。
                var queueTotal = 0;
                var queueDone = 0;
                var (report, produced) = await service
                    .ConvertAsync(
                        source,
                        stage =>
                        {
                            _onInfo?.Invoke(stage);
                            _onProgress?.Invoke(stage, null);
                        },
                        ct,
                        (phase, done, total, text) =>
                        {
                            if (phase == "queue")
                            {
                                queueTotal = total;
                                queueDone = done;
                                _onProgress?.Invoke(text, total == 0 ? null : (double)done / total);
                                return;
                            }

                            var innerFraction = total == 0 ? 0.0 : (double)done / total;
                            _onProgress?.Invoke(
                                text,
                                queueTotal == 0 ? null : (queueDone + innerFraction) / queueTotal);
                        }, ModelScalePrompt.ShowAsync, VpkModelDecisionPrompt.ShowAsync)
                    .ConfigureAwait(false);
                LastVpkImportReport = report;
                _onInfo?.Invoke(report.ToSummary());
                LogService.Info(report.ToDetail());

                if (produced.Count == 0)
                {
                    if (notifyLibraryChanged) _library.NotifyImportCompleted();
                    return new List<string>();
                }

                // 每个 VPK 一个文件夹，逐个走常规导入。派生数据在整批之后再算一次，
                // 否则每个 VPK 都要重算一遍全库内容事实。
                var guids = new List<string>();
                // guid → 它属于哪个主体组、是主体还是材质包（挂选项关系时要用）。
                var groupOf = new Dictionary<string, VpkProducedPackage>(StringComparer.OrdinalIgnoreCase);
                var affected = new List<ModNodeId>();
                var conflicts = false;
                foreach (var package in produced)
                {
                    ct.ThrowIfCancellationRequested();

                    // **同一来源再来一次 = 更新那个 Mod。** 不新建节点、不换名字、不动顺序与启停，
                    // 素体 key 与 unit id 由 `--reuse-model` 逐位沿用（见 VpkImportService）。
                    if (package.IsUpdate && package.UpdateTargetDirectory is { } updateTarget)
                    {
                        var updated = await SwapIntoExistingModAsync(package, updateTarget, ct).ConfigureAwait(false);
                        if (updated is { } updatedGuid)
                        {
                            guids.Add(updatedGuid);
                            groupOf[updatedGuid] = package;
                            if (_library.Get(updatedGuid) is { } node) affected.Add(new ModNodeId(Guid.Parse(node.Guid)));
                            continue;
                        }

                        // 换不进去就退回"新建一个"：产物是好的，用户至少能用上。
                        _onInfo?.Invoke($"{package.UpdateTargetName}：没能更新原有 Mod（原因见上一条），改为新建一个。");
                    }

                    var imported = await ImportPathAsync(
                        package.Directory,
                        ct,
                        notifyLibraryChanged: false,
                        refreshDerivedData: false,
                        // 这是转换产出，不是待转换的来源：见 ImportPathAsync 里的说明。
                        allowVpkConversion: false).ConfigureAwait(false);
                    guids.AddRange(imported);
                    foreach (var guid in imported) groupOf[guid] = package;
                    affected.AddRange(LastAffectedNodeIds);
                    conflicts |= LastImportHasOptionPathConflicts;

                    // **不自动换甲。** 转换产物是"新 Unit id 的自定义素体"，它本来就该以
                    // 自定义素体模式存在：用户在护甲映射页把它挂到某件护甲上（或者到详情页
                    // 主动选一个目标）才算"要用它替换谁"。
                    //
                    // 以前这里会立刻换到 CLI 的缺省目标（RE-2310），后果是：用户装完一个 VPK
                    // 模组，发现自己的荣誉卫队被顶掉了，而他从没做过这个决定；想换回自定义素体
                    // 又会在换甲链路里撞上"把 Unit 搬到它自己身上"。默认不动，是更安全的语义。
                    foreach (var guid in imported)
                        LogVpkCustomModelImported(guid);
                }

                // 「原比例」路线的后半程：模型已入库，先问要不要替换哪件甲（候选与详情页下拉同源），
                // 再按意愿全量构建骨架动画并作为 [原比例动画] Mod 入库。
                // 动画失败/取消 → 整批回滚本批导入的 Mod（用户定的策略：不留半套原比例产物）。
                var nativePackages = produced
                    .Where(package => package.NativeModelDirectory is not null)
                    .ToArray();
                if (nativePackages.Length != 0)
                {
                    try
                    {
                        foreach (var package in nativePackages)
                        {
                            ct.ThrowIfCancellationRequested();
                            // ⚠️ **不能拿库目录去比暂存目录。** `NativeModelDirectory` 是暂存
                            // （`StagingRoot/pkg/...`），入库后节点在 `ModsDirectory` 下、名字还可能
                            // 被去重改过（`CreateUniqueDirectoryName`）。旧实现直接比全路径，
                            // 于是永远不相等 ⇒ 换甲询问与骨架动画**整段被静默跳过**，用户看到的
                            // 就是"选了要生成动画，但没有任何进度"。
                            //
                            // 现在按"这一批里属于这个产物的 GUID"找，再用 `sections.json`
                            // 挑出真正的模型主体（同目录也可能有材质节点）。
                            var modelGuid = FindNativeModelGuid(guids, groupOf, package);
                            var modDirectory = modelGuid is null ? null : TryGetModDirectory(modelGuid);
                            if (modDirectory is null) continue;   // 这个主体转换失败，没入库，跳过

                            await PromptAndApplyTargetArmorAsync(modelGuid!, modDirectory, ct)
                                .ConfigureAwait(false);

                            // 挂点对调（2026-11-05）：选择「制作原骨架护甲」后，同时产出
                            // [骨骼挂点修正] 独立 lua 包并作为独立 Mod 入库（与 [原比例动画]
                            // 同一套命名/回滚语义）。它对应的是原骨架模型本身，不依赖是否
                            // 生成骨架动画。配置与 Avatar/Bones 补丁按本模型生成，复用 B23 运行时。
                            var modelBaseName = Path.GetFileName(modDirectory);
                            var gripFixName = VpkImportService.NativeGripFixPrefix
                                + (modelBaseName.StartsWith(VpkImportService.NativeModelPrefix, StringComparison.Ordinal)
                                    ? modelBaseName[VpkImportService.NativeModelPrefix.Length..]
                                    : modelBaseName);
                            var gripFixRoot = Path.Combine(Path.GetTempPath(),
                                "hd2gripx-" + Guid.NewGuid().ToString("N")[..8]);
                            Directory.CreateDirectory(gripFixRoot);
                            var gripFixExported = await VpkAnimationBuildService.BuildAttachmentFixAsync(
                                modDirectory, gripFixRoot, ct).ConfigureAwait(false);
                            var gripFixPackageDirectory = Path.Combine(gripFixRoot, gripFixName);
                            Directory.Move(Path.Combine(gripFixExported, "patch版"), gripFixPackageDirectory);
                            RewriteLuaPackageIdentity(gripFixPackageDirectory, gripFixName);
                            var gripFixGuids = await ImportPathAsync(
                                gripFixPackageDirectory,
                                ct,
                                notifyLibraryChanged: false,
                                refreshDerivedData: false,
                                allowVpkConversion: false).ConfigureAwait(false);
                            guids.AddRange(gripFixGuids);
                            affected.AddRange(LastAffectedNodeIds);
                            conflicts |= LastImportHasOptionPathConflicts;
                            VpkImportService.DeleteQuietly(gripFixRoot);
                            LogService.Info($"骨骼挂点修正包「{gripFixName}」已作为独立 Mod 导入"
                                + "（包含本模型的 Lua 与配套骨架；头部子节点保留原生行为）。");

                            if (!package.WantsNativeAnimation) continue;
                            _onProgress?.Invoke($"正在为 {Path.GetFileName(modDirectory)} 生成原比例骨架动画", null);
                            var animationRuntime = await VpkAnimationBuildService.BuildAsync(
                                modDirectory,
                                Path.Combine(Path.GetTempPath(),
                                    "hd2anim-" + Guid.NewGuid().ToString("N")[..8], "runtime"),
                                (phase, done, total, text) =>
                                    _onProgress?.Invoke(text, total == 0 ? null : (double)done / total),
                                ct).ConfigureAwait(false);
                            var animationPackageDirectory = Path.Combine(
                                Path.GetDirectoryName(animationRuntime)!, "package");
                            Directory.CreateDirectory(animationPackageDirectory);
                            foreach (var file in Directory.EnumerateFiles(animationRuntime))
                                File.Copy(file, Path.Combine(animationPackageDirectory, Path.GetFileName(file)), overwrite: true);
                            var animationName = VpkImportService.NativeAnimationPrefix
                                + (modelBaseName.StartsWith(VpkImportService.NativeModelPrefix, StringComparison.Ordinal)
                                    ? modelBaseName[VpkImportService.NativeModelPrefix.Length..]
                                    : modelBaseName);
                            var animationGuids = await ImportPathAsync(
                                animationPackageDirectory,
                                ct,
                                notifyLibraryChanged: false,
                                refreshDerivedData: false,
                                allowVpkConversion: false).ConfigureAwait(false);
                            guids.AddRange(animationGuids);
                            affected.AddRange(LastAffectedNodeIds);
                            conflicts |= LastImportHasOptionPathConflicts;
                            VpkImportService.DeleteQuietly(Path.GetDirectoryName(Path.GetDirectoryName(animationRuntime)!)!);
                            LogService.Info($"骨架动画「{animationName}」已作为独立 Mod 导入，与 {modelBaseName} 成套启用/停用。");
                        }
                    }
                    catch (OperationCanceledException)
                    {
                        RollbackVpkBatch(guids);
                        throw;
                    }
                    catch (Exception exception) when (exception is IOException or InvalidOperationException
                        or InvalidDataException or UnauthorizedAccessException or JsonException)
                    {
                        RollbackVpkBatch(guids);
                        throw new InvalidOperationException(
                            $"骨架动画生成失败，本批 VPK 导入的 Mod 已全部回滚：{exception.Message}", exception);
                    }
                }

                LastAffectedNodeIds = affected.Distinct().ToArray();
                LastImportHasOptionPathConflicts = conflicts;

                // 同批的"模型 + 它的材质包"自动接成 主体 → 选项：用户现在要导入完之后在库里
                // 把材质包一个个拖到模型下面，而同一批转换出来的东西本来就知道谁是谁的。
                // **物理结构不变**（还是平铺的一个个文件夹），改的只是 option.json 的父子关系。
                var attach = await AttachVpkBatchOptionsAsync(guids, groupOf, ct).ConfigureAwait(false);
                if (attach.Relationships > 0)
                {
                    var message = attach.Hosts == 1
                        ? $"已把 {attach.Materials} 个材质包设为同批模型的选项。"
                        : $"已把 {attach.Materials} 个材质包挂到 {attach.Hosts} 个模型主体的选项下。";
                    _onInfo?.Invoke(message);
                    LogService.Info(message);
                }

                if (attach.Failures > 0)
                {
                    LogService.Warn($"有 {attach.Failures} 个模型主体没能建立选项关系（产物本身没问题，可在库里手动拖）。");
                }

                if (refreshDerivedData && LastAffectedNodeIds.Count != 0)
                {
                    await _library.RefreshCommittedContentAsync(
                        LastAffectedNodeIds,
                        ModContentChangeKind.Changed,
                        alreadyInvalidated: true,
                        cancellationToken: ct).ConfigureAwait(false);
                }

                if (notifyLibraryChanged) _library.NotifyImportCompleted();
                return guids.Where(guid => _library.Get(guid) != null).ToList();
            }
            finally
            {
                source.Dispose();
            }
        }

        /// <summary>一次"把同批材质包挂成选项"的结果。<c>Relationships</c> = 实际新建的关系条数。</summary>
        private readonly record struct VpkOptionAttachResult(int Hosts, int Materials, int Relationships, int Failures);

        /// <summary>
        /// 把新产物换进**库里已有的**那个 Mod，返回它的 guid（换不进去返回 <c>null</c>）。
        /// <para>
        /// <b>为什么要走这条路而不是"删了重建"。</b>删了重建会换掉节点 id、名字、在配置里的位置、
        /// 启停状态与它的选项关系；素体还会多出一具（unit id 变了，旧映射全部指向不存在的 unit）。
        /// 而用户重新导入同一个包时想要的只是"产物换成新的"。
        /// </para>
        /// <para>
        /// <b>只换产物，不碰用户的改动</b>：<c>Overwrite/</c>、<c>wardrobe.json</c>、
        /// <c>custom-model.json</c>、<c>components.json</c> 全部原样保留
        /// （见 <see cref="VpkPayloadSwap.PreservedFileNames"/>）。
        /// </para>
        /// </summary>
        private async Task<string?> SwapIntoExistingModAsync(
            VpkProducedPackage package,
            string modDirectory,
            CancellationToken cancellationToken)
        {
            try
            {
                var payload = Path.Combine(modDirectory, ModNodePayloadLayout.VpkPatchDirectoryName);
                var backupRoot = Path.Combine(
                    _paths.ModsDirectory,
                    ".hd2modmanager-swap-backups",
                    Path.GetFileName(modDirectory) + "-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss", System.Globalization.CultureInfo.InvariantCulture));
                var swap = VpkPayloadSwap.Swap(payload, package.Directory, backupRoot);
                if (!swap.Succeeded)
                {
                    _onError?.Invoke(swap.Error ?? "替换 vpk2patch/ 失败。");
                    return null;
                }

                // 报告必须一起换：管理器显示的材质/贴图/警告全来自它，只换载荷会让界面停在旧数字。
                if (!string.IsNullOrWhiteSpace(package.ReportJson))
                {
                    var reportPath = VpkConversionReport.GetPath(modDirectory);
                    var restoreReadOnly = VpkPayloadSwap.ClearReadOnlyForWrite(reportPath);
                    try
                    {
                        await File.WriteAllTextAsync(reportPath, package.ReportJson, cancellationToken).ConfigureAwait(false);
                    }
                    catch (UnauthorizedAccessException exception)
                    {
                        // 报告写不进去不算更新失败：产物是新的，只是界面上的计数与警告会旧一层。
                        _onError?.Invoke($"`vpk2patch.json` 写不进去（{exception.Message}）：产物已换成新的，"
                            + "但界面上的材质/贴图计数与警告仍是上一次的。");
                    }
                    finally
                    {
                        if (restoreReadOnly) VpkPayloadSwap.MarkReadOnly(reportPath);
                    }
                }

                // 物理参数：**必须在换完之后、在真正的 Mod 目录上做**。
                //
                // `physbone embed-mod` 要靠目录里那份来源 .vpk 才找得到 jiggle 骨；
                // 在暂存目录上跑只会得到"没有物理参数"，然后把用户原来那套参数覆盖成空。
                //
                // ⚠️ 顺序：**先嵌参数，再把只读补回去**。反过来的话这一步要写
                // `.gpu_resources`，而那些文件刚被标成只读 —— 得到的是一句
                // "Access to the path … is denied"，一个字都没提只读。
                var physBone = await VpkPhysBoneEmbedder.TryRunAsync(modDirectory, cancellationToken).ConfigureAwait(false);
                if (physBone is not null) _onInfo?.Invoke($"{package.UpdateTargetName}：{physBone}");

                // 这条路径后面没有写入步骤了，把库的只读保护补回去。
                if (swap.RestoreReadOnly) VpkPayloadSwap.SetPayloadReadOnly(payload);

                var relative = Path.GetRelativePath(_paths.ModsDirectory, modDirectory);
                var node = _library.Snapshot.Nodes.Values.FirstOrDefault(candidate =>
                    string.Equals(
                        candidate.RelativePath.TrimEnd(Path.DirectorySeparatorChar),
                        relative.TrimEnd(Path.DirectorySeparatorChar),
                        StringComparison.OrdinalIgnoreCase));
                if (node is null)
                {
                    _onError?.Invoke($"在库里找不到目录 {relative} 对应的 Mod：产物已换成新的，"
                        + "但界面上的材质/贴图计数可能仍是旧的。下次刷新库时会重新读。");
                    return null;
                }

                if (swap.BackupDirectory is not null)
                    _onInfo?.Invoke($"{package.UpdateTargetName}：旧产物已备份到 {swap.BackupDirectory}。");

                // 内容事实必须失效重读，否则界面还显示上一批的 Unit / 材质 / 贴图。
                await _library.InvalidateContentNodeAsync(node.Id, cancellationToken).ConfigureAwait(false);
                return node.Id.Value.ToString("N");
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException
                or InvalidDataException or InvalidOperationException)
            {
                _onError?.Invoke($"更新原有 Mod 失败：{exception.Message}");
                return null;
            }
        }

        /// <summary>
        /// 把 [骨骼挂点修正] 包的 manifest 改写成"每个模型一份身份"：
        /// Name 用带前缀的包名，Guid 由包名确定性派生——同一模型重复导入会替换旧包，
        /// 不同模型的包互不冲突（目录里的固定 GUID 只是导出功能的身份）。
        /// </summary>
        private static void RewriteLuaPackageIdentity(string packageDirectory, string name)
        {
            var manifestPath = Path.Combine(packageDirectory, "manifest.json");
            var manifest = JsonDocument.Parse(File.ReadAllText(manifestPath));
            using var output = new MemoryStream();
            using (var writer = new Utf8JsonWriter(output, new JsonWriterOptions { Indented = true }))
            {
                writer.WriteStartObject();
                foreach (var property in manifest.RootElement.EnumerateObject())
                {
                    if (property.Name == "Name") continue;
                    if (property.Name == "Guid") continue;
                    property.WriteTo(writer);
                }
                writer.WriteString("Guid", FormatDeterministicGuid(name));
                writer.WriteString("Name", name);
                writer.WriteEndObject();
            }
            File.WriteAllBytes(manifestPath, output.ToArray());
        }

        /// <summary>包名 → 稳定 GUID（MD5 前 16 字节；只用于避免导入冲突，非安全用途）。</summary>
        private static string FormatDeterministicGuid(string name)
        {
            using var md5 = System.Security.Cryptography.MD5.Create();
            var hash = md5.ComputeHash(System.Text.Encoding.UTF8.GetBytes("hd2-gripx:" + name));
            return new Guid(hash).ToString();
        }

        /// <summary>
        /// 导入末尾询问"这个原比例模型替换哪件甲"。候选与 Mod 详情页的护甲下拉同源
        /// （游戏护甲 + 已注册自定义素体），应用走同一个 <see cref="VpkRekeyService"/>。
        /// <para>
        /// <b>失败只记日志、不拦导入。</b>换甲是"装完就能用"的便利步；换不动的产物本身是好的，
        /// 用户可以在详情页重试——那页有完整的状态与警告展示。只有用户明确取消整个导入才向上抛。
        /// </para>
        /// </summary>
        private async Task PromptAndApplyTargetArmorAsync(
            string guid, string modDirectory, CancellationToken ct)
        {
            IReadOnlyList<VpkTargetArmorOption> options;
            try
            {
                var catalog = new EquipmentUnitCatalogService(_paths);
                options = (await catalog.GetEntriesAsync().ConfigureAwait(false))
                    .Where(entry => entry.Category.Equals("Armor", StringComparison.OrdinalIgnoreCase))
                    .GroupBy(entry => entry.ArchiveId, StringComparer.OrdinalIgnoreCase)
                    .Select(group => new VpkTargetArmorOption(group.Key, group.First().DisplayName))
                    .OrderBy(option => option.DisplayName, StringComparer.CurrentCulture)
                    .ToArray();
                try
                {
                    var registry = CoreServices.CreateRuntimeArmorRegistryService(_paths);
                    var customModels = (await registry.ReadCustomModelCatalogAsync().ConfigureAwait(false))
                        .Where(entry => entry.Parts.Count != 0)
                        .Select(entry => new VpkTargetArmorOption(
                            entry.ArchiveId, entry.DisplayName + "（自定义素体）", VpkTargetArmorKind.CustomModel))
                        .OrderBy(option => option.DisplayName, StringComparer.CurrentCulture)
                        .ToArray();
                    options = options.Concat(customModels).ToArray();
                }
                catch (Exception exception) when (exception is IOException or InvalidDataException or InvalidOperationException)
                {
                    // 注册表坏了不能连带把游戏护甲列表一起废掉（与详情页同样的独立降级）。
                    LogService.Warn($"读取已注册自定义素体失败，换甲候选只列游戏护甲：{exception.Message}");
                }
            }
            catch (Exception exception) when (exception is IOException or InvalidDataException or InvalidOperationException)
            {
                LogService.Warn($"读取护甲列表失败，跳过导入末尾的换甲询问：{exception.Message}");
                return;
            }

            // 「跳过」= 保持自定义素体模式（不自动换甲是既有设计）；选了目标才落一次换甲。
            var target = await VpkTargetArmorPrompt.ShowAsync(
                Path.GetFileName(modDirectory), options, null, ct).ConfigureAwait(false);
            if (target is null) return;
            var outcome = await VpkRekeyService
                .RunAsync(guid, modDirectory, new[] { target.ArchiveId }, null,
                    stage => _onProgress?.Invoke(stage, null), ct)
                .ConfigureAwait(false);
            if (!outcome.Ok)
            {
                LogService.Warn($"换到「{target.DisplayName}」失败，可在 Mod 详情页重试：{outcome.Error}");
                return;
            }

            LogService.Info(outcome.RestoredFromSource
                ? $"已退回自定义素体（{target.DisplayName}）。"
                : $"已把「{Path.GetFileName(modDirectory)}」换到 {target.DisplayName}："
                    + $"替换 {outcome.ReplacedUnits} 个 Unit、隐藏 {outcome.HiddenMeshes} 个网格。"
                + (outcome.Warnings.Count != 0 ? " 注意：" + string.Join(" ", outcome.Warnings) : string.Empty));

            var nodeId = new ModNodeId(Guid.Parse(guid));
            await _library.InvalidateContentNodeAsync(nodeId, CancellationToken.None).ConfigureAwait(false);
            await _library.RefreshCommittedContentAsync(
                [nodeId], ModContentChangeKind.Changed, alreadyInvalidated: true,
                cancellationToken: CancellationToken.None).ConfigureAwait(false);
        }

        /// <summary>
        /// 动画失败/取消后的整批回滚：把这次 VPK 导入新建的 Mod 全部移除。
        /// 回滚自身失败只记日志——真正的失败原因已经在往上抛的那条异常里。
        /// </summary>
        private void RollbackVpkBatch(List<string> guids)
        {
            var ids = guids.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            if (ids.Length == 0) return;
            try
            {
                var deletion = _library.RemoveManyAsync(ids, CancellationToken.None)
                    .GetAwaiter().GetResult();
                LogService.Warn($"骨架动画失败，已回滚本批导入的 {deletion.RemovedNodeIds.Count} 个 Mod"
                    + (deletion.HasFailures ? "（部分未能移除，请在库里手动删除）" : "。"));
            }
            catch (Exception exception)
            {
                LogService.Error($"回滚本批 VPK 导入失败，请手动删除相关 Mod：{exception.Message}");
            }
        }

        /// <summary>
        /// 把这一批里的**材质包**挂到同一批的**模型主体**下面当选项。
        /// <para>
        /// <b>按主体分组挂。</b>整合包里几套角色的材质裸名相同（<c>tights_socks.vmt</c> 谁都有），
        /// 把 plum 的材质挂到 chiffon 下面会得到一堆"看起来对、点开什么都不变"的选项。
        /// 所以只把**同一个主体组**里的材质挂给这个主体。
        /// </para>
        /// <para>
        /// <b>判据：</b>转换阶段已经算好了——含 <c>vpk2patch/sections.json</c> 的是模型主体，
        /// 其余是它的材质包（见 <c>VpkImportService.BuildConversionWorkload</c>）。
        /// 没有分组信息的（只导材质包）退回老做法：全部材质挂到唯一的主体下。
        /// </para>
        /// <para>
        /// <b>失败只记日志。</b>这一步是便利，不是导入正确性的一部分：关系写失败时产物照样是好的，
        /// 手动拖一下就能补。
        /// </para>
        /// </summary>
        private async Task<VpkOptionAttachResult> AttachVpkBatchOptionsAsync(
            List<string> guids,
            IReadOnlyDictionary<string, VpkProducedPackage> groupOf,
            CancellationToken cancellationToken)
        {
            var distinct = guids.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            if (distinct.Length < 2) return default;

            // 分组：主体 → 它自己的材质包。分组信息缺失时整批算一组（老行为）。
            var groups = distinct
                .GroupBy(guid => groupOf.TryGetValue(guid, out var package) && package.GroupName is { Length: > 0 }
                    ? package.GroupName
                    : "（整批）", StringComparer.OrdinalIgnoreCase)
                .Select(group => new
                {
                    Hosts = group.Where(guid => !groupOf.TryGetValue(guid, out var package) || package.IsModel).ToArray(),
                    Materials = group.Where(guid => groupOf.TryGetValue(guid, out var package) && !package.IsModel).ToArray(),
                })
                .Where(group => group.Hosts.Length != 0 && group.Materials.Length != 0)
                .ToArray();

            if (groups.Length == 0) return default;

            var relationships = 0;
            var failures = 0;
            var materials = groups.Sum(group => group.Materials.Length);
            var hosts = groups.Sum(group => group.Hosts.Length);
            foreach (var group in groups)
            {
                foreach (var host in group.Hosts)
                {
                    try
                    {
                        var result = await _library.AddOptionsToHostAsync(host, group.Materials, cancellationToken)
                            .ConfigureAwait(false);
                        relationships += result.ChangedNodeIds.Count;
                    }
                    catch (Exception exception) when (exception is ModRelationshipMutationException
                        or InvalidOperationException or IOException or UnauthorizedAccessException)
                    {
                        failures++;
                        LogService.Warn($"没能把同批材质包设为主体「{_library.Get(host)?.Name ?? host}」的选项：{exception.Message}");
                    }
                }
            }

            return new VpkOptionAttachResult(hosts, materials, relationships, failures);
        }

        /// <summary>
        /// 找出某个转换产物（暂存目录）入库后对应的**模型主体** GUID。
        /// <para>
        /// `groupOf` 已经记录了"这个 GUID 来自哪个产物"，所以不需要也不该比较路径。
        /// 同一产物可能导入多个节点（模型 + 同包的材质），用 `vpk2patch/sections.json`
        /// 挑出带 Unit 的那个；都没有时退回第一个候选，交给调用方继续。
        /// </para>
        /// </summary>
        private string? FindNativeModelGuid(
            IReadOnlyList<string> guids,
            IReadOnlyDictionary<string, VpkProducedPackage> groupOf,
            VpkProducedPackage package)
        {
            string? first = null;
            foreach (var guid in guids)
            {
                if (!groupOf.TryGetValue(guid, out var owner) || !ReferenceEquals(owner, package)) continue;
                first ??= guid;
                var directory = TryGetModDirectory(guid);
                if (directory is null) continue;
                if (File.Exists(Path.Combine(directory, ModNodePayloadLayout.VpkPatchDirectoryName, "sections.json")))
                    return guid;
            }
            return first;
        }

        /// <summary>从 Mod 的 GUID 拿到它的目录；拿不到就 <c>null</c>。</summary>
        private string? TryGetModDirectory(string guid)
        {
            if (!Guid.TryParse(guid, out var id)) return null;
            if (!_library.Snapshot.Nodes.TryGetValue(new ModNodeId(id), out var node)) return null;
            return Path.Combine(_paths.ModsDirectory, node.RelativePath);
        }

        /// <summary>
        /// 转换产物的"装完就能用"提示：告诉用户下一步去哪，而不是替他改掉某件护甲。
        /// <para>
        /// 只对<b>含 Unit 的</b>转换产物说这句话（判据是 <c>vpk2patch/sections.json</c>）：
        /// 纯材质包没有 Unit，也就没有"挂到哪件护甲"这回事，对它说这句话只会让人困惑。
        /// </para>
        /// </summary>
        private void LogVpkCustomModelImported(string guid)
        {
            if (!Guid.TryParse(guid, out var id)
                || !_library.Snapshot.Nodes.TryGetValue(new ModNodeId(id), out var node))
                return;
            var modDirectory = Path.Combine(_paths.ModsDirectory, node.RelativePath);
            if (!File.Exists(Path.Combine(modDirectory, ModNodePayloadLayout.VpkPatchDirectoryName, "sections.json")))
                return;

            LogService.Info($"VPK 转换产物「{node.Metadata.Name}」已作为自定义素体导入（未替换任何原版护甲）。"
                + "要让它生效，请在护甲映射页把它挂到某件护甲上，或到 Mod 详情页选择目标护甲。");
        }

    }
}
