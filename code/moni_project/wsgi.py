"""
WSGI config for moni_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""
import sys
if sys.version_info < (3, 10):
    from importlib_metadata import distributions
    import importlib.metadata
    # 3.10에 추가된 기능을 3.9 환경에서 수동으로 연결
    importlib.metadata.packages_distributions = lambda: {d.name: [d.name] for d in distributions()}
    
import os

from django.core.wsgi import get_wsgi_application

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moni_project.settings')

application = get_wsgi_application()