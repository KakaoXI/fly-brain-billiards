import {aimGuide,pullPower,FrameBuffer} from './pool-math.js';
const BUILD='smooth-4';
const $ = id => document.getElementById(id);
const fmt = n => Number(n || 0).toLocaleString('it-IT', {maximumFractionDigits: 0});
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const colors = ['#f5f1df','#e8b733','#3970c3','#c84849','#9164b9','#e88c31','#3d9366','#8d3545','#20222a'];
let state, token, stateTime=0, angle=0, power=.65, placing=false, connected=false, lastCommand='', toastTimer;
let positions, activity, brainView, loadingPoints=false, stopPolling=false;
let drag=null, shotPending=false, stream=null, streamToken='', streamed=false, lastStream=0, renderFrame=null;
let brainVisible=false, bodyVisible=true, visionVisible=false, ratesVisible=false, tableVisible=true, brainDirty=true;
const frameBuffer=new FrameBuffer(65);
const table=$('table'), ctx=table.getContext('2d'), bodyCtx=$('body').getContext('2d');

function text(id, value) { const el=$(id); if(el && el.textContent!==String(value))el.textContent=value; }
function toast(message) { text('toast',message); $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>{$('toast').hidden=true;},6000); }
async function json(url, options) { const r=await fetch(url,options); if(!r.ok){const raw=await r.text();let detail;try{detail=JSON.parse(raw).detail;}catch{detail=raw;}const error=new Error(typeof detail==='string'?detail:r.statusText);error.status=r.status;throw error;}return r.json(); }
async function command(name, data={}) {
  const send=()=>json('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Biliardo-Token':token},body:JSON.stringify({name,...data})});
  let result;
  try{result=await send();}catch(e){if(e.status!==403)throw e;const boot=await json('/api/bootstrap');token=boot.token;result=await send();}
  state=result.state;stateTime=performance.now();update();return result;
}
function act(name, data={}) { return command(name,data).catch(e=>toast(e.message)); }
function humanTurn() { return connected && !shotPending && state?.phase==='ready' && !state.paused && state.game.turn==='human' && state.game.phase==='aim'; }
function setAngle(value) { angle=((value%360)+360)%360; $('angle').value=String(angle); text('angle-value',`${Math.round(angle)}°`); }
function setPower(value) { power=clamp(value,0,1);$('power').value=String(Math.max(3,Math.round(power*100)));text('power-value',`${Math.round(power*100)}%`);$('mouse-power-bar').style.width=`${power*100}%`; }
$('angle').addEventListener('input',e=>setAngle(+e.target.value));
$('power').addEventListener('input',e=>setPower(+e.target.value/100));
async function shoot(){if(!humanTurn()||power<.03)return;placing=false;shotPending=true;try{await command('shoot',{angle:angle*Math.PI/180,power});}catch(e){toast(e.message);}finally{shotPending=false;update();}}
$('shoot').addEventListener('click',shoot);
$('pause').addEventListener('click',()=>act('pause',{enabled:!state?.paused}));
$('learning').addEventListener('change',e=>act('learning',{enabled:e.target.checked}));
$('new').addEventListener('click',()=>{placing=false;act('new');});
$('save').addEventListener('click',()=>act('save'));
$('place').addEventListener('click',()=>{placing=!placing; update();});
function tablePoint(e){const r=table.getBoundingClientRect();return {x:(e.clientX-r.left)*1160/r.width-80,y:(e.clientY-r.top)*660/r.height-80};}
function aimAt(point){const cue=state.game.balls[0];if(Math.hypot(point.x-cue.x,point.y-cue.y)>18)setAngle(Math.atan2(point.y-cue.y,point.x-cue.x)*180/Math.PI);}
table.addEventListener('pointerdown',async e=>{
  if(!humanTurn()||e.button!==0)return;
  const point=tablePoint(e);
  if(placing){try{await command('place',point);placing=false;update();}catch(error){toast(error.message);}return;}
  e.preventDefault();aimAt(point);drag={start:point,angle:angle*Math.PI/180,id:e.pointerId};setPower(0);
  table.setPointerCapture(e.pointerId);table.classList.add('charging');table.focus({preventScroll:true});
});
table.addEventListener('pointermove',e=>{if(!humanTurn()||placing)return;const point=tablePoint(e);if(drag){setPower(pullPower(drag.start,point,drag.angle));}else aimAt(point);});
table.addEventListener('pointerup',e=>{if(!drag||drag.id!==e.pointerId)return;drag=null;table.classList.remove('charging');if(table.hasPointerCapture(e.pointerId))table.releasePointerCapture(e.pointerId);if(power>=.03)shoot();});
function cancelDrag(){drag=null;table.classList.remove('charging');setPower(0);}
table.addEventListener('pointercancel',cancelDrag);
table.addEventListener('lostpointercapture',()=>{if(drag)cancelDrag();});
document.addEventListener('keydown',e=>{
  if(e.code==='Escape'&&drag){cancelDrag();return;}
  if(document.querySelector('dialog[open]') || /INPUT|BUTTON|SELECT|TEXTAREA/.test(e.target.tagName))return;
  if(e.code==='Space' && humanTurn()){e.preventDefault();$('shoot').click();}
  if(humanTurn() && ['ArrowLeft','ArrowRight'].includes(e.code)){e.preventDefault();setAngle(angle+(e.code==='ArrowLeft'?-1:1));}
});
for(const button of document.querySelectorAll('dialog .close'))button.addEventListener('click',()=>button.closest('dialog').close());
$('help').addEventListener('click',()=>$('help-dialog').showModal());
$('memory').addEventListener('click',async()=>{
  $('archive-dialog').showModal();text('save-list','Caricamento…');
  try{
    const saves=await json('/api/saves');$('save-list').replaceChildren();
    if(!saves.length)text('save-list','Nessun salvataggio ancora disponibile.');
    for(const save of saves){
      const row=document.createElement('div');row.className='save-row';
      const info=document.createElement('div');info.textContent=save.name;
      const small=document.createElement('small');small.textContent=`${new Date(save.modified*1000).toLocaleString('it-IT')} · ${(save.bytes/1048576).toFixed(1)} MB`;info.append(small);
      const load=document.createElement('button');load.textContent='Riprendi';load.addEventListener('click',async()=>{try{await command('load',{file:save.name});$('archive-dialog').close();}catch(e){toast(e.message);}});
      const download=document.createElement('a');download.href=`/api/saves/${encodeURIComponent(save.name)}`;download.download=save.name;download.textContent='↓';download.setAttribute('aria-label',`Scarica ${save.name}`);
      row.append(info,load,download);$('save-list').append(row);
    }
  }catch(e){text('save-list',e.message);}
});

