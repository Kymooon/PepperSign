from app import create_app

import os, sys
import app
import app.routes.health as health_mod

print("[BOOT] cwd:", os.getcwd())
print("[BOOT] python:", sys.executable)
print("[BOOT] run.py:", __file__)
print("[BOOT] app module:", app.__file__)
print("[BOOT] health module:", health_mod.__file__)


app = create_app()

if __name__ == "__main__":
    cfg = app.config["PSCFG"]
    app.run(host="0.0.0.0", port=cfg["PORT"], debug=False)
