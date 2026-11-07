using HD2SourceModel;
using HD2SourceMigration.Retarget;
using HD2SourceMigration.VpkConversion;

namespace HD2SourceMigration.Tests;

public sealed class SingleVrdIsolationTests
{
    private static string Root()
    {
        var p = new DirectoryInfo(AppContext.BaseDirectory);
        while (p is not null && !File.Exists(Path.Combine(p.FullName,"WpfApp1.sln"))) p=p.Parent;
        return p?.FullName ?? throw new InvalidDataException("Repository fixtures missing");
    }
    [Theory]
    [InlineData("test01_survivor_namvet.mdl")]
    [InlineData("test07_survivor_gambler.mdl")]
    public void MixedPhysicsBatchesHaveUniqueTargetsAndExactSourceParents(string file)
    {
        var source=SourceModelReader.Read(File.ReadAllBytes(Path.Combine(Root(),"outputs/vrd-analysis-20261107/vpk-extract",file)));
        var resolved=source.Bones.ToDictionary(b=>b.Index,_=>0);
        var (extras,targets,drivers)=Retargeter.PlanPhysicsExtras(source.Bones,resolved,114,_=>Vec3.Zero);
        var physics=source.Bones.Where(b=>b.Jiggle is not null || b.QuatInterp is not null).ToArray();
        Assert.Equal(8,drivers.Count); Assert.Equal(physics.Length,extras.Count);
        Assert.Equal(physics.Length,targets.Values.Distinct().Count());
        foreach(var bone in physics)
        {
            var index=targets[bone.Index]; var extra=extras[index-114];
            Assert.Equal(bone.DisplayName,extra.Name);
            Assert.Equal(Hd2NameHash.Of(bone.DisplayName),extra.NameHash);
            Assert.Equal(targets.GetValueOrDefault(bone.ParentIndex,0),extra.ParentIndex);
            Assert.True(extra.ParentIndex<index);
            Assert.Equal(0,extra.AnchorIndex);
        }
        Assert.All(resolved.Values,i=>Assert.Equal(0,i));
        var jiggles=source.Bones.Select(b=>b with { QuatInterp=null }).ToArray();
        var legacyMap=new Dictionary<int,int>(resolved);
        var legacy=Retargeter.PlanJiggleBones(jiggles,legacyMap,114,_=>Vec3.Zero);
        var (combined,_,none)=Retargeter.PlanPhysicsExtras(jiggles,resolved,114,_=>Vec3.Zero);
        Assert.Empty(none); Assert.Equal(legacy,combined);
    }
    [Fact]
    public void LegacyDriverJsonAndConstructorRemainCompatible()
    {
        var fact=new SourceQuatInterpDriverFact(0,"driver","hips","head",Vec3.Zero,[],Quat.Identity,Quat.Identity);
        var json=System.Text.Json.JsonSerializer.Serialize(fact);
        Assert.DoesNotContain("RuntimeControlBind",json);
        var copy=System.Text.Json.JsonSerializer.Deserialize<SourceQuatInterpDriverFact>(json)!;
        Assert.Equal(fact.BoneName,copy.BoneName);Assert.Null(copy.RuntimeControlBind);
    }
    [Fact]
    public void NativeSidecarCannotOptIntoSingleV3EvenWithInheritedCalibration()
    {
        var fact=new SourceQuatInterpDriverFact(0,"driver","hips","head",Vec3.Zero,[],Quat.Identity,Quat.Identity,Quat.Identity);
        var native=Assert.Single(PhysBoneDriverRigSidecar.ForNativeSkeleton([fact],1));
        Assert.Null(native.RuntimeControlBind);
        Assert.Throws<InvalidDataException>(()=>PhysBoneDriverRigSidecar.ForSingleSkeleton([native],1));
    }
    [Fact]
    public void SingleDriverCalibrationUsesFinalAxesAndCanonicalControlBind()
    {
        var (_,rig)=TestRig.MatchingRigs(); var parent=rig.Find("hips")!; var control=rig.Find("head")!;
        var old=rig.Bones.ToDictionary(b=>b.Index,_=>Mat4.Identity);
        var final=new Dictionary<int,Mat4>(old);
        final[parent.Index]=new Mat4(0,-1,0,0,1,0,0,0,0,0,1,0,0,0,0,1);
        var fact=new SourceQuatInterpDriverFact(0,"driver","hips","head",Vec3.Zero,[],Quat.Identity,Quat.Identity);
        var f=Assert.Single(SingleHd2Skeleton.FinalizeDriverFrames([fact],rig,old,final));
        var expected=new float[]{0,0,-MathF.Sqrt(.5f),MathF.Sqrt(.5f)};
        Assert.True(Math.Abs(Quat.Dot(expected,f.FrameConjugation))>0.99999);
        Assert.True(Math.Abs(Quat.Dot(expected,f.RuntimeControlBind!))>0.99999);
        Assert.Null(fact.RuntimeControlBind);
        var legacy=PhysBoneDriverRig.Serialize([fact]);
        Assert.Equal(2u,BitConverter.ToUInt32(legacy,8)); Assert.Equal(28u,BitConverter.ToUInt32(legacy,24));
        var single=PhysBoneDriverRig.Serialize([f],PhysBoneDriverRig.SingleVersion);
        Assert.Equal(3u,BitConverter.ToUInt32(single,8)); Assert.Equal(44u,BitConverter.ToUInt32(single,24));
        for(var k=0;k<4;k++) Assert.Equal(f.RuntimeControlBind![k],BitConverter.ToSingle(single,32+28+4*k));
        Assert.Throws<InvalidDataException>(()=>PhysBoneDriverRig.Serialize([fact],PhysBoneDriverRig.SingleVersion));
    }
}
