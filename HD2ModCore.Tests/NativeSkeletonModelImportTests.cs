using System.Buffers.Binary;
using System.IO.Compression;
using System.Text.Json;
using HD2ModCore.Application;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class NativeSkeletonModelImportTests : IDisposable
{
	private readonly string root = Path.Combine(Path.GetTempPath(), "hd2-native-import", Guid.NewGuid().ToString("N"));
	private readonly StoragePaths paths;
	private readonly RuntimeArmorRegistryService registry;
	private readonly JsonModLibraryStore store;
	private static readonly RuntimeArmorRegistryModel Model = new("native-test", null,
		[new(3, "1122334455667788", 0, 0)], "Native character");

	public NativeSkeletonModelImportTests()
	{
		paths = new StoragePaths(Path.Combine(root, "app"));
		registry = new RuntimeArmorRegistryService(paths, Path.Combine(root, "external-registry"));
		store = new JsonModLibraryStore(paths);
	}

	private ModLibraryImporter Importer(IModLibraryStore? targetStore = null) => new(paths,
		new ObjectTreeImporter(new PatchFileNameParser()),
		new ArchiveObjectTreeImporter(new ObjectTreeImporter(new PatchFileNameParser())), targetStore ?? store);

	private string Source(RuntimeArmorRegistryModel? model = null, ulong unit = 0x1122334455667788)
	{
		var source = Path.Combine(root, "source", "character");
		Directory.CreateDirectory(source);
		File.WriteAllText(Path.Combine(source, "source-skeleton.json"), "{\"version\":1,\"bones\":[{\"name\":\"pelvis\"}]}");
		File.WriteAllText(Path.Combine(source, "custom-model.json"), JsonSerializer.Serialize(model ?? Model, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
		var toc = new byte[141];
		BinaryPrimitives.WriteUInt32LittleEndian(toc, 4026531857);
		BinaryPrimitives.WriteUInt32LittleEndian(toc.AsSpan(8), 1);
		BinaryPrimitives.WriteUInt64LittleEndian(toc.AsSpan(60), unit);
		BinaryPrimitives.WriteUInt64LittleEndian(toc.AsSpan(68), 0xe0a48d0be9a7453f);
		BinaryPrimitives.WriteUInt64LittleEndian(toc.AsSpan(76), 140);
		BinaryPrimitives.WriteUInt32LittleEndian(toc.AsSpan(116), 1);
		File.WriteAllBytes(Path.Combine(source, "9ba626afa44a3aa3.patch_5"), toc);
		return source;
	}

	[Fact]
	public async Task ImportZip_RegistersNativeModelAndPreservesSidecarOwnership()
	{
		var source = Source();
		var zip = Path.Combine(root, "model.zip");
		ZipFile.CreateFromDirectory(Path.GetDirectoryName(source)!, zip);
		var result = await Importer().ImportArchiveAsync(zip);
		var document = await registry.ReadWorkspaceDocumentOrEmptyAsync();
		Assert.Equal(Model.Key, Assert.Single(document.ModelDefinitions).Key);
		Assert.Empty(document.Mappings);
		Assert.False(document.Enabled);
		var owner = Assert.Single(result.Snapshot.Nodes.Values,
			node => VpkCustomModelFile.TryReadKey(Path.Combine(paths.ModsDirectory, node.RelativePath)) == Model.Key);
		Assert.True(File.Exists(Path.Combine(paths.ModsDirectory, owner.RelativePath, "9ba626afa44a3aa3.patch_0")));
	}

	[Fact]
	public async Task NativeZipPlan_IsStableAcrossTemporaryExtractions()
	{
		var source = Source();
		var zip = Path.Combine(root, "model.zip");
		ZipFile.CreateFromDirectory(Path.GetDirectoryName(source)!, zip);
		var planner = new ModImportPlanner(new ObjectTreeImporter(new PatchFileNameParser()),
			new ArchiveObjectTreeImporter(new ObjectTreeImporter(new PatchFileNameParser())));
		var first = await planner.PlanArchiveAsync(zip);
		var second = await planner.PlanArchiveAsync(zip);
		Assert.Equal(JsonSerializer.Serialize(first), JsonSerializer.Serialize(second));
		Assert.Equal("model-character", Assert.Single(first.Items).DisplayName);
	}

	[Fact]
	public async Task Reimport_PreservesModelsNamesMappingsAndSettings()
	{
		var other = new RuntimeArmorRegistryModel("existing", 42);
		var original = new RuntimeArmorRegistryDocument(7, true, [new(10, ModelKey: other.Key)], [other],
			[new(42, 3, "8877665544332211", 0, 0)], [new(10, false)], "existing_only");
		await registry.SaveWorkspaceAsync(original);
		var source = Source();
		await Importer().ImportFolderAsync(source);
		var merged = await registry.ReadWorkspaceDocumentOrEmptyAsync();
		Assert.Equal(2, merged.ModelDefinitions.Count);
		Assert.Equal(original.Mappings, merged.Mappings);
		Assert.Equal(original.PieceOverrideDefinitions, merged.PieceOverrideDefinitions);
		Assert.Equal(original.TargetModeDefinitions, merged.TargetModeDefinitions);
		Assert.Equal(original.CompositionMode, merged.CompositionMode);
		Assert.Equal(7, merged.Revision);
		Assert.True(merged.Enabled);
		var before = File.ReadAllBytes(registry.WorkspacePath);
		Source(Model with { Name = "Different package label" });
		await Importer().ImportFolderAsync(source);
		Assert.Equal(before, File.ReadAllBytes(registry.WorkspacePath));
	}

	[Fact]
	public async Task ConflictingKey_FailsWithoutChangingLibraryOrRegistry()
	{
		var source = Source();
		await Importer().ImportFolderAsync(source);
		var before = File.ReadAllBytes(registry.WorkspacePath);
		var libraryBefore = File.ReadAllBytes(paths.LibraryPath);
		Source(Model with { Pieces = [new(3, "8877665544332211", 0, 0)] }, 0x8877665544332211);
		var error = await Assert.ThrowsAsync<InvalidDataException>(() => Importer().ImportFolderAsync(source).AsTask());
		Assert.Contains("件表不同", error.Message);
		Assert.Equal(before, File.ReadAllBytes(registry.WorkspacePath));
		Assert.Equal(libraryBefore, File.ReadAllBytes(paths.LibraryPath));
		Assert.Single(Directory.EnumerateDirectories(paths.ModsDirectory), path => Path.GetFileName(path) != ".hd2modmanager");
	}

	[Fact]
	public async Task MissingUnit_RejectsDefinitionWithoutRegistering()
	{
		var error = await Assert.ThrowsAsync<InvalidDataException>(() => Importer().ImportFolderAsync(Source(unit: 9)).AsTask());
		Assert.Contains("不在该 Mod", error.Message);
		Assert.False(File.Exists(registry.WorkspacePath));
		Assert.Null(await store.TryLoadAsync());
	}

	[Fact]
	public async Task OrdinaryCustomModel_WithoutNativeManifestIsUnaffected()
	{
		var source = Source();
		File.Delete(Path.Combine(source, "source-skeleton.json"));
		await Importer().ImportFolderAsync(source);
		Assert.False(File.Exists(registry.WorkspacePath));
	}

	[Fact]
	public async Task LibrarySaveFailure_DoesNotRegisterModel()
	{
		var failing = new InterceptingStore(store, beforeSave: () => throw new IOException("save failed"));
		await Assert.ThrowsAsync<IOException>(() => Importer(failing).ImportFolderAsync(Source()).AsTask());
		Assert.False(File.Exists(registry.WorkspacePath));
		Assert.Null(await store.TryLoadAsync());
	}

	[Fact]
	public async Task RegistrySaveFailure_RollsBackImportedLibraryNodesAndFiles()
	{
		var failing = new InterceptingStore(store, afterSave: () => Directory.CreateDirectory(registry.WorkspacePath));
		var error = await Record.ExceptionAsync(() => Importer(failing).ImportFolderAsync(Source()).AsTask());
		Assert.True(error is IOException or UnauthorizedAccessException, error?.ToString());
		Assert.Empty((await store.TryLoadAsync())!.Nodes);
		Assert.DoesNotContain(Directory.EnumerateDirectories(paths.ModsDirectory), path => Path.GetFileName(path) != ".hd2modmanager");
	}

	[NativePackageFact]
	public async Task RealModelZip_RegistersAllSevenUnits()
	{
		var result = await Importer().ImportArchiveAsync(Environment.GetEnvironmentVariable("HD2_NATIVE_TEST_MODEL_ZIP")!);
		var model = Assert.Single(await registry.ReadWorkspaceModelsAsync());
		Assert.Equal(7, model.Pieces!.Select(piece => piece.Unit).Distinct().Count());
		Assert.Equal(new uint[] { 0, 2, 3, 4, 5, 6, 7 }, model.Pieces!.Select(piece => piece.Slot).Distinct().Order().ToArray());
		Assert.Contains(result.Snapshot.Nodes.Values, node =>
			VpkCustomModelFile.TryReadKey(Path.Combine(paths.ModsDirectory, node.RelativePath)) == model.Key);
	}

	private sealed class InterceptingStore(IModLibraryStore inner, Action? beforeSave = null, Action? afterSave = null) : IModLibraryStore
	{
		public ValueTask<LibrarySnapshot?> TryLoadAsync(CancellationToken cancellationToken = default) => inner.TryLoadAsync(cancellationToken);
		public async ValueTask SaveAsync(LibrarySnapshot snapshot, CancellationToken cancellationToken = default)
		{
			beforeSave?.Invoke();
			await inner.SaveAsync(snapshot, cancellationToken);
			afterSave?.Invoke();
		}
	}

	public void Dispose()
	{
		if (!Directory.Exists(root)) return;
		foreach (var path in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
			File.SetAttributes(path, FileAttributes.Normal);
		Directory.Delete(root, recursive: true);
	}
}

public sealed class NativePackageFactAttribute : FactAttribute
{
	public NativePackageFactAttribute()
	{
		if (!File.Exists(Environment.GetEnvironmentVariable("HD2_NATIVE_TEST_MODEL_ZIP")))
			Skip = "Set HD2_NATIVE_TEST_MODEL_ZIP to run the real native model package audit.";
	}
}
