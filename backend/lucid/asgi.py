"""The ASGI app: `uvicorn lucid.asgi:application`.

Keep heavy imports (model SDKs, LangChain) out of module load, so a cold start stays fast (B10,
T3): import them inside the code path that needs them.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lucid.settings")

application = get_asgi_application()
