"""LIF on all retained MaleCNS edges, NVRTC GPU kernels, persistent state.

Compact-spike kernel is reused unmodified from FastFly. Integration/FP32
propagation here are explicit FLYBLOX adaptations, not the original benchmark.
"""
import hashlib
import json
import math
import os
import time
import numpy as np
from flyblox.config import ROOT, signature
from .plasticity import Plasticity

os.environ.setdefault('CUPY_CACHE_DIR', str(ROOT / 'data/cupy_cache'))

CUDA = r'''
extern "C" __global__ void integrate(float* v,float* g,float* adapt,float* mod,
 int* refractory,float* incoming,float* mincoming,const float* drive,
 const float* rest,const unsigned char* kc,unsigned int* bits,int* counts,
 int n,int words,float dt,float noise,unsigned int seed,unsigned int tick) {
 int i=blockIdx.x*blockDim.x+threadIdx.x; bool spike=false;
 if(i<n){
  g[i]=g[i]*expf(-dt/5.0f)+incoming[i]; incoming[i]=0;
  mod[i]=mod[i]*expf(-dt/100.0f)+mincoming[i]; mincoming[i]=0;
  adapt[i]*=expf(-dt/200.0f);
  if(refractory[i]>0){refractory[i]--;v[i]=rest[i];}
  else{
   unsigned int h=i^(tick*2654435761u)^(seed*1664525u);
   h^=h>>16;h*=0x45d9f3bu;h^=h>>16;
   float z=noise*((float)(h&65535)/32768.0f-1.0f);
   v[i]+=(rest[i]-v[i]+g[i]+drive[i]-adapt[i]+z)*(1-expf(-dt/20.0f));
   spike=v[i]>=-45.0f;
   if(spike){v[i]=rest[i];refractory[i]=(int)ceilf(2.2f/dt);counts[i]++;if(kc[i])adapt[i]+=8.0f;}
  }
 }
 unsigned int b=__ballot_sync(0xffffffff,spike);
 if((threadIdx.x&31)==0){int w=i>>5;if(w<words)bits[w]=b;}
}
extern "C" __global__ void propagate(const unsigned int* spikes,const unsigned int* count,
 const long long* ptr,const int* post,const float* weight,const unsigned char* modulator,
 float* incoming,float* mincoming){
 unsigned int warp=(blockIdx.x*blockDim.x+threadIdx.x)>>5;
 unsigned int stride=(gridDim.x*blockDim.x)>>5,lane=threadIdx.x&31;
 for(unsigned int s=warp;s<*count;s+=stride){
  unsigned int i=spikes[s];
  for(long long e=ptr[i]+lane;e<ptr[i+1];e+=32){
   if(modulator[i])atomicAdd(&mincoming[post[e]],fabsf(weight[e]));
   else atomicAdd(&incoming[post[e]],weight[e]);
  }
 }
}
extern "C" __global__ void gather(const unsigned int* bits,const long long* ptr,
 const int* pre,const long long* edge,const float* weight,const unsigned char* modulator,
 float* incoming,float* mincoming,int n){
 int i=blockIdx.x*blockDim.x+threadIdx.x;
 if(i>=n)return;
 float fast=0,slow=0;
 for(long long j=ptr[i];j<ptr[i+1];j++){
  int p=pre[j];
  if(bits[p>>5]&(1u<<(p&31))){
   if(modulator[p])slow+=fabsf(weight[edge[j]]);else fast+=weight[edge[j]];
  }
 }
 incoming[i]+=fast;mincoming[i]+=slow;
}
'''


