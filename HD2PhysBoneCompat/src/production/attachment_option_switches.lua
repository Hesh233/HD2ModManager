-- Standard manifest option markers are independent Chef modules, not duplicate runtimes.
local M={SCHEMA='hd2-grip-switches-v1'}
function M.resolve(profile,lookup)
 assert(profile.optionSwitches and profile.optionSwitches.schema==M.SCHEMA,'switch_schema')
 local state={schema=M.SCHEMA,fpArms=false,bones={},selected={},invalid={},activeBoneCount=0}
 for _,spec in ipairs(profile.optionSwitches.specs)do
  local ok,value=pcall(lookup,spec.owner)
  local valid=ok and type(value)=='table' and value.schema==M.SCHEMA and value.key==spec.key and value.enabled==true
  if not ok or (value~=nil and not valid)then state.invalid[#state.invalid+1]=spec.key end
  -- attachment-fix.enabled is the TP gate, not a hidden dependency of the FP option.
  local present=valid and (spec.key=='fp_arms' or profile.optionSwitches.enabled~=false)
  if spec.key=='fp_arms'then state.fpArms=present
  else state.bones[spec.bone]=present;if present then state.activeBoneCount=state.activeBoneCount+1 end end
  state.selected[#state.selected+1]={key=spec.key,enabled=present,owner=spec.owner}
 end
 return state
end
function M.apply(profile,state)
 assert(state.schema==M.SCHEMA,'switch_state_schema')
 local filtered={};local skipped={}
 for _,row in ipairs(profile.attachments or {})do if state.bones[row.node.name]then filtered[#filtered+1]=row else skipped[#skipped+1]=row end end
 profile.attachments=filtered;profile.attachmentPassthroughParents={}
 for _,row in ipairs(skipped)do profile.attachmentPassthroughParents[row.node.index]=row.node end
 profile.rightAttachmentEnabled=state.bones.attach_hand_r==true
 if profile.rightGrip then profile.rightGrip.enabled=profile.rightAttachmentEnabled end
 assert(profile.leftGrip,'left_grip_profile_required')
 profile.leftGrip.enabled=state.bones.attach_hand_l==true
 profile.attachmentSwitchState=state
 profile.allAttachmentBonesOff=state.activeBoneCount==0
 profile.firstPersonSource.runtimeEnabled=state.fpArms
 profile.firstPersonSource.hiddenOnly=not state.fpArms
 local names={};for _,bone in ipairs(profile.optionSwitches.bones)do if state.bones[bone]then names[#names+1]=bone end end
 profile.attachmentFixSettings.bones=names
 -- FP total switch is independent of TP hand-bone switches; FP solver keeps its accepted inputs.
 return profile
end
return M
