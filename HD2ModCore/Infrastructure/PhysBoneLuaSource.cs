using System.Reflection;
using System.Text;

namespace HD2ModCore.Infrastructure;

/// <summary>
/// 物理骨骼运行时的 Lua 载荷来源。
///
/// 两个文件都作为嵌入资源随 Core 程序集发布（见 csproj 里的 <c>PhysBone\*.lua</c>），
/// 这样"转换器 / 部署器 / 外置包导出"用的是同一份源码，不存在版本漂移。
/// </summary>
public static class PhysBoneLuaSource
{
	/// <summary>求解器库（纯 Lua，无依赖）。</summary>
	public const string CompatSuffix = "PhysBone.physbone_compat.lua";

	/// <summary>生产入口（发现 / 调度 / 挂卸钩子）。</summary>
	public const string RuntimeSuffix = "PhysBone.physbone_runtime.lua";

	/// <summary>骨骼挂点动态修正运行时（独立功能，与物理运行时互不依赖）。</summary>
	public const string AttachmentFixSuffix = "PhysBone.attachment_fix_runtime.lua";

	public static string LoadCompat() => Read(CompatSuffix);

	public static string LoadRuntime() => Read(RuntimeSuffix);

	public static string LoadAttachmentFix() => Read(AttachmentFixSuffix);

	/// <summary>
	/// 合成**单文件**外置包：把 compat 内联进 runtime，并在末尾自动 install。
	///
	/// 为什么内联而不是两个文件：玩家只要把**一个** .lua 拖进 mod 库就完事，
	/// 不依赖第三方加载器的模块解析规则（不同加载器对 `require` 路径的处理并不一致）。
	/// 代价是两个 Lua 功能各带一份 compat 副本——体积上完全可以接受。
	/// </summary>
	/// <param name="addonId">
	/// 给了就把它写成**第一行**的 <c>-- HD2-Addon: &lt;addonId&gt;</c> 标记。
	/// Boot Mod Loader / Chef Shared Loader / MDL3 都按这个标记识别 addon，
	/// 而且要求它必须是首行——所以这里不能有任何前导空行或 BOM。
	/// </param>
	public static string ComposeStandalonePackage(string? addonId = null, string mode = "external")
	{
		var compat = LoadCompat();
		var runtime = LoadRuntime();
		var builder = new StringBuilder(compat.Length + runtime.Length + 2048);
		if (!string.IsNullOrWhiteSpace(addonId))
		{
			builder.Append("-- HD2-Addon: ").Append(addonId).Append('\n');
		}
		builder.AppendLine("-- HD2 物理骨骼运行时（外置包，单文件）");
		builder.AppendLine("-- 由 HD2 Mod Manager 生成。compat 库已内联，直接放进 mod 库即可。");
		builder.AppendLine("-- 需要游戏里已部署带物理参数的 patch（转换时 embed 过容器）。");
		builder.AppendLine("-- 2026-11-05 拆分：挂点动态修正已独立为 hd2attachmentfix.lua，本包只负责物理。");
		builder.AppendLine();
		builder.AppendLine("local __hd2_loader = ...");
		builder.AppendLine("local __hd2_chef = type(__hd2_loader) == 'table' and __hd2_loader.loader == 'Chef Shared Loader'");
		builder.AppendLine("-- ==== physbone_compat.lua（内联） ====");
		builder.AppendLine("local PhysBoneCompat = (function()");
		builder.AppendLine(compat);
		builder.AppendLine("end)()");
		builder.AppendLine("-- ==== physbone_runtime.lua ====");
		builder.AppendLine("local PhysBoneRuntime = (function()");
		builder.AppendLine(runtime);
		builder.AppendLine("end)()");
		builder.AppendLine();
		builder.AppendLine("-- ==== 自动安装 ====");
		builder.AppendLine("-- 游戏自身的 VM 里 `stingray` 一定存在；外部加载器环境下同样如此。");
		builder.AppendLine("local ok, err = pcall(function()");
		builder.AppendLine("\tlocal engine = rawget(_G, 'stingray')");
		builder.AppendLine("\tif engine == nil then return end");
		builder.Append("\tlocal options = { compat = PhysBoneCompat, mode = '")
			.Append(mode)
			.AppendLine("' }");
		builder.AppendLine("\tif type(__hd2_loader) == 'table' and type(__hd2_loader.log_directory) == 'string' and __hd2_loader.log_directory ~= '' then");
		builder.AppendLine("\t\toptions.logPath = __hd2_loader.log_directory .. '/hd2physbone_compact.log'");
		builder.AppendLine("\tend");
		builder.AppendLine("\tPhysBoneRuntime.install(engine, options)");
		// Chef treats a returned API table as a module and does not infer its global
		// callbacks. Export the installed callback explicitly, only for that contract.
		builder.AppendLine("\tif __hd2_chef then");
		builder.AppendLine("\t\tPhysBoneRuntime.version = PhysBoneRuntime.VERSION");
		builder.AppendLine("\t\tPhysBoneRuntime.render = rawget(_G, 'render')");
		builder.AppendLine("\t\tPhysBoneRuntime.shutdown = PhysBoneRuntime.uninstall");
		builder.AppendLine("\t\tPhysBoneRuntime.on_stop = PhysBoneRuntime.uninstall");
		builder.AppendLine("\tend");
		builder.AppendLine("end)");
		builder.AppendLine("if not ok then");
		builder.AppendLine("\tlocal real = rawget(_G, 'print')");
		builder.AppendLine("\tif type(real) == 'function' then real('[physbone] 安装失败: ' .. tostring(err)) end");
		builder.AppendLine("end");
		builder.AppendLine();
		builder.AppendLine("return PhysBoneRuntime");
		return builder.ToString();
	}

