using System.Buffers.Binary;
using HD2SourceMigration.VpkConversion;

namespace HD2SourceMigration.Tests;

public sealed class SerializedCullingBoundsTests
{
    [Fact]
    public void RecomputedBoundsAreWrittenAtTheRelocatedMeshHeader()
    {
        var bytes=Enumerable.Repeat((byte)0xa5,256).ToArray();
        var bounds=new float[]{-.2f,-.3f,0,.4f,.5f,1.8f,2};
        UnitAuthor.WriteSerializedCullingBounds(bytes,128,bounds);
        for(var i=0;i<7;i++)Assert.Equal(bounds[i],BinaryPrimitives.ReadSingleLittleEndian(bytes.AsSpan(136+i*4,4)));
        Assert.All(bytes.Take(136),b=>Assert.Equal(0xa5,b));
        Assert.All(bytes.Skip(164),b=>Assert.Equal(0xa5,b));
    }

    [Fact]
    public void InvalidBoundsAreRejectedBeforeWriting()
    {
        Assert.Throws<ArgumentException>(()=>UnitAuthor.WriteSerializedCullingBounds(new byte[256],0,new float[6]));
        Assert.Throws<ArgumentException>(()=>UnitAuthor.WriteSerializedCullingBounds(new byte[256],0,[0,0,0,1,1,1,float.NaN]));
    }
}
