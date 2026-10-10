import shutil
import subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(shutil.which('node') is None,reason='Node required for browser geometry')
def test_status_edges_geometry_and_postal_scrubbing():
    code=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c={window:{},document:{querySelector:()=>null},matchMedia:()=>({matches:true})};
for(const name of ['checkblock','location-check','chat-home'])vm.runInNewContext(fs.readFileSync('app/web/'+name+'.js','utf8'),c);
const tier=c.window.LocationCheck.tier,geo=c.window.CheckBlock.distanceToCluster;
assert.equal(tier([{distance:150,people:10}],false),'red');
assert.equal(tier([{distance:150.01,people:10}],false),'amber');
assert.equal(tier([{distance:150,people:9}],false),'amber');
assert.equal(tier([{distance:1000,people:2}],true),'amber');
assert.equal(tier([{distance:1000.01,people:100}],true),'purple');
assert.equal(tier([{distance:1000.01,people:100}],false),'green');
assert.equal(tier([{distance:1,people:2},{distance:140,people:10}],true),'red');
assert.equal(tier([],false),'green');
const polygon={type:'Polygon',coordinates:[[[103.8,1.3],[103.81,1.3],[103.81,1.31],[103.8,1.31],[103.8,1.3]],[[103.803,1.303],[103.807,1.303],[103.807,1.307],[103.803,1.307],[103.803,1.303]]]};
assert.equal(geo(1.301,103.801,polygon),0);assert(geo(1.305,103.805,polygon)>0);
assert(!c.window.ChatHome.scrub('邮编560123附近怎么样？ 1.312312,103.812323').includes('560123'));
assert(!c.window.ChatHome.scrub('1.312312,103.812323').includes('1.312312'));
"""
    result=subprocess.run(['node','-e',code],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
