import numpy as np

ACTIONS=['FORWARD','BACKWARD','LEFT','RIGHT','JUMP']


class Decoder:
    def __init__(self,graph,cfg):
        self.graph,self.cfg=graph,cfg
        self.groups={}
        for action,names in cfg['motor_populations'].items():
            ix=graph.population(names, 'L' if action=='left' else 'R' if action=='right' else None)
            if len(ix)==0:raise ValueError(f'Popolazione motoria assente nel dataset: {action} {names}')
            self.groups[action]=ix
        self.ema={k:0.0 for k in self.groups}
        self.last_jump=-10.0

    def decode(self,counts,seconds,sim_seconds):
        for name,ix in self.groups.items():
            rate=float(np.mean(counts[ix]))/seconds
            alpha=1-np.exp(-seconds/.1)
            self.ema[name]+=alpha*(rate-self.ema[name])
        t=self.cfg['motor_thresholds']; r=self.ema
        forward=r['forward']>=t['forward'];back=r['backward']>=t['backward']
        if forward and back:
            forward=r['forward']/t['forward']>r['backward']/t['backward'];back=not forward
        turn=r['right']-r['left']
        jump=r['jump']>=t['jump'] and sim_seconds-self.last_jump>=.8
        if jump:self.last_jump=sim_seconds
        flags=[forward,back,turn<=-t['turn'],turn>=t['turn'],jump]
        return {'rates':dict(r),'flags':[int(v) for v in flags],
                'actions':[a for a,v in zip(ACTIONS,flags) if v] or ['IDLE'],
                'source':'fixed_neural_decoder','populations':{k:self.graph.cells(v) for k,v in self.groups.items()}}

    def state(self):return {'ema':self.ema.copy(),'last_jump':self.last_jump}
    def restore(self,state):self.ema=state['ema'].copy();self.last_jump=state['last_jump']
