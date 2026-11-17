namespace HD2ModManager.ViewModels;

/// <summary>下拉里的一个目标。<c>ArchiveId</c> 是这一套装备要替换的全部归档（护甲 + 头盔），或者自定义素体的伪 id。</summary>
public enum VpkTargetArmorKind
{
	/// <summary>游戏里真实存在的护甲归档（按 setId 会再补上配套头盔）。</summary>
	GameArmor = 0,

	/// <summary>护甲映射页里注册的自定义素体：<c>custom-model:&lt;key&gt;</c>，没有游戏归档。</summary>
	CustomModel = 1,
}

public sealed record VpkTargetArmorOption(
	string ArchiveId,
	string DisplayName,
	VpkTargetArmorKind Kind = VpkTargetArmorKind.GameArmor)
{
	public override string ToString() => DisplayName;
}

