"""Record relevant live log evidence without modifying game or loader settings."""
from pathlib import Path
from package_native_v14 import WORK,save_json,digest

def main():
    root=Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2')
    chef=root/'chef_loader.log';physics=root/'hd2physbone.log'
    loader=chef.read_text(encoding='utf-8-sig').splitlines()
    runtime=physics.read_text(encoding='utf-8-sig').splitlines()
    requested=[('17:29:19','started mods/hd2modmanager/physbone 2.1.8'),
        ('17:30:34','switched off mods/hd2modmanager/physbone'),
        ('17:30:35','it starts at the next launch'),('17:44:49','found 0 addon(s)')]
    evidence=[]
    for time,fragment in requested:
        found=[line for line in loader if line.startswith(time) and fragment in line]
        assert found,(time,fragment)
        evidence.append(found[-1])
    for time,fragment in [('17:29:19','variant=test01-v13-B4'),('17:30:32','native_hand_sync')]:
        found=[line for line in runtime if line.startswith(time) and fragment in line]
        assert found,(time,fragment)
        evidence.append(found[-1])
    save_json(WORK/'runtime-activation-evidence.json',dict(status='PASS',scope='historical v13 execution evidence; v14 not game-tested',
        evidence=evidence,files=[dict(path=str(p),sha256=digest(p)) for p in (chef,physics)],
        v13Loaded=True,v13CallbacksExecuted=True,v13AvatarReadbackObserved=True,armorSkinningEffect='unverified',
        userObservation='Removing v13 Lua caused no visible change',
        v14Diagnostic='Read matched model arm nodes before and after update_unit; never write model nodes'))
    print('Historical v13 loading/execution recorded; armor skinning remains unverified.')

if __name__=='__main__':main()
