"""Open the local site when it is listening; reuse an already running instance."""
import json
import threading
import time
import urllib.request
import webbrowser

URL = 'http://127.0.0.1:8766'


def running():
    try:
        with urllib.request.urlopen(URL+'/api/bootstrap', timeout=1) as response:
            result = json.load(response)
            return 'token' in result and 'game' in result.get('state', {})
    except Exception:
        return False


def open_when_ready():
    for _ in range(120):
        if running():
            webbrowser.open(URL)
            return
        time.sleep(.5)


def main():
    if running():
        webbrowser.open(URL)
        print('Il biliardo è già aperto. Sessione esistente conservata.')
        return
    threading.Thread(target=open_when_ready, daemon=True).start()
    from .server import app, BASE
    import logging
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(BASE/'logs/server.log', encoding='utf-8'), logging.StreamHandler()])
    uvicorn.run(app, host='127.0.0.1', port=8766, access_log=False, timeout_graceful_shutdown=3)


if __name__ == '__main__':
    main()
