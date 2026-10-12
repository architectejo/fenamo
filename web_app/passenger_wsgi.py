import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from fenamo.wsgi import application  # noqa: E402,F401
