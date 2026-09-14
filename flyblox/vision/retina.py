"""Pixels only. Hex-column projection inherited from MaleCNS import."""
import base64
import io
import numpy as np
from PIL import Image, ImageDraw


def jpeg(frame, quality=72):
    out = io.BytesIO()
    Image.fromarray(frame).save(out, format='JPEG', quality=quality)
    return base64.b64encode(out.getvalue()).decode()


class Retina:
    def __init__(self, graph, resolution):
        self.graph, self.resolution = graph, tuple(resolution)
        self.previous = None

    def transform(self, frame, mask_rect=None):
        # Optical telemetry is excluded to prevent reward/status leakage into vision.
        clean = frame.copy()
        if mask_rect:
            x,y,w,h = mask_rect
            clean[y:y+h,x:x+w] = 127
        small = np.asarray(Image.fromarray(clean).resize(self.resolution, Image.Resampling.BILINEAR))
        rgb = small.astype(np.float32) / 255
        linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb+.055)/1.055)**2.4)
        lum = linear @ np.array([.2126,.7152,.0722],np.float32)
        motion = np.zeros_like(lum) if self.previous is None else lum-self.previous
        # Temporal contrast is a motion proxy, not semantic detection or dense optical flow.
        self.previous = lum.copy()
        def sample(uv):
            return np.clip((uv[:,0]*(small.shape[1]-1)).astype(int),0,small.shape[1]-1), np.clip((uv[:,1]*(small.shape[0]-1)).astype(int),0,small.shape[0]-1)
        x,y = sample(self.graph.uv)
        light = lum[y,x].astype(np.float32)
        rx,ry = sample(self.graph.r8_uv)
        color = linear[ry,rx,self.graph.r8_channel].astype(np.float32)
        previews = {}
        for side in ['L','R']:
            canvas = Image.new('RGB',(240,160),(6,15,22)); draw = ImageDraw.Draw(canvas)
            indices = np.flatnonzero(self.graph.eye_sides[self.graph.retina] == side)
            for i in indices:
                px,py = self.graph.uv[i]*[239,159]
                draw.ellipse((px-1,py-1,px+1,py+1),fill=tuple(int(v) for v in small[y[i],x[i]]))
            previews[side] = np.asarray(canvas)
        return {'light':light,'color':color,'frame':small,'left':previews['L'],'right':previews['R'],
                'luminance':np.repeat((lum*255).astype(np.uint8)[...,None],3,axis=2),
                'motion':np.stack([np.maximum(motion,0)*255,np.abs(motion)*100,np.maximum(-motion,0)*255],axis=2).clip(0,255).astype(np.uint8),
                'summary':{'luminance_mean':float(light.mean()),'color_mean':float(color.mean()),'motion_energy':float(np.abs(motion).mean()),
                           'stimulated_r1r6':int((light>.01).sum()),'stimulated_r8':int((color>.01).sum()),'source':'raw_pixels'}}