const rackCache={};let historyKey='';
function updateRack(id, numbers){
  const key=numbers.map(n=>+state.game.balls[n].pocketed).join('');if(rackCache[id]===key)return;rackCache[id]=key;
  const rack=$(id);rack.replaceChildren();
  for(const n of numbers){const dot=document.createElement('span');dot.className='rack-ball'+(n>8?' stripe':'')+(state.game.balls[n].pocketed?' out':'');dot.title=`Palla ${n}${state.game.balls[n].pocketed?' imbucata':''}`;rack.append(dot);}
}
function update(){
  if(!state)return;
  const g=state.game,b=state.brain,ready=state.phase==='ready',canShoot=humanTurn(),fly=g.turn==='fly';
  $('loading').hidden=ready; text('loading-detail',state.error||state.loading);
  $('connection').textContent=!connected?'Disconnesso':state.phase==='error'?'Errore del modello':!ready?'Caricamento GPU':state.paused?'In pausa':'Connectoma attivo';
  $('shoot').disabled=!canShoot; $('angle').disabled=!canShoot; $('power').disabled=!canShoot;
  for(const id of ['new','save','pause','learning'])$(id).disabled=!ready||!connected;
  $('human-player').classList.toggle('active',!fly);$('fly-player').classList.toggle('active',fly);
  text('human-left',g.balls.filter(v=>v.number>=1&&v.number<=7&&!v.pocketed).length);text('fly-left',g.balls.filter(v=>v.number>=9&&!v.pocketed).length);
  updateRack('human-rack',[1,2,3,4,5,6,7]);updateRack('fly-rack',[9,10,11,12,13,14,15]);
  text('game-message',state.paused?'Simulazione in pausa. Cervello e tavolo sono fermi.':g.message);
  text('game-number',`TAVOLO ${String(g.game_number).padStart(2,'0')}`);
  text('turn-label',g.phase==='over'?'PARTITA CONCLUSA':fly?'IL TURNO DELLA MOSCA':'IL TUO TURNO');
  text('turn-title',g.winner?(g.winner==='human'?'Hai vinto.':'Vince la mosca.'):state.paused?'Un momento di pausa.':g.phase==='moving'?'Segui il colpo.':fly?'La mosca prepara il tiro.':'La stecca è tua.');
  text('turn-help',g.winner?'Apri un nuovo tavolo: la memoria appresa rimane.':state.paused?'Premi Riprendi per continuare.':g.phase==='moving'?'Il prossimo tiro parte quando tutte le palle sono ferme.':fly?(b?.body?.status==='In attesa del turno'?'Osserva il tavolo.':`${b?.body?.status||'Osserva il tavolo'} · ${(b?.body?.aim_seconds||0).toFixed(1)} s di preparazione.`):'Muovi il mouse per mirare. Tieni premuto, tira indietro per caricare e rilascia.');
  text('table-note',placing?'CLICCA UN PUNTO LIBERO PER LA BIANCA':g.phase==='moving'?'':fly?'CONTROLLO AUTONOMO DELLA STECCA':'MIRA · TIENI PREMUTO E TIRA INDIETRO · RILASCIA');
  $('place').hidden=!(canShoot&&g.ball_in_hand);text('place',placing?'Annulla posizionamento':'Posiziona la bianca');
  text('pause',state.paused?'▶ Riprendi simulazione':'Ⅱ Pausa simulazione');$('learning').checked=state.learning;
  text('live-label',state.paused?'PAUSA':'LIVE');
  if(state.saved_at)text('save-status',`Salvata ${new Date(state.saved_at).toLocaleTimeString('it-IT')} · autosave attivo`);
  if(state.command){const sig=JSON.stringify(state.command);if(sig!==lastCommand){lastCommand=sig;if(state.command.message!=='Operazione in corso…')toast(state.command.message);}}
  if(b){
    text('neurons',fmt(b.neurons));text('edges',`${fmt(b.edges)} connessioni simulate`);
    text('active',fmt(b.stats.active));text('spike-window',`${fmt(b.stats.spikes)} spike in ${b.stats.window_ms||40} ms neurali`);
    $('reward').replaceChildren(document.createTextNode(`${b.last_reward.value} `),Object.assign(document.createElement('em'),{textContent:'DA'}));
    text('reward-reason',b.last_reward.reason);$('reward-bar').style.width=`${clamp(b.pulse_ms/2000*100,0,100)}%`;
    $('updates').replaceChildren(document.createTextNode(`${g.fly_shots} `),Object.assign(document.createElement('em'),{textContent:'tiri'}));
    text('fly-angle',`${Math.round(b.body.angle*180/Math.PI)}°`);text('fly-power',`${Math.round(b.body.power*100)}%`);text('motor-spikes',fmt(b.body.release_spikes));
    text('body-state',state.paused?'In pausa':g.turn==='fly'?(g.phase==='aim'?b.body.status:'Osserva'):'In attesa');$('body-state').title=b.body.status;
    text('plastic',fmt(b.memory.plastic_edges));text('changed',fmt(b.memory.changed_edges));text('pulse',`${Math.round(b.pulse_ms)} ms`);
    text('neural-clock',`${(b.sim_ms/1000).toFixed(2)} s neurali`);text('speed',`${Math.round(b.step_wall_ms)} ms reali / ${b.neural_step_ms} ms neurali`);
    text('brain-caption',`${fmt(b.stats.active)} neuroni con spike · nessuna attività generata per la grafica`);
    text('memory-source',b.source);
    text('readout-detail',`${b.readout_parameters} pesi artificiali · ${b.body.updates} tiri valutati · ultima variazione ${b.body.last_gradient.toFixed(6)}. Esplorazione ${state.learning?'attiva':'ridotta, pesi congelati'}.`);
    text('performance-detail',`${g.fly_pots} mezze imbucate regolarmente in ${g.fly_shots} tiri · premio cumulativo ${g.reward_total}. Abilità di gioco non ancora validata.`);
    if(brainVisible&&!positions&&!loadingPoints)loadBrain();if(ratesVisible)drawRates(b.rates);
  }
  const nextHistoryKey=`${g.game_number}/${g.history.map(e=>`${e.id}:${e.actor}:${e.reward}`).join(',')}`;
  if(historyKey===nextHistoryKey)return;historyKey=nextHistoryKey;
  const history=g.history.slice().reverse();$('events').replaceChildren();
  if(!history.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='Il primo tiro aprirà il diario della partita.';$('events').append(empty);}
  for(const event of history){
    const row=document.createElement('div');row.className='event';
    const chip=document.createElement('span');chip.className=`event-chip ${event.level}`;chip.textContent=event.actor==='human'?'TU':event.reward?`+${event.reward}`:'0';
    const content=document.createElement('div');content.className='event-text';content.textContent=event.actor==='fly'?event.reason:event.foul||((event.pots.length?`Imbucate: ${event.pots.join(', ')}`:'Tiro concluso'));
    const small=document.createElement('small');small.textContent=`${event.actor==='fly'?'Mosca':'Tu'} · forza ${Math.round(event.power*100)}% · ${Math.round(event.angle*180/Math.PI)}°`;content.append(small);
    const number=document.createElement('span');number.className='event-number';number.textContent=`#${event.id}`;row.append(chip,content,number);$('events').append(row);
  }
}

