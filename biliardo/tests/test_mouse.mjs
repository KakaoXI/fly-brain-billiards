import test from 'node:test';
import assert from 'node:assert/strict';
import {aimGuide,pullPower,FrameBuffer} from '../dist/pool-math.js';

test('drag backward sets continuous power; click and forward movement do not shoot',()=>{
  assert.equal(pullPower({x:400,y:250},{x:400,y:250},0),0);
  assert.equal(pullPower({x:400,y:250},{x:320,y:250},0),.5);
  assert.equal(pullPower({x:400,y:250},{x:500,y:250},0),0);
  assert.equal(pullPower({x:400,y:250},{x:0,y:250},0),1);
});
test('power follows the cue orientation at any angle',()=>{
  assert.ok(Math.abs(pullPower({x:400,y:250},{x:400,y:170},Math.PI/2)-.5)<1e-9);
});
test('guide hits the first ball and shows its outgoing direction',()=>{
  const guide=aimGuide([{number:0,x:200,y:250},{number:9,x:500,y:250},{number:10,x:700,y:250}],0);
  assert.equal(guide.target.number,9);assert.equal(guide.contact.x,478);assert.equal(guide.contact.y,250);
  assert.equal(guide.objectEnd.y,250);assert.ok(guide.objectEnd.x>700);
  assert.deepEqual(guide.cueEnd,guide.contact);
});
test('cut shot has different cue and target directions',()=>{
  const guide=aimGuide([{number:0,x:200,y:250},{number:9,x:500,y:265}],0);
  assert.ok(guide.objectEnd.y>265);assert.ok(guide.cueEnd.y<250);
});
test('pocketed balls and balls behind the cue cannot be selected',()=>{
  const guide=aimGuide([{number:0,x:200,y:250},{number:9,x:500,y:250,pocketed:true},{number:10,x:100,y:250}],0);
  assert.equal(guide.target,null);assert.equal(guide.contact.x,989);
});
test('buffer interpolates between actual server samples instead of freezing every poll',()=>{
  const buffer=new FrameBuffer(0),a={id:1,t:0,game:1,shot:1,phase:'moving',body:[0,.5],balls:[[100,250,100,0,0]]},b={...a,id:2,t:20,balls:[[102,250,100,0,0]]};
  buffer.push([a,b],1000);
  assert.equal(buffer.sample(990).balls[0][0],101);
  assert.equal(buffer.sample(995).balls[0][0],101.5);
});
test('new shot does not interpolate across a discontinuity',()=>{
  const buffer=new FrameBuffer(0),a={id:1,t:0,game:1,shot:1,body:[0,.5],balls:[[100,250,0,0,0]]},b={...a,id:2,t:20,shot:2,balls:[[500,250,0,0,0]]};
  buffer.push([a,b],1000);
  assert.equal(buffer.sample(990).balls[0][0],100);
  assert.equal(buffer.sample(1000).balls[0][0],500);
});
test('server restart and memory load reset old frame IDs',()=>{
  const buffer=new FrameBuffer(0),a={id:5000,t:100,epoch:'old',game:1,shot:1,body:[0,.5],balls:[[100,250,0,0,0]]};
  buffer.push([a],200);
  buffer.push([{...a,id:1,t:0,epoch:'new',balls:[[600,250,0,0,0]]}],300);
  assert.equal(buffer.sample(300).balls[0][0],600);assert.equal(buffer.frames.length,1);
});
