// Run the actual input handlers against a small DOM/canvas test double.
// No browser automation, visual inspection or live user input is involved.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {aimGuide,pullPower,FrameBuffer} from '../dist/pool-math.js';

async function setup(){
  const calls=[],elements=new Map();
  class Element{
    constructor(){this.handlers={};this.style={};this.classList={add(){},remove(){},toggle(){}};this.width=1160;this.height=660;this.clientWidth=1160;this.clientHeight=660;this.tagName='CANVAS';}
    addEventListener(name,fn){(this.handlers[name]??=[]).push(fn);}
    emit(name,e={}){for(const fn of this.handlers[name]||[])fn({button:0,pointerId:1,preventDefault(){},...e});}
    append(){}replaceChildren(){}setAttribute(){}focus(){}setPointerCapture(){}hasPointerCapture(){return false;}releasePointerCapture(){}
    getBoundingClientRect(){return {left:0,top:0,width:1160,height:660};}
    getContext(){return new Proxy({}, {get:(_,name)=>name.startsWith('create')?()=>({addColorStop(){}}):()=>{}});}
  }
  const html=fs.readFileSync(new URL('../dist/index.html',import.meta.url),'utf8');
  for(const match of html.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element());
  const document=new Element();Object.assign(document,{hidden:false,getElementById:id=>elements.get(id),createElement:()=>new Element(),createTextNode:text=>({textContent:text}),querySelector:()=>null,querySelectorAll:()=>[]});
  const game={balls:Array.from({length:16},(_,number)=>({number,x:number?650+number*23:240,y:250,vx:0,vy:0,pocketed:false})),phase:'aim',turn:'human',shot_id:0,game_number:1,history:[],fly_shots:0,fly_pots:0,reward_total:0,message:'Tocca a te'};
  const state={phase:'ready',build:'smooth-3',brain:null,game,paused:false,learning:true};
  class Observer{observe(){}disconnect(){}}
  const context=vm.createContext({console,document,window:new Element(),location:{reload(){throw Error('Unexpected reload');}},devicePixelRatio:1,
    performance:{now:()=>1000},IntersectionObserver:Observer,ResizeObserver:Observer,EventSource:class{close(){}},AbortController,
    setTimeout(){return 1;},clearTimeout(){},requestAnimationFrame(){},aimGuide,pullPower,FrameBuffer,
    fetch:async(url,options)=>{
      if(url==='/api/bootstrap')return {ok:true,json:async()=>({token:'test-token',state:structuredClone(state)})};
      if(url==='/api/command'){const command=JSON.parse(options.body);calls.push(command);return {ok:true,json:async()=>({accepted:true,state:{...structuredClone(state),game:{...structuredClone(game),phase:'moving',shot_id:1}}})};}
      throw Error('Unexpected request: '+url);
    }});
  const source=fs.readFileSync(new URL('../dist/app.js',import.meta.url),'utf8').replace(/^import .*?;\r?\n/,'');
  new vm.Script(source,{filename:'app.js'}).runInContext(context);
  await new Promise(setImmediate);await new Promise(setImmediate);
  return {table:elements.get('table'),document,calls};
}
test('press, pull and release submits the mouse power once',async()=>{
  const {table,calls}=await setup();
  table.emit('pointerdown',{clientX:580,clientY:330});
  table.emit('pointermove',{clientX:500,clientY:330});
  table.emit('pointerup',{clientX:500,clientY:330});
  await new Promise(setImmediate);
  assert.equal(calls.length,1);assert.equal(calls[0].name,'shoot');assert.equal(calls[0].angle,0);assert.equal(calls[0].power,.5);
});
test('a simple aim click cannot accidentally fire',async()=>{
  const {table,calls}=await setup();
  table.emit('pointerdown',{clientX:580,clientY:330});table.emit('pointerup',{clientX:580,clientY:330});
  await new Promise(setImmediate);assert.equal(calls.length,0);
});
test('Escape cancels a charged mouse shot',async()=>{
  const {table,document,calls}=await setup();
  table.emit('pointerdown',{clientX:580,clientY:330});table.emit('pointermove',{clientX:450,clientY:330});
  document.emit('keydown',{code:'Escape',target:table});table.emit('pointerup',{clientX:450,clientY:330});
  await new Promise(setImmediate);assert.equal(calls.length,0);
});