function rounded(c,x,y,w,h,r,fill,stroke){c.beginPath();c.roundRect(x,y,w,h,r);if(fill){c.fillStyle=fill;c.fill();}if(stroke){c.strokeStyle=stroke;c.stroke();}}
function paintBall(c,b,x,y,r=11){
  c.save();c.shadowColor='#00170aaa';c.shadowBlur=5;c.shadowOffsetY=3;
  const n=b.number,color=colors[n>8?n-8:n];c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fillStyle=n>8?'#f5f1df':color;c.fill();c.shadowColor='transparent';
  c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.clip();if(n>8){c.fillStyle=color;c.fillRect(x-r,y-r*.48,r*2,r*.96);}
  const shade=c.createRadialGradient(x-r*.4,y-r*.5,0,x,y,r*1.3);shade.addColorStop(0,'#ffffff44');shade.addColorStop(.5,'#ffffff00');shade.addColorStop(1,'#00000077');c.fillStyle=shade;c.fillRect(x-r,y-r,r*2,r*2);
  if(n){c.beginPath();c.arc(x,y,4.6,0,Math.PI*2);c.fillStyle='#f2eddf';c.fill();c.fillStyle='#243024';c.font='bold 6.5px Segoe UI';c.textAlign='center';c.textBaseline='middle';c.fillText(n,x,y+.2);}
  c.restore();
}
const sprites=new Map();
function ball(c,b,x,y,r=11){
  if(!sprites.has(b.number)){const image=document.createElement('canvas');image.width=image.height=80;const g=image.getContext('2d');g.scale(2,2);paintBall(g,b,20,20);sprites.set(b.number,image);}
  const size=40*r/11;c.drawImage(sprites.get(b.number),x-size/2,y-size/2,size,size);
}
const backdrop=document.createElement('canvas');backdrop.width=1160;backdrop.height=660;
function paintTableBackground(){
  const c=backdrop.getContext('2d');
  c.save();c.shadowBlur=28;c.shadowColor='#0007';c.shadowOffsetY=14;rounded(c,45,44,1070,572,30,'#443c2e');c.restore();
  rounded(c,49,48,1062,564,27,'#64543d','#8a765245');rounded(c,62,61,1036,538,20,'#243a28');
  const felt=c.createLinearGradient(0,80,0,580);felt.addColorStop(0,'#245d49');felt.addColorStop(.55,'#1e5a46');felt.addColorStop(1,'#174f3d');rounded(c,80,80,1000,500,5,felt);
  // Cushion segments stop at the pocket jaws.
  c.lineWidth=15;c.lineCap='butt';c.strokeStyle='#397259';
  for(const y of [78,582])for(const [a,b] of [[110,550],[610,1050]]){c.beginPath();c.moveTo(a,y);c.lineTo(b,y);c.stroke();}
  for(const x of [78,1082]){c.beginPath();c.moveTo(x,110);c.lineTo(x,550);c.stroke();}
  c.lineWidth=1;c.strokeStyle='#92aa7040';c.strokeRect(95,95,970,470);
  for(const [x,y] of [[80,80],[580,80],[1080,80],[80,580],[580,580],[1080,580]]){
    c.beginPath();c.arc(x,y,25,0,Math.PI*2);c.fillStyle='#181e17';c.fill();c.lineWidth=3;c.strokeStyle='#8a79524d';c.stroke();c.beginPath();c.arc(x,y+2,17,0,Math.PI*2);c.fillStyle='#090f0b';c.fill();
  }
  for(const x of [205,330,455,705,830,955])for(const y of [59,601]){c.save();c.translate(x,y);c.rotate(Math.PI/4);c.fillStyle='#c8b78b';c.fillRect(-2,-2,4,4);c.restore();}
  for(const y of [205,330,455])for(const x of [59,1101]){c.save();c.translate(x,y);c.rotate(Math.PI/4);c.fillStyle='#c8b78b';c.fillRect(-2,-2,4,4);c.restore();}
  c.fillStyle='#d4ddba28';c.font='12px Segoe UI';c.textAlign='center';c.fillText('F L Y   /   P O O L',580,470);
}
paintTableBackground();
function drawTable(){
  const c=ctx;c.clearRect(0,0,1160,660);c.drawImage(backdrop,0,0);
  if(!state)return;
  renderFrame=frameBuffer.sample(performance.now());
  const g=renderFrame?{...state.game,phase:renderFrame.phase,turn:renderFrame.turn,
    balls:renderFrame.balls.map((b,n)=>({number:n,x:b[0],y:b[1],vx:b[2],vy:b[3],pocketed:!!b[4]}))}:state.game;
  const cue=g.balls[0];
  if(g.phase==='aim'&&!cue.pocketed){
    const fly=g.turn==='fly',a=fly?(renderFrame?.body[0]??state.brain?.body.angle??0):angle*Math.PI/180,p=fly?(renderFrame?.body[1]??state.brain?.body.power??.5):power;
    const x=cue.x+80,y=cue.y+80,dx=Math.cos(a),dy=Math.sin(a);
    c.save();c.beginPath();c.rect(80,80,1000,500);c.clip();
    if(!fly){
      const guide=aimGuide(g.balls,a),gx=guide.contact.x+80,gy=guide.contact.y+80;
      c.setLineDash([7,7]);c.lineWidth=1.6;c.strokeStyle='#eeecd9a8';c.beginPath();c.moveTo(x+dx*16,y+dy*16);c.lineTo(gx,gy);c.stroke();c.setLineDash([]);
      c.beginPath();c.arc(gx,gy,11,0,Math.PI*2);c.fillStyle='#f2f0d51c';c.fill();c.strokeStyle='#e9e7cfb0';c.lineWidth=1.2;c.stroke();
      if(guide.target){
        const tx=guide.target.x+80,ty=guide.target.y+80,ex=guide.objectEnd.x+80,ey=guide.objectEnd.y+80;
        c.strokeStyle='#e8c780';c.lineWidth=2.1;c.beginPath();c.moveTo(tx,ty);c.lineTo(ex,ey);c.stroke();
        const aa=Math.atan2(ey-ty,ex-tx);c.beginPath();c.moveTo(ex-9*Math.cos(aa-.42),ey-9*Math.sin(aa-.42));c.lineTo(ex,ey);c.lineTo(ex-9*Math.cos(aa+.42),ey-9*Math.sin(aa+.42));c.stroke();
        c.setLineDash([3,6]);c.lineWidth=1;c.strokeStyle='#eee9ce66';c.beginPath();c.moveTo(gx,gy);c.lineTo(guide.cueEnd.x+80,guide.cueEnd.y+80);c.stroke();c.setLineDash([]);
      }
    }
    const pull=drag?p*92:p*17;
    c.lineCap='round';c.lineWidth=6;c.strokeStyle='#c7a877';c.beginPath();c.moveTo(x-dx*(24+pull),y-dy*(24+pull));c.lineTo(x-dx*(162+pull),y-dy*(162+pull));c.stroke();
    c.lineWidth=3;c.strokeStyle='#83a8ab';c.beginPath();c.moveTo(x-dx*(21+pull),y-dy*(21+pull));c.lineTo(x-dx*(26+pull),y-dy*(26+pull));c.stroke();
    if(drag){c.fillStyle='#e9d390';c.font='bold 14px Segoe UI';c.textAlign='center';c.fillText(`${Math.round(p*100)}%`,x+dy*30,y-dx*30);}
    if(fly){
      const hx=x-dx*(142+p*17),hy=y-dy*(142+p*17);c.fillStyle='#e6cc89';c.beginPath();c.arc(hx,hy,7,0,Math.PI*2);c.fill();c.lineWidth=3;c.strokeStyle='#dbbf7d';c.beginPath();c.moveTo(hx,hy);c.lineTo(hx-dx*20+dy*23,hy-dy*20-dx*23);c.lineTo(hx-dx*43,hy-dy*43);c.stroke();c.beginPath();c.arc(hx-dx*45,hy-dy*45,13,0,Math.PI*2);c.stroke();
    }c.restore();
  }
  for(const b of g.balls){if(!b.pocketed)ball(c,b,b.x+80,b.y+80);}
  if(placing){c.strokeStyle='#edeac3';c.lineWidth=2;c.setLineDash([3,4]);c.beginPath();c.arc(cue.x+80,cue.y+80,21,0,Math.PI*2);c.stroke();c.setLineDash([]);}
}
function drawBody(){
  const c=bodyCtx,w=540,h=220;c.clearRect(0,0,w,h);
  const b=state?.brain?.body,p=b?.power||.48,a=b?.angle||0;
  c.strokeStyle='#dfe4d5';c.lineWidth=1;for(let x=20;x<w;x+=25){c.beginPath();c.moveTo(x,12);c.lineTo(x,h-15);c.stroke();}for(let y=12;y<h;y+=25){c.beginPath();c.moveTo(20,y);c.lineTo(w-20,y);c.stroke();}
  const elbow=[205+Math.sin(a)*28,105],wrist=[325-p*58,138];
  c.strokeStyle='#687f5c';c.lineWidth=9;c.lineJoin='round';c.lineCap='round';c.beginPath();c.moveTo(112,61);c.lineTo(152,117);c.lineTo(...elbow);c.lineTo(...wrist);c.stroke();
  c.beginPath();c.moveTo(152,117);c.lineTo(118,177);c.lineTo(91,186);c.moveTo(152,117);c.lineTo(183,177);c.lineTo(215,186);c.stroke();
  c.fillStyle='#e8eadc';c.strokeStyle='#8b9c78';c.lineWidth=3;c.beginPath();c.ellipse(111,48,26,19,-.35,0,Math.PI*2);c.fill();c.stroke();
  for(const [x,y] of [[152,117],elbow,wrist]){c.beginPath();c.arc(x,y,7,0,Math.PI*2);c.fillStyle='#d6b971';c.fill();c.strokeStyle='#eee8d1';c.lineWidth=2;c.stroke();}
  c.lineWidth=5;c.strokeStyle='#b8975f';c.beginPath();c.moveTo(wrist[0]-70,145);c.lineTo(wrist[0]+150,145);c.stroke();
  c.fillStyle='#628574';c.fillRect(wrist[0]+149,141,7,8);ball(c,{number:0},454,145,13);
  c.strokeStyle='#a9b795';c.lineWidth=1;c.setLineDash([3,5]);c.beginPath();c.moveTo(30,198);c.lineTo(510,198);c.stroke();c.setLineDash([]);
}
function drawRates(data){
  const c=$('rates').getContext('2d'),w=1000,h=260;c.clearRect(0,0,w,h);const left=52,right=975,top=25,bottom=213;
  let max=50;for(const d of data)max=Math.max(max,d.hz,d.pam,d.motor);max=Math.ceil(max/50)*50;
  c.font='16px Segoe UI';c.textAlign='right';
  for(let i=0;i<=4;i++){const y=bottom-(bottom-top)*i/4;c.strokeStyle='#dce1d3';c.lineWidth=1;c.beginPath();c.moveTo(left,y);c.lineTo(right,y);c.stroke();c.fillStyle='#89967c';c.fillText(Math.round(max*i/4),left-10,y+5);}
  for(const [key,color] of [['hz','#c5a253'],['pam','#599e94'],['motor','#8b8ad0']]){c.strokeStyle=color;c.lineWidth=2.5;c.beginPath();data.forEach((d,i)=>{const x=left+(right-left)*i/Math.max(1,data.length-1),y=bottom-d[key]/max*(bottom-top);i?c.lineTo(x,y):c.moveTo(x,y);});c.stroke();}
  c.textAlign='left';c.fillStyle='#8a957d';c.fillText('Hz',left,18);if(data.length){c.font='14px Segoe UI';c.fillText(`${data[0].t.toFixed(1)} s neurali`,left,244);c.textAlign='right';c.fillText(`${data.at(-1).t.toFixed(1)} s`,right,244);}
}

