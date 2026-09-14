"""Process-lifetime scheduling for short GPU submissions and 240 Hz physics."""
from contextlib import contextmanager
import logging
import sys


@contextmanager
def responsive_timing():
    previous = sys.getswitchinterval()
    timer = None
    # CuPy releases the GIL around short kernel launches. Let the submitting
    # thread resume promptly while physics and HTTP remain responsive.
    sys.setswitchinterval(.001)
    if sys.platform == 'win32':
        import ctypes
        winmm = ctypes.WinDLL('winmm')
        if winmm.timeBeginPeriod(1) == 0:
            timer = winmm
            logging.getLogger('biliardo').info('Windows timer resolution requested: 1 ms')
    try:
        yield
    finally:
        if timer is not None:
            timer.timeEndPeriod(1)
        sys.setswitchinterval(previous)
