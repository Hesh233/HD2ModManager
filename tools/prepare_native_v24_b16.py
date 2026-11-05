"""Continue the established profile-only bisection from B15-A1."""
from pathlib import Path
source=Path(__file__).with_name('prepare_native_v23_b15.py').read_text(encoding='utf-8')
replacements=[
 ('native-v23-b15-20261105','native-v24-b16-20261105'),
 ("baseline['revision']=='native-v22'","baseline['revision']=='native-v23'"),
 ("R/'project/diagnostics/B14'","R/'project/diagnostics/B15'"),
 ('variants/A/','variants/A1/'),
 ('B14-A','B15-A1'),
 ('len(root_set)==8','len(root_set)==4'),
 ("{'attach_weapon','attach_hand_l','attach_hand_r','head_aim'}","{'attach_hand_l','attach_hand_r'}"),
 ('len(first_roots)==4','len(first_roots)==2'),
 ('len(roots)==4','len(roots)==2'),
 ("len(groups['A1'])==6 and len(groups['A2'])==11","len(groups['A1'])==3 and len(groups['A2'])==3"),
 ("profile['revision']='test01-v23-B15-'+variant","profile['revision']='test01-v24-B16-'+variant"),
 ("restored['attachmentProbe']['variant']='A'","restored['attachmentProbe']['variant']='A1'"),
 ('docs/native-v23-B15-20261105.md','docs/native-v24-B16-20261105.md'),
 ("'B15-'+variant","'B16-'+variant"),
 ("'hd2physbone-B15-'+variant","'hd2physbone-B16-'+variant"),
 ("'B15-A1-原生持枪挂点二分测试.zip'","'B16-H-双手挂点二分测试.zip'"),
 ("'B15-A2-来源武器骨二分测试.zip'","'B16-W-武器瞄准挂点二分测试.zip'"),
 ("'test01 B15-'","'test01 B16-'"),
 ("'A1':","'H':"),("'A2':","'W':"),
 ("groups['A1']","groups['H']"),("groups['A2']","groups['W']"),
 ('rootFamiliesPerGroup=4','rootFamiliesPerGroup=2'),
 ('unionExactlyEqualsB14A','unionExactlyEqualsB15A1'),
 ("probe='B15-A1/A2'","probe='B16-H/W'"),
 ('A1 native hand/weapon/head aim families; A2 boss aim and three Source weapon families.',
  'H: attach_hand_l and attach_hand_r/weapon_aim. W: attach_weapon/aim_weapon and head_aim.'),
 ('A1 4 roots/6 nodes, A2 4 roots/11 nodes','H 2 roots/3 nodes, W 2 roots/3 nodes'),
 ('B15 prepared:','B16 prepared:'),
]
for old,new in replacements:
    assert old in source,old
    source=source.replace(old,new)
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
