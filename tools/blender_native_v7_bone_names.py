"""Run in Blender's Text Editor. Default: inspect only, without scene changes.

To enable names for the NEXT SDK import, set REGISTER_NAMES = True and run again.
This updates the one active SDK's in-memory dictionary only; restart loses it.
Existing bones, vertex groups, constraints and animation paths are never renamed.
"""
import json
import sys
from pathlib import Path

REGISTER_NAMES = False
MANIFEST_PATH = ''  # Optional absolute source-skeleton.json path.


def inspect(bpy, manifest, register=False):
    rows = manifest['bones'] + manifest.get('motionLayers', [])
    names = {int(row['hash']):row['name'] for row in rows}
    if len(names) != len(rows) or len(set(names.values())) != len(rows):
        raise ValueError('Manifest has duplicate hashes or names')
    sdks = []
    for key in bpy.context.preferences.addons.keys():
        module = sys.modules.get(key)
        dictionary = getattr(module, 'Global_BoneNames', None)
        if isinstance(dictionary, dict) and hasattr(module, 'Global_TocManager'):
            sdks.append((key,module,dictionary))
    if len(sdks) != 1:
        raise RuntimeError(f'Expected one enabled SDK with Global_BoneNames; found {[s[0] for s in sdks]}')
    key, module, dictionary = sdks[0]
    clashes = {str(h):{'existing':dictionary[h], 'requested':name}
               for h,name in names.items() if h in dictionary and dictionary[h] != name}
    for h,name in dictionary.items():
        if name in names.values() and h not in names:
            clashes[str(h)] = {'existing':name,'reason':'Name belongs to a different hash'}
    missing = {str(h):name for h,name in names.items() if h not in dictionary}
    numeric = []
    for armature in bpy.data.armatures:
        for bone in armature.bones:
            if bone.name.isdecimal() and int(bone.name) in names:
                numeric.append({'armature':armature.name,'displayName':bone.name,'normalizedName':names[int(bone.name)]})
    if register and clashes:
        raise RuntimeError('Dictionary conflicts; no changes applied: ' + json.dumps(clashes,ensure_ascii=False))
    if register:
        dictionary.update(names)
    return {'mode':'register-in-memory-dictionary' if register else 'read-only',
        'sdk':key,'sdkPath':getattr(module,'__file__',None),'sourceNames':len(manifest['bones']),
        'helperNames':len(manifest.get('motionLayers',[])), 'missingBefore':missing,'conflicts':clashes,
        'numericDisplayBones':numeric, 'registered':len(missing) if register else 0,
        'sceneChanged':False,
        'nextStep':'Re-import into a separate Blender scene to see names; this script does not rename existing data.'}


def main():
    import bpy
    if MANIFEST_PATH:
        path = Path(MANIFEST_PATH)
    else:
        location = Path(__file__).resolve()
        candidates = [location.parent/'source-skeleton.json', location.parent.parent/'source-skeleton.json']
        path = next((p for p in candidates if p.is_file()),None)
        if path is None:
            raise FileNotFoundError('Set MANIFEST_PATH to this project\'s source-skeleton.json')
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    print(json.dumps(inspect(bpy,manifest,REGISTER_NAMES),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
