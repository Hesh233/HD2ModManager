"""Read public references through the requested local HTTP proxy only."""
import concurrent.futures
import argparse
import hashlib
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/native-b8-analysis-20261104/web'
PROXY='http://127.0.0.1:7890'
SOURCES={
 'stingray-unit':'https://help.autodesk.com/cloudhelp/ENU/Stingray-Help/lua_ref/obj_stingray_Unit.html',
 'stingray-world':'https://help.autodesk.com/cloudhelp/ENU/Stingray-Help/lua_ref/obj_stingray_World.html',
 'stingray-matrix':'https://help.autodesk.com/cloudhelp/ENU/Stingray-Help/lua_ref/obj_stingray_Matrix4x4.html',
 'khronos-skinning':'https://github.khronos.org/glTF-Tutorials/gltfTutorial/gltfTutorial_020_Skins.html',
 'search-stingray':'https://www.google.com/search?q='+quote('Stingray Unit set_local_pose link_node animation bone mode'),
 'search-hd2':'https://www.google.com/search?q='+quote('Helldivers 2 Lua link_node skeleton weapon grip animation'),
 'search-bing-stingray':'https://www.bing.com/search?q='+quote('site:help.autodesk.com Stingray Unit scene_graph_parent set_local_pose link_unit'),
 'search-bing-hd2':'https://www.bing.com/search?q='+quote('Helldivers 2 Lua skeleton link_unit weapon grip'),
}


class Plain(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag in ('p','div','section','br','tr','li','h1','h2','h3','h4','pre'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
        if tag in ('p','div','section','tr','li','h1','h2','h3','h4','pre'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


def fetch(item):
    name,url=item
    path=OUT/(name+'.html')
    command=['curl.exe','--silent','--show-error','--fail','--location','--proxy',PROXY,'--noproxy','',
        '--connect-timeout','10','--max-time','40','--retry','1','--retry-all-errors',
        '--output',str(path),'--write-out','%{http_code}\n%{url_effective}',url]
    cp=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    result=dict(name=name,url=url,proxy=PROXY,exitCode=cp.returncode,status=cp.stdout,error=cp.stderr)
    if cp.returncode==0:
        data=path.read_bytes();parser=Plain();parser.feed(data.decode('utf-8',errors='replace'))
        lines=[' '.join(line.split())for line in ''.join(parser.parts).splitlines()]
        plain='\n'.join(line for line in lines if line)
        (OUT/(name+'.txt')).write_text(plain,encoding='utf-8')
        result.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    print(json.dumps({k:v for k,v in result.items()if k not in ('error','sha256')},ensure_ascii=True),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('names',nargs='*',choices=list(SOURCES))
    args=parser.parse_args();selected=args.names or list(SOURCES)
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:results=list(pool.map(fetch,[(k,SOURCES[k])for k in selected]))
    if (OUT/'sources.json').exists():
        old=json.loads((OUT/'sources.json').read_text(encoding='utf-8'))
        results=[r for r in old if r['name']not in selected]+results
    (OUT/'sources.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