class Brain:
    MODEL = 'flyblox-malecns-lif-v1'

    def __init__(self, graph, cfg):
        import cupy as cp
        from flywire_sim import compile_kernels
        self.cp, self.graph, self.cfg = cp, graph, cfg
        self.dt = float(cfg['neural_dt_ms'])
        self.n = graph.n
        self.words = (self.n + 31) // 32
        self.delay = max(1, math.ceil(1.8 / self.dt))
        self.ring_length = self.delay + 1
        module = cp.RawModule(code=CUDA)
        self.integrate = module.get_function('integrate')
        self.propagate = module.get_function('propagate')
        self.gather = module.get_function('gather')
        self.compact = compile_kernels()['compact']
        self.ptr, self.post = cp.asarray(graph.ptr), cp.asarray(graph.post)
        if cfg.get('deterministic',False):
            order=np.argsort(graph.post,kind='stable')
            pre=np.repeat(np.arange(graph.n,dtype=np.int32),np.diff(graph.ptr))
            self.inverse_ptr=cp.asarray(np.r_[0,np.cumsum(np.bincount(graph.post,minlength=graph.n))].astype(np.int64))
            self.inverse_pre=cp.asarray(pre[order]);self.inverse_edges=cp.asarray(order.astype(np.int64))
        self.weight = cp.asarray(graph.weight)
        self.corrected_edges = []
        if cfg.get('r8_ame12_sign_override', False):
            for i in np.flatnonzero(np.char.startswith(graph.types, 'R8')):
                edges = np.arange(graph.ptr[i], graph.ptr[i+1])
                selected = edges[graph.types[graph.post[edges]] == 'aMe12']
                self.corrected_edges.extend(selected.tolist())
            ix = cp.asarray(self.corrected_edges, dtype=cp.int64)
            self.weight[ix] = cp.abs(self.weight[ix])
        self.modulator = cp.asarray(graph.modulator)
        self.kc = cp.asarray(graph.circuit['kc_mask'])
        rest = np.full(self.n, -52, np.float32)
        rest[graph.circuit['kc']] = -60
        self.rest = cp.asarray(rest)
        self.v = self.rest.copy()
        self.g = cp.zeros(self.n, cp.float32)
        self.adapt = cp.zeros_like(self.g)
        self.mod = cp.zeros_like(self.g)
        self.refractory = cp.zeros(self.n, cp.int32)
        self.ring = cp.zeros((self.ring_length, self.n), cp.float32)
        self.mod_ring = cp.zeros_like(self.ring)
        self.drive = cp.zeros_like(self.g)
        self.bits = cp.zeros(self.words, cp.uint32)
        self.spikes = cp.zeros(self.n, cp.uint32)
        self.nspikes = cp.zeros(1, cp.uint32)
        self.counts = cp.zeros(self.n, cp.int32)
        self.light = np.zeros(len(graph.retina), np.float32)
        self.color = np.zeros(len(graph.r8), np.float32)
        self.memory = Plasticity(graph, cfg['learning_rate'])
        self.plastic_indices = cp.asarray(graph.circuit['edges'])
        self.tick, self.total_spikes = 0, 0
        self.pulses = {'reward': 0.0, 'aversive': 0.0}
        self.last_counts = np.zeros(self.n, np.int32)
        model_sources=['flyblox/brain/runtime.py','flyblox/brain/plasticity.py','flyblox/brain/connectome.py',
                       'flyblox/control/decoder.py','flyblox/vision/retina.py','external/stonkfly/stonkfly/neural/rule.py']
        self.model_hash = hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in model_sources)).hexdigest()

    @property
    def sim_ms(self):
        return self.tick * self.dt

    def reinforce(self, value):
        if value:
            key = 'reward' if value > 0 else 'aversive'
            self.pulses[key] = max(self.pulses[key], self.sim_ms + self.cfg['dopamine_pulse_ms'] * min(abs(value), 2))

    def clear_reward(self):
        self.pulses = {'reward': 0.0, 'aversive': 0.0}

    def step(self, luminance, color, duration_ms, learning=False):
        cp = self.cp
        start = time.perf_counter()
        remaining = max(1, round(duration_ms / self.dt))
        total = np.zeros(self.n, np.int32)
        while remaining:
            ticks = min(remaining, max(1, int(10 / self.dt)))
            interval = ticks * self.dt
            self.light += (1 - math.exp(-interval / 10)) * (luminance - self.light)
            self.color += (1 - math.exp(-interval / 10)) * (color - self.color)
            drive = np.zeros(self.n, np.float32)
            drive[self.graph.lamina] = self.cfg['lamina_bias']
            drive[self.graph.retina] += self.cfg['retina_current'] * self.light / (.02 + self.light)
            drive[self.graph.r8] += self.cfg['retina_current'] * self.color / (.02 + self.color)
            for key, end in self.pulses.items():
                if self.sim_ms < end:
                    drive[self.graph.circuit[key]] += self.cfg['dopamine_current']
            self.drive.set(drive)
            self.counts.fill(0)
            for _ in range(ticks):
                slot = self.tick % self.ring_length
                target = (self.tick + self.delay) % self.ring_length
                self.integrate(((self.n+255)//256,), (256,),
                    (self.v,self.g,self.adapt,self.mod,self.refractory,self.ring[slot],self.mod_ring[slot],
                     self.drive,self.rest,self.kc,self.bits,self.counts,np.int32(self.n),np.int32(self.words),
                     np.float32(self.dt),np.float32(self.cfg['background_drive']),np.uint32(self.cfg['seed']),np.uint32(self.tick & 0xffffffff)))
                if self.cfg.get('deterministic',False):
                    self.gather(((self.n+127)//128,), (128,),
                        (self.bits,self.inverse_ptr,self.inverse_pre,self.inverse_edges,self.weight,self.modulator,self.ring[target],self.mod_ring[target],np.int32(self.n)))
                else:
                    self.nspikes.fill(0)
                    self.compact(((self.words+255)//256,), (256,),
                        (self.bits,self.spikes,self.nspikes,np.int32(self.words),np.int32(self.n)))
                    self.propagate((512,), (128,), (self.spikes,self.nspikes,self.ptr,self.post,self.weight,self.modulator,
                                                               self.ring[target],self.mod_ring[target]))
                self.tick += 1
            counts = self.counts.get()
            if learning:
                weights = self.memory.step(counts, interval / 1000, True)
                self.weight[self.plastic_indices] = cp.asarray(weights)
            total += counts
            remaining -= ticks
        self.last_counts = total
        self.total_spikes += int(total.sum())
        return total, time.perf_counter() - start

    def reset_state(self):
        self.v[:] = self.rest
        for a in [self.g,self.adapt,self.mod,self.refractory,self.ring,self.mod_ring,self.drive,self.counts]:
            a.fill(0)
        self.light.fill(0); self.color.fill(0); self.last_counts=np.zeros(self.n,np.int32)
        self.tick = self.total_spikes = 0
        self.clear_reward()
        self.memory.kc_trace.fill(0); self.memory.dan_trace.fill(0)

    def reset_learning(self):
        self.memory.reset()
        self.weight[self.plastic_indices] = self.cp.asarray(self.memory.baseline)
        self.clear_reward()

    def save(self, path, extra):
        from pathlib import Path
        path = Path(path)
        metadata = {'model': self.MODEL, 'model_hash': self.model_hash, 'graph': self.graph.hash,
                    'configuration': self.cfg, 'config_hash': signature(self.cfg), 'tick': self.tick,
                    'total_spikes': self.total_spikes, 'pulses': self.pulses, 'extra': extra}
        arrays = {k: getattr(self, k).get() for k in ['v','g','adapt','mod','refractory','ring','mod_ring']}
        arrays.update({k: getattr(self.memory,k) for k in ['kc_trace','dan_trace','u','w']})
        temporary = path.with_suffix('.partial')
        with temporary.open('wb') as stream:
            np.savez_compressed(stream, metadata=json.dumps(metadata),light=self.light,color=self.color,**arrays)
        temporary.replace(path)

    def load(self, path):
        with np.load(path, allow_pickle=False) as data:
            m = json.loads(str(data['metadata']))
            if any(m.get(k) != v for k,v in {'model':self.MODEL,'model_hash':self.model_hash,'graph':self.graph.hash,'config_hash':signature(self.cfg)}.items()):
                raise ValueError('Checkpoint incompatibile con modello, dataset o configurazione')
            targets = {k:getattr(self,k) for k in ['v','g','adapt','mod','refractory','ring','mod_ring','light','color']}
            targets.update({k:getattr(self.memory,k) for k in ['kc_trace','dan_trace','u','w']})
            # Validate everything BEFORE modifying any live state.
            for k,target in targets.items():
                a = data[k]
                if a.shape != target.shape or a.dtype != target.dtype or not np.isfinite(a).all():
                    raise ValueError(f'Stato checkpoint non valido: {k}')
            if m['tick'] < 0 or not np.all((data['w'] >= -.9-1e-6) & (data['w'] <= 1+1e-6)):
                raise ValueError('Limiti checkpoint non validi')
            for k,target in targets.items():
                if isinstance(target, np.ndarray): target[:] = data[k]
                else: target.set(data[k])
            self.tick,self.total_spikes,self.pulses = m['tick'],m['total_spikes'],m['pulses']
            self.weight[self.plastic_indices] = self.cp.asarray(self.memory.weights())
            return m['extra']


def Path_source_rule():
    from pathlib import Path
    return (ROOT / 'external/stonkfly/stonkfly/neural/rule.py').read_text()
