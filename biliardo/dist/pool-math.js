// Human-only geometric aiming aid. Served as JavaScript on Windows, too.
const TAU=Math.PI*2, R=11;
export function wrapAngle(a){return (a%TAU+TAU)%TAU;}
export function pullPower(start,point,angle){return Math.max(0,Math.min(1,((start.x-point.x)*Math.cos(angle)+(start.y-point.y)*Math.sin(angle))/160));}
function railDistance(x,y,dx,dy){
  const values=[];
  if(dx>1e-9)values.push((1000-R-x)/dx);else if(dx< -1e-9)values.push((R-x)/dx);
  if(dy>1e-9)values.push((500-R-y)/dy);else if(dy< -1e-9)values.push((R-y)/dy);
  return Math.max(0,Math.min(...values.filter(v=>v>=0)));
}
export function aimGuide(balls,angle){
  const cue=balls[0],dx=Math.cos(angle),dy=Math.sin(angle);let distance=railDistance(cue.x,cue.y,dx,dy),target=null;
  for(const b of balls){
    if(!b.number||b.pocketed)continue;
    const ox=b.x-cue.x,oy=b.y-cue.y,along=ox*dx+oy*dy,perp=ox*ox+oy*oy-along*along;
    if(along<=0||perp>4*R*R)continue;
    const hit=along-Math.sqrt(Math.max(0,4*R*R-perp));
    if(hit>=0&&hit<distance){distance=hit;target=b;}
  }
  const contact={x:cue.x+dx*distance,y:cue.y+dy*distance};
  if(!target)return {contact,target:null,distance};
  const nx=(target.x-contact.x)/(2*R),ny=(target.y-contact.y)/(2*R),dot=Math.max(0,dx*nx+dy*ny);
  const length=Math.min(280,railDistance(target.x,target.y,nx,ny)*.55);
  const tangent={x:dx-dot*nx,y:dy-dot*ny};
  return {contact,target,distance,objectEnd:{x:target.x+nx*length,y:target.y+ny*length},
    cueEnd:{x:contact.x+tangent.x*160,y:contact.y+tangent.y*160}};
}

// Render past authoritative physics samples, not extrapolated independent balls.
// At collisions the source contains the actual 240 Hz contact positions.
export class FrameBuffer {
  constructor(delay=65){this.frames=[];this.offset=null;this.delay=delay;this.received=0;this.gaps=0;this.epoch=null;}
  push(batch,now){
    if(!batch.length)return;
    if(batch.at(-1).epoch!==this.epoch){this.frames=[];this.offset=null;this.epoch=batch.at(-1).epoch;}
    const estimate=now-batch.at(-1).t;
    this.offset=this.offset===null?estimate:Math.min(this.offset+.04,estimate);
    for(const frame of batch){if(!this.frames.length||frame.id>this.frames.at(-1).id)this.frames.push(frame);}
    this.frames=this.frames.slice(-400);this.received+=batch.length;
  }
  sample(now){
    if(!this.frames.length)return null;
    const t=now-this.offset-this.delay;
    while(this.frames.length>2&&this.frames[1].t<=t)this.frames.shift();
    const a=this.frames[0],b=this.frames[1]||a;
    if(a.game!==b.game||a.shot!==b.shot||b.t<=a.t)return t>=b.t?b:a;
    const f=Math.max(0,Math.min(1,(t-a.t)/(b.t-a.t)));
    return {...a,body:a.body.map((v,i)=>i===0?v+Math.atan2(Math.sin(b.body[i]-v),Math.cos(b.body[i]-v))*f:v+(b.body[i]-v)*f),
      balls:a.balls.map((ball,i)=>ball.map((v,j)=>j<2?v+(b.balls[i][j]-v)*f:j===4?(f===1?b.balls[i][j]:v):v))};
  }
}
