-- Model-specific attachment entry; uses the same B23 implementation as the test package.
-- Physics stays in physbone_runtime.lua. Calibration is generated from this model's
-- converter skeleton; old L4D2 weapon-bone positions are never a grip target.
local M = { VERSION = '1.0.19' }
function M.install(engine, options)
    assert(type(options)=='table' and type(options.profile)=='table', 'attachment_profile_required')
    assert(options.transfer and options.transfer.VERSION==M.VERSION, 'attachment_runtime_version_mismatch')
    assert(type(options.profile.attachments)=='table' and (#options.profile.attachments>0 or options.profile.optionSwitches), 'attachment_plan_required')
    return options.transfer.new(engine, options.profile, options.logger, options.armMath, options.sceneContext)
end
return M
