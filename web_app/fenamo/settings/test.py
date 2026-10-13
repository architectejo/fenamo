"""Réglages de TEST uniquement (jamais utilisés en développement ni en production).

Hacheur MD5 : le hachage par défaut de Django (PBKDF2, des centaines de milliers
d'itérations) domine le temps de la suite dès qu'un test crée un compte ou se
connecte. MD5 est instantané ; les mots de passe de test sont fictifs.
"""

from .dev import *  # noqa: F401,F403

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
