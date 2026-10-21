"""Container entry point; proxy trust is explicit and defaults to loopback."""

import os
import uvicorn
from app.config import PORT, ROOT_PATH

uvicorn.run("app.main:app", host="0.0.0.0", port=PORT,
            root_path=ROOT_PATH,
            proxy_headers=True,
            forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
            timeout_graceful_shutdown=20)