	/// <summary>Compose the shared B23 runtime with a profile compiled from the selected model.</summary>
	public static string ComposeAttachmentFixPackage(string? addonId = null, string? profileSource = null)
	{
		if (string.IsNullOrWhiteSpace(profileSource))
			throw new InvalidOperationException("挂点修正需要该模型生成的 attachment-profile.lua；请重新生成原骨架工程。");
		var old = Read("PhysBone.native_attachments.lua");
		var mathStart = old.IndexOf("local M={VERSION='0.12.1'}", StringComparison.Ordinal);
		var mathEnd = old.IndexOf("-- Source mstudioquatinterpbone_t:", mathStart, StringComparison.Ordinal);
		var compat = LoadCompat();
		var quaternionStart = compat.IndexOf("local function stored9_quaternion(r)", StringComparison.Ordinal);
		var quaternionEnd = compat.IndexOf("local function quaternion_axis_angle(", quaternionStart, StringComparison.Ordinal);
		var math = old[mathStart..mathEnd] + compat[quaternionStart..quaternionEnd]
			+ "\nM.quaternion=function(r)return {stored9_quaternion(r)}end\nM.rotate=rot\nreturn M\n";
		var source = Read("PhysBone.native_grip_transfer_test_entry.lua")
			.Replace("-- INSERT LEGACY ARM MATH", math, StringComparison.Ordinal)
			.Replace("-- INSERT TRANSFER MODULE", Read("PhysBone.native_grip_transfer_test.lua"), StringComparison.Ordinal)
			.Replace("-- INSERT FIRST PERSON GUARD", Read("PhysBone.native_first_person_guard.lua"), StringComparison.Ordinal)
			.Replace("-- INSERT ATTACHMENT ADAPTER", LoadAttachmentFix(), StringComparison.Ordinal)
			.Replace("-- INSERT TRANSFER PROFILE", profileSource, StringComparison.Ordinal);
        source = source.Replace("\r\n", "\n", StringComparison.Ordinal);
        return string.IsNullOrWhiteSpace(addonId) ? source : source.Replace(
			"-- HD2-Addon: mods/hd2modmanager/attachment_fix", "-- HD2-Addon: " + addonId, StringComparison.Ordinal);
	}

	private static string Read(string suffix)
	{
		var assembly = typeof(PhysBoneLuaSource).Assembly;
		var name = assembly.GetManifestResourceNames()
			.SingleOrDefault(candidate => candidate.EndsWith(suffix, StringComparison.Ordinal))
			?? throw new InvalidOperationException($"内置物理运行时资源缺失：{suffix}");
		using var stream = assembly.GetManifestResourceStream(name)
			?? throw new InvalidOperationException($"无法读取内置物理运行时资源：{suffix}");
		using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
		return reader.ReadToEnd();
	}
}
