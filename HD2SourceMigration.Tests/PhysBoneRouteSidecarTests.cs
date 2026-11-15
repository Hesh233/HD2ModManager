using HD2SourceMigration.VpkConversion;

namespace HD2SourceMigration.Tests;

public sealed class PhysBoneRouteSidecarTests
{
	[Theory]
	[InlineData(false, "direct-v1")]
	[InlineData(true, "skeleton-v1")]
	public void WritesExplicitRouteWithoutBomAndReadsBoundedContentLayer(bool skeleton, string expected)
	{
		var root=Path.Combine(Path.GetTempPath(),"hd2-physics-route-"+Guid.NewGuid());
		try
		{
			var path=PhysBoneRouteSidecar.Write(Path.Combine(root,"vpk2patch"),skeleton);
			Assert.Equal(expected,System.Text.Encoding.UTF8.GetString(File.ReadAllBytes(path)));
			Assert.Equal(expected,PhysBoneRouteSidecar.Read(root));
		}
		finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
	}
	[Fact]
	public void MissingRouteIsLegacyAndBackupFoldersAreNotScanned()
	{
		var root=Path.Combine(Path.GetTempPath(),"hd2-physics-route-"+Guid.NewGuid());
		try
		{
			Assert.Null(PhysBoneRouteSidecar.Read(root));
			PhysBoneRouteSidecar.Write(Path.Combine(root,"backup"),false);
			Assert.Null(PhysBoneRouteSidecar.Read(root));
		}
		finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
	}
	[Fact]
	public void ConflictingOrInvalidRoutesFailBeforeEmbedding()
	{
		var root=Path.Combine(Path.GetTempPath(),"hd2-physics-route-"+Guid.NewGuid());
		try
		{
			PhysBoneRouteSidecar.Write(root,false);
			var path=PhysBoneRouteSidecar.Write(Path.Combine(root,"vpk2patch"),true);
			Assert.Throws<InvalidDataException>(()=>PhysBoneRouteSidecar.Read(root));
			File.WriteAllText(path,"not-a-route");
			Assert.Throws<InvalidDataException>(()=>PhysBoneRouteSidecar.Read(root));
		}
		finally { if(Directory.Exists(root)) Directory.Delete(root,true); }
	}
}
