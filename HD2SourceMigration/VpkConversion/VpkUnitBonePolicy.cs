using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceMigration.Retarget;

namespace HD2SourceMigration.VpkConversion;

/// <summary>Per-unit subset is exclusive to direct conversion. Local binds are never rebuilt from the avatar.</summary>
public static class VpkUnitBonePolicy
{
	public static UnitTransformInfo ForUnit(UnitTransformInfo? avatar, IReadOnlyList<RetargetExtraBone>? extras,
		UnitTransformInfo full, RetargetedMesh mesh, UnitTransformInfo? singleBind, UnitTransformInfo? nativeBind,
		out ExtraBoneSelection? selection)
	{
		selection = null;
		if (singleBind is not null) return singleBind;
		if (nativeBind is not null) return nativeBind;
		if (extras is not { Count: > 0 }) return full;
		var baseCount = avatar?.Matrices.Count ?? 0;
		selection = ExtraBoneSubset.Select(extras, baseCount, mesh);
		var result = UnitTransformInfoAppender.Append(avatar, selection.Extras)
			?? throw new InvalidDataException("A direct Unit conversion requires an avatar bind.");
		UnitTransformInfoAppender.AssertLocalAndWorldAgree(result, baseCount);
		return result;
	}
}
