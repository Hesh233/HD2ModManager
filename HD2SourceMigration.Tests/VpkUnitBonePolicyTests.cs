using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceMigration.Retarget;
using HD2SourceMigration.VpkConversion;
using HD2SourceModel;

namespace HD2SourceMigration.Tests;

public sealed class VpkUnitBonePolicyTests
{
	private static UnitTransformInfo Bind(float x) => new(0, 0, 0,
		[new UnitLocalTransform([1,0,0,0,1,0,0,0,1], [x,0,0], [1,1,1], 0)],
		[new UnitTransformMatrix([1,0,0,0,0,1,0,0,0,0,1,0,x,0,0,1])],
		[new UnitTransformEntry(1,0)], [Hd2NameHash.Of("root")]);
	private static RetargetExtraBone Extra(string name, int parent, float x) =>
		new(name, Hd2NameHash.Of(name), parent, new Vec3(x,0,0));
	private static RetargetedMesh Mesh(string bone) => new(
		[new RetargetedVertex(Vec3.Zero, Vec3.Zero, 0, 0, [new RetargetedInfluence(Hd2NameHash.Of(bone),1)])], []);

	[Theory]
	[InlineData(true)]
	[InlineData(false)]
	public void LocalSingleAndNativeReturnExactAuthoritativeBindWithoutSubset(bool single)
	{
		var avatar = Bind(0);
		var extras = new[] { Extra("used",0,8), Extra("unused",0,9) };
		var authoritative = UnitTransformInfoAppender.Append(Bind(7),extras)!;
		var originalHashes = authoritative.NameHashes.ToArray();
		var originalMatrices = authoritative.Matrices.Select(m=>m.Values.ToArray()).ToArray();
		var originalLocals = authoritative.LocalTransforms.ToArray();
		var result = VpkUnitBonePolicy.ForUnit(avatar,extras,authoritative,Mesh("used"),
			single ? authoritative : null, single ? null : authoritative, out var selection);
		Assert.Same(authoritative,result);
		Assert.Null(selection);
		Assert.Equal(originalHashes,result.NameHashes);
		Assert.Equal(originalLocals,result.LocalTransforms);
		for(var i=0;i<originalMatrices.Length;i++) Assert.Equal(originalMatrices[i],result.Matrices[i].Values);
		Assert.Contains(Hd2NameHash.Of("unused"),result.NameHashes);
		Assert.Equal(7f,result.Matrices[0].Values[12]);
	}

	[Fact]
	public void DirectSubsetKeepsWeightedAncestorsAndDropsOnlyUnusedExtras()
	{
		var avatar=Bind(0);
		var extras=new[] { Extra("parent",0,1),Extra("child",1,2),Extra("unused",0,3) };
		var full=UnitTransformInfoAppender.Append(avatar,extras)!;
		var result=VpkUnitBonePolicy.ForUnit(avatar,extras,full,Mesh("child"),null,null,out var selection);
		Assert.NotNull(selection);
		Assert.Equal(1,selection.Dropped);
		Assert.Equal(new[]{Hd2NameHash.Of("root"),Hd2NameHash.Of("parent"),Hd2NameHash.Of("child")},result.NameHashes);
		Assert.Equal(1,result.Entries[2].ParentIndex);
		Assert.Equal(full.Matrices[2].Values,result.Matrices[2].Values);
		UnitTransformInfoAppender.AssertLocalAndWorldAgree(result);
	}

	[Fact]
	public void MaterialOnlySharedBindRemainsNullAndHasNoImplicitAvatarRead()
	{
		Assert.Null(UnitTransformInfoAppender.Append(null,[]));
	}
}