class BrainView {
  constructor(canvas,raw){
    this.canvas=canvas;this.yaw=.05;this.pitch=.35;this.drag=null;this.moved=false;this.n=raw.length/3;
    let lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity],known=0;
    for(let i=0;i<raw.length;i+=3)if(Number.isFinite(raw[i])&&Number.isFinite(raw[i+1])&&Number.isFinite(raw[i+2])){known++;for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],raw[i+j]);hi[j]=Math.max(hi[j],raw[i+j]);}}
    const scale=Math.max(...hi.map((v,j)=>v-lo[j]))/2;this.xyz=new Float32Array(raw.length);
    for(let i=0;i<raw.length;i+=3)for(let j=0;j<3;j++)this.xyz[i+j]=Number.isFinite(raw[i+j])?(raw[i+j]-(lo[j]+hi[j])/2)/scale:999;
    text('coordinate-count',`${fmt(known)} somi localizzati / ${fmt(this.n)} neuroni simulati`);
    const gl=canvas.getContext('webgl',{alpha:false,antialias:true});this.gl=gl;
    if(!gl){text('coordinate-count',`WebGL non disponibile · ${fmt(this.n)} neuroni continuano a essere simulati`);return;}
    const vs=`attribute vec3 p;attribute float s;uniform float yaw;uniform float pitch;uniform float aspect;varying float glow;void main(){float x=p.x*cos(yaw)+p.z*sin(yaw);float z=-p.x*sin(yaw)+p.z*cos(yaw);float y=p.y*cos(pitch)-z*sin(pitch);z=p.y*sin(pitch)+z*cos(pitch);float depth=2.6-z*.35;gl_Position=vec4(x*2.5/depth/aspect,-y*2.5/depth,0.,1.);gl_PointSize=s>0.?2.2+min(s*.18,2.8):1.2;glow=min(s/5.,1.);}`;
    const fs=`precision mediump float;varying float glow;void main(){float d=length(gl_PointCoord-vec2(.5));if(d>.5)discard;vec3 col=mix(vec3(.19,.32,.24),vec3(1.,.78,.36),glow);gl_FragColor=vec4(col,mix(.20,.85,glow)*(1.-d));}`;
    const shader=(type,source)=>{const v=gl.createShader(type);gl.shaderSource(v,source);gl.compileShader(v);if(!gl.getShaderParameter(v,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(v));return v;};
    this.program=gl.createProgram();gl.attachShader(this.program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(this.program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(this.program);if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw Error('Impossibile inizializzare la mappa neurale');gl.useProgram(this.program);
    const pbuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,pbuffer);gl.bufferData(gl.ARRAY_BUFFER,this.xyz,gl.STATIC_DRAW);const loc=gl.getAttribLocation(this.program,'p');gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,3,gl.FLOAT,false,0,0);
    this.sbuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.sbuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(this.n),gl.DYNAMIC_DRAW);const sloc=gl.getAttribLocation(this.program,'s');gl.enableVertexAttribArray(sloc);gl.vertexAttribPointer(sloc,1,gl.FLOAT,false,0,0);
    this.yawLoc=gl.getUniformLocation(this.program,'yaw');this.pitchLoc=gl.getUniformLocation(this.program,'pitch');this.aspectLoc=gl.getUniformLocation(this.program,'aspect');gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
    canvas.addEventListener('pointerdown',e=>{this.drag=[e.clientX,e.clientY];this.moved=false;canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointermove',e=>{if(!this.drag)return;const dx=e.clientX-this.drag[0],dy=e.clientY-this.drag[1];if(Math.abs(dx)+Math.abs(dy)>2)this.moved=true;this.yaw+=dx*.009;this.pitch+=dy*.009;this.drag=[e.clientX,e.clientY];brainDirty=true;});
    canvas.addEventListener('pointerup',e=>{if(!this.moved)this.pick(e);this.drag=null;});
    canvas.addEventListener('pointercancel',()=>{this.drag=null;});
  }
  setActivity(counts){if(!this.gl||counts.length!==this.n)return;const gl=this.gl;gl.bindBuffer(gl.ARRAY_BUFFER,this.sbuffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(counts),gl.DYNAMIC_DRAW);brainDirty=true;}
  draw(){
    const gl=this.gl;if(!gl)return;
    const ratio=Math.min(devicePixelRatio||1,2),w=Math.round(this.canvas.clientWidth*ratio),h=Math.round(this.canvas.clientHeight*ratio);
    if(this.canvas.width!==w||this.canvas.height!==h){this.canvas.width=w;this.canvas.height=h;}
    gl.viewport(0,0,w,h);gl.clearColor(.071,.145,.118,1);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(this.program);gl.uniform1f(this.yawLoc,this.yaw);gl.uniform1f(this.pitchLoc,this.pitch);gl.uniform1f(this.aspectLoc,w/h);gl.drawArrays(gl.POINTS,0,this.n);
  }
  async pick(e){
    const rect=this.canvas.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*2-1,py=1-(e.clientY-rect.top)/rect.height*2;
    const cy=Math.cos(this.yaw),sy=Math.sin(this.yaw),cx=Math.cos(this.pitch),sx=Math.sin(this.pitch),aspect=rect.width/rect.height;
    let best=.0015,index=-1;for(let i=0;i<this.n;i++){const p=this.xyz.subarray(i*3,i*3+3);if(p[0]>900)continue;const x=p[0]*cy+p[2]*sy,z=-p[0]*sy+p[2]*cy,y=p[1]*cx-z*sx,zz=p[1]*sx+z*cx,depth=2.6-zz*.35;const d=(x*2.5/depth/aspect-px)**2+(-y*2.5/depth-py)**2;if(d<best){best=d;index=i;}}
    if(index>=0){try{const n=await json(`/api/neuron/${index}`);text('neuron-detail',`${n.type||'Tipo non annotato'} · ${n.side||'—'}\nID ${n.id}\n${n.spikes} spike / ${n.window_ms} ms · ${(n.spikes*1000/n.window_ms).toFixed(0)} Hz`);$('neuron-detail').style.whiteSpace='pre-line';$('neuron-detail').hidden=false;}catch(e){toast(e.message);}}
  }
}

