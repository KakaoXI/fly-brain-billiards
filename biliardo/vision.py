"""An overhead artificial eye. Its exact RGB pixels feed real retinal neurons."""
import math
import numpy as np
from PIL import Image, ImageDraw
from .game import COLORS, POCKETS


def render_eye(game_state, gaze=0.):
    scale, border = .6, 20
    im = Image.new('RGB', (640, 340), '#523f31')
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 620, 320), fill='#185849')
    for x, y in POCKETS:
        px, py = border+x*scale, border+y*scale
        d.ellipse((px-14, py-14, px+14, py+14), fill='#080d0b')
    for b in game_state['balls']:
        if b['pocketed']:
            continue
        n = b['number']
        x, y, r = border+b['x']*scale, border+b['y']*scale, 7
        color = COLORS[n if n < 9 else n-8]
        d.ellipse((x-r, y-r, x+r, y+r), fill=color)
        if n > 8:
            # White caps leave a colored equatorial stripe, matching the table.
            d.chord((x-r, y-r, x+r, y+r), 180, 360, fill='#f5f1df')
            d.rectangle((x-r+1, y-2, x+r-1, y+2), fill=color)
            d.chord((x-r, y-r, x+r, y+r), 0, 180, fill='#f5f1df')
            d.rectangle((x-r+1, y-2, x+r-1, y+2), fill=color)
        if n:
            d.ellipse((x-3, y-3, x+3, y+3), fill='#f4f0e4')
            # No target arrows, object masks, rewards or HUD in the retinal frame.
    cue = game_state['balls'][0]
    if not cue['pocketed'] and game_state['turn'] == 'fly' and game_state['phase'] == 'aim':
        x, y = border+cue['x']*scale, border+cue['y']*scale
        d.line((x-15*math.cos(gaze), y-15*math.sin(gaze), x-90*math.cos(gaze), y-90*math.sin(gaze)), fill='#d4b680', width=3)
    return np.asarray(im)
