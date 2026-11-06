import copy, struct, unittest
from static_model_mounts import rewrite_unit, matrix, WorldTransform, bone_name_hash, _calculate_world_transforms
from anim_batch_mod.formats import UnitData


def fixture():
    names=['root','r_hand','l_hand','head','test_r_hand','test_l_hand','test_head',
           'test_weapon_r','test_weapon_l','attach_hand_r','attach_hand_l','attach_cam_1','attach_samplepouch']
    parents=[None,0,0,0,0,0,0,4,5,1,2,3,0]
    poses=[WorldTransform([i*.1,0,0],[0,0,0,1],[1,1,1]) for i in range(len(names))]
    poses[4].scale=[.5,2,1]
    def node(i):return dict(name=names[i],hash=bone_name_hash(names[i]),index=999,parent=999)
    profile=dict(avatar=dict(nodes=[node(1),node(2),node(3)]),target=node(9),nativeRight=node(1),sourceRight=node(4),
        attachments=[dict(node=node(10),source=node(5),native=node(2)),
                     dict(node=node(12),source=node(4),native=node(0),axes=[1,0,0,0,1,0,0,0,1,0,0,0])])
    manifest=dict(bones=[dict(name=names[4],driver='r_hand'),dict(name=names[5],driver='l_hand'),
        dict(name=names[6],driver='head'),dict(name=names[7],sourceName='ValveBiped.weapon_bone'),
        dict(name=names[8],sourceName='ValveBiped.L_weapon_bone')])
    def encode():
        raw=bytearray(56);struct.pack_into('<I',raw,52,56)
        world=_calculate_world_transforms(poses,parents)
        raw.extend(struct.pack('<I12x',len(names)))
        for p in poses:raw.extend(struct.pack('<16f',*matrix(p)))
        for p in world:raw.extend(struct.pack('<16f',*matrix(p,True)))
        for p in parents:raw.extend(struct.pack('<HH',1,65535 if p is None else p))
        raw.extend(struct.pack('<'+str(len(names))+'I',*(bone_name_hash(n) for n in names)))
        return bytes(raw)
    return encode,parents,profile,manifest


class StaticMountTests(unittest.TestCase):
    def test_actual_reparent_with_scaled_source_parent_and_wrong_avatar_indices(self):
        encode,parents,profile,manifest=fixture();raw=encode()
        output,report=rewrite_unit(raw,profile,manifest,{4,5,6})
        a,b=UnitData.parse(raw),UnitData.parse(output)
        self.assertEqual(b.parents[9],7);self.assertEqual(b.parents[10],8);self.assertEqual(b.parents[12],4)
        self.assertEqual(b.parents[11],3);self.assertEqual(b.name_hashes,a.name_hashes)
        self.assertEqual(b.transforms[11],a.transforms[11]);self.assertEqual(b.transforms[6],a.transforms[6])
        self.assertGreater(report['sourceWristMovesMount'],.019);self.assertLess(report['nativeWristMovesMount'],1e-6)
        before=_calculate_world_transforms(a.transforms,a.parents);after=_calculate_world_transforms(b.transforms,b.parents)
        for i in (4,5,6):self.assertEqual(before[i],after[i])
        for x,y in zip(after[9].position,after[7].position):self.assertAlmostEqual(x,y,places=5)

    def test_reject_weighted_mount_or_descendant(self):
        encode,parents,profile,manifest=fixture()
        with self.assertRaisesRegex(ValueError,'weighted'):rewrite_unit(encode(),profile,manifest,{9})

    def test_reject_head_attachment(self):
        encode,parents,profile,manifest=fixture();parents[12]=3
        with self.assertRaisesRegex(ValueError,'Head'):rewrite_unit(encode(),profile,manifest,{4,5,6})

if __name__=='__main__':unittest.main()