async function loadBrain(){
  loadingPoints=true;
  try{const r=await fetch('/api/positions');if(!r.ok)throw Error('Anatomia ancora in caricamento');positions=new Float32Array(await r.arrayBuffer());brainView=new BrainView($('brain'),positions);if(activity)brainView.setActivity(activity);}catch(e){text('coordinate-count',e.message);}finally{loadingPoints=false;}
}
function connectStream(){
  if(!token||document.hidden||stopPolling)return;
  if(stream&&streamToken===token)return;
  stream?.close();streamToken=token;stream=new EventSource(`/api/stream?token=${encodeURIComponent(token)}`);
  stream.onmessage=e=>{
    const packet=JSON.parse(e.data);if(!packet.frames?.length)return;
    streamed=true;lastStream=performance.now();frameBuffer.push(packet.frames,lastStream);
    const f=packet.frames.at(-1);if(!state||state.phase!=='ready')return;
    const changed=state.game.phase!==f.phase||state.game.turn!==f.turn||state.game.shot_id!==f.shot||state.paused!==f.paused;
    Object.assign(state.game,{phase:f.phase,turn:f.turn,shot_id:f.shot,game_number:f.game,ball_in_hand:f.hand,
      balls:f.balls.map((b,n)=>({number:n,x:b[0],y:b[1],vx:b[2],vy:b[3],pocketed:!!b[4]}))});
    state.paused=f.paused;
    if(state.brain){state.brain.body.angle=f.body[0];state.brain.body.power=f.body[1];}
    if(changed){if(drag&&!humanTurn())cancelDrag();update();}
  };
  stream.onerror=()=>{streamed=false;if(performance.now()-lastStream>5000){stream?.close();stream=null;token=null;}};
}
const visibility=new IntersectionObserver(entries=>{
  for(const entry of entries){
    const v=entry.isIntersecting;
    if(entry.target===table)tableVisible=v;
    if(entry.target===$('brain')){brainVisible=v;if(v){brainDirty=true;if(!positions&&!loadingPoints&&state?.phase==='ready')loadBrain();}}
    if(entry.target===$('body'))bodyVisible=v;
    if(entry.target===$('eye'))visionVisible=v;
    if(entry.target===$('rates'))ratesVisible=v;
  }
},{rootMargin:'80px'});
for(const id of ['table','brain','body','eye','rates'])visibility.observe($(id));
new ResizeObserver(()=>{brainDirty=true;}).observe($('brain'));
document.addEventListener('visibilitychange',()=>{if(document.hidden){stream?.close();stream=null;}else{connectStream();brainDirty=true;}});
async function pollState(){
  if(stopPolling)return;
  try{if(!token||!connected){const boot=await json('/api/bootstrap');token=boot.token;state=boot.state;}else state=await json('/api/state');stateTime=performance.now();connected=true;if(state.build&&parseInt(state.build.split('-').at(-1))>parseInt(BUILD.split('-').at(-1))){location.reload();return;}connectStream();update();}
  catch(e){connected=false;text('connection','Connessione interrotta');$('shoot').disabled=true;}
  setTimeout(pollState,document.hidden?1500:500);
}
async function pollNeural(){
  if(stopPolling)return;
  if(state?.phase==='ready'&&!document.hidden){
    const results=await Promise.allSettled([visionVisible?json('/api/vision'):Promise.resolve(null),brainVisible?fetch('/api/activity').then(async r=>{if(!r.ok)throw Error('Attività non disponibile');return new Uint16Array(await r.arrayBuffer());}):Promise.resolve(null)]);
    if(results[0].status==='fulfilled'){
      const v=results[0].value;if(v){for(const [id,key] of [['eye','eye'],['eye-left','left'],['eye-right','right']])if(v[key])$(id).src=`data:image/jpeg;base64,${v[key]}`;
      if(v.summary){text('r1',fmt(v.summary.stimulated_r1r6));text('r8',fmt(v.summary.stimulated_r8));text('motion',v.summary.motion_energy.toFixed(4));}}
    }
    if(results[1].status==='fulfilled'&&results[1].value){activity=results[1].value;brainView?.setActivity(activity);}
  }
  setTimeout(pollNeural,600);
}
let lastBodyDraw=0,lastFrameTime=0,metricsStart=0,framesDrawn=0,frameDurations=[],drawDurations=[];
function animate(now){
  if(stopPolling)return;
  if(!document.hidden){
    const begin=performance.now();
    if(tableVisible)drawTable();
    if(bodyVisible&&now-lastBodyDraw>90){drawBody();lastBodyDraw=now;}
    if(brainVisible&&brainDirty){brainView?.draw();brainDirty=false;}
    if(lastFrameTime&&now-lastFrameTime<1000)frameDurations.push(now-lastFrameTime);
    drawDurations.push(performance.now()-begin);framesDrawn++;lastFrameTime=now;
    if(!metricsStart)metricsStart=now;
    if(now-metricsStart>=5000&&token){
      const sorted=frameDurations.slice().sort((a,b)=>a-b),draws=drawDurations.slice().sort((a,b)=>a-b);
      const metrics={build:BUILD,fps:Math.round(framesDrawn*1000/(now-metricsStart)),frame_p95_ms:sorted[Math.floor(sorted.length*.95)]||0,
        draw_p95_ms:draws[Math.floor(draws.length*.95)]||0,stream_age_ms:Math.max(0,performance.now()-lastStream),table_visible:tableVisible,brain_visible:brainVisible};
      text('render-health',`${metrics.fps} FPS`);
      fetch('/api/client-metrics',{method:'POST',headers:{'Content-Type':'application/json','X-Biliardo-Token':token},body:JSON.stringify(metrics)}).catch(()=>{});
      framesDrawn=0;frameDurations=[];drawDurations=[];metricsStart=now;
    }
  }else{lastFrameTime=metricsStart=0;framesDrawn=0;frameDurations=[];drawDurations=[];}
  requestAnimationFrame(animate);
}

