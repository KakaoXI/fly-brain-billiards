from pathlib import Path
import copy
import hashlib
import json
import math
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path=None):
    path = Path(path or ROOT / 'config/config.yaml')
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
    for key in ['capture_fps', 'brain_speed', 'control_rate', 'max_key_hold_time', 'checkpoint_interval', 'neural_dt_ms']:
        value = cfg[key]
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} deve essere un numero positivo finito')
    if not 1 <= cfg['capture_fps'] <= 60 or not .1 <= cfg['neural_dt_ms'] <= 1:
        raise ValueError('capture_fps: 1–60; neural_dt_ms: 0.1–1')
    if cfg['adapter'] not in ['studio', 'generic']:
        raise ValueError('adapter deve essere studio o generic')
    if len(cfg['retina_resolution']) != 2 or min(cfg['retina_resolution']) < 16:
        raise ValueError('retina_resolution non valida')
    for key in ['learning_rate','background_drive','lamina_bias','retina_current','dopamine_current']:
        if not math.isfinite(cfg[key]) or cfg[key]<0:raise ValueError(f'{key}: valore finito non negativo richiesto')
    for key,value in cfg['motor_thresholds'].items():
        if not math.isfinite(value) or value<=0:raise ValueError(f'Soglia motoria {key} non valida')
    if cfg.get('imitation_enabled'):raise ValueError('La calibrazione per imitazione e disponibile solo offline: analyze.bat --imitation')
    if cfg['max_session_mb']<1:raise ValueError('max_session_mb deve essere almeno 1')
    if cfg['capture_fps']/cfg['brain_speed']>1000/cfg['neural_dt_ms']:
        raise ValueError('brain_speed produce intervalli inferiori al passo neurale')
    for roi in [cfg['generic'].get('health_roi'),*[t.get('roi') for t in cfg['generic'].get('templates',[])]]:
        if roi is None:continue
        if len(roi)!=4 or not all(math.isfinite(v) for v in roi) or min(roi)<0 or min(roi[2:])<=0 or roi[0]+roi[2]>1 or roi[1]+roi[3]>1:
            raise ValueError('ROI generica: [x,y,w,h] normalizzata entro 0..1')
    return copy.deepcopy(cfg)


def signature(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, allow_nan=False).encode()).hexdigest()