// Optional imperative WebMCP tools share the same validation and visible actions.
const registry=document.modelContext,lifecycle=new AbortController();
if(registry?.registerTool){
  const register=tool=>{try{Promise.resolve(registry.registerTool(tool,{signal:lifecycle.signal})).catch(e=>console.warn('WebMCP',e));}catch(e){console.warn('WebMCP',e);}};
  register({name:'read_pool_state',title:'Leggi partita e cervello',description:'Legge turno, palle, ricompense e attività neurale della sessione locale.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:false},execute:async()=>{const s=await json('/api/state');return {phase:s.phase,paused:s.paused,game:s.game,brain:s.brain};}});
  register({name:'shoot_human_cue',title:'Esegui il tiro del giocatore',description:'Completa un tiro umano in questa partita con direzione in gradi e forza da 0.03 a 1. Non sceglie la mira della mosca.',inputSchema:{type:'object',properties:{degrees:{type:'number',minimum:0,maximum:359},power:{type:'number',minimum:.03,maximum:1}},required:['degrees','power'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute:async input=>{if(!input||Object.keys(input).some(k=>!['degrees','power'].includes(k))||!Number.isFinite(input.degrees)||input.degrees<0||input.degrees>359||!Number.isFinite(input.power)||input.power<.03||input.power>1)throw Error('Direzione e forza non valide');setAngle(input.degrees);setPower(input.power);await command('shoot',{angle:input.degrees*Math.PI/180,power:input.power});return {shot:state.game.shot_id,phase:state.game.phase};}});
  register({name:'save_pool_memory',title:'Salva memoria completa',description:'Avvia un salvataggio locale del cervello, del corpo e del tavolo. Restituisce il file solo a scrittura completata.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute:async()=>{await command('save');for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,500));const s=await json('/api/state');if(s.command?.file&&s.command.ok){state=s;update();return {file:s.command.file,saved_at:s.saved_at};}if(s.command?.ok===false)throw Error(s.command.message);}throw Error('Salvataggio ancora in corso: controllare Archivio');}});
}
window.addEventListener('pagehide',()=>{stopPolling=true;stream?.close();visibility.disconnect();lifecycle.abort();});
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
setAngle(0);setPower(0);pollState();pollNeural();requestAnimationFrame(animate);
