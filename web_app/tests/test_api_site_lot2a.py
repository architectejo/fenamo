"""API /api/v1/site/ (lot 2a) : clé du site, limite de débit, verrou F-07, contrat des lectures, champs interdits."""
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from api.models import CleSite
from api.services import cles
from compte.models import Compte
from compte.services import verrou_application as V
from coptapp.models import Antenne, Province
from virtrine.models import (Article, ArticleTraduction, Config, DocumentPublic, Galery, MembreComite, Partenaire,
                             TelephoneSite)

INTERDITS = {'id', 'pk', 'user', 'user_id', 'auteur', 'is_delete', 'integration_code', 'statut', 'brouillon', 'cle', 'password',
             'empreinte', 'prefixe', 'principale', 'publie', 'lien_video', 'chemin', 'mbr', 'telephone', 'phone', 'mail', 'gmail',
             'adresse', 'membre', 'compte', 'username', 'token', 'secret'}
POINTS = ['config/', 'articles/', 'galerie/', 'comite/', 'coordinations/', 'statistiques/']


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path  # aucun fichier de test dans le dossier de médias réel
    return tmp_path


@pytest.fixture
def cle(db):
    from virtrine.models import Config
    config = Config.instance()
    config.donnees_reelles_actif = True  # ces tests portent sur les données réelles ; l'interrupteur faux est testé dans test_F60_donnees_reelles.py
    config.save(update_fields=['donnees_reelles_actif'])
    return cles.creer_cle('Site public')[1]


def get(client, chemin, cle=None, **params):
    entetes = {'HTTP_X_SITE_KEY': cle} if cle else {}
    return client.get('/api/v1/site/' + chemin, params, **entetes)


def corps(reponse):
    return json.loads(reponse.content)


def cles_recursives(donnees):
    if isinstance(donnees, dict):
        for k, v in donnees.items():
            yield k
            yield from cles_recursives(v)
    elif isinstance(donnees, list):
        for v in donnees:
            yield from cles_recursives(v)


def article(titre='Titre', statut='publie', jours=-1, **kw):
    return Article.objects.create(titre=titre, statut=statut, date_publication=timezone.now() + timedelta(days=jours),
                                  description=kw.pop('description', '<p>Texte</p>'), **kw)


# ---------------------------------------------------------------- clés

def test_api_site_sans_cle_401(client, db):
    for chemin in POINTS:
        r = get(client, chemin)
        assert r.status_code == 401 and corps(r) == {'detail': 'Clé du site absente ou invalide.'}


def test_api_site_cle_invalide_401_journalisee_sans_la_cle(client, cle, caplog):
    mauvaise = cle[:-3] + 'xyz'
    with caplog.at_level('WARNING', logger='api.cles'):
        assert get(client, 'config/', mauvaise).status_code == 401
        assert get(client, 'config/', 'nimportequoi').status_code == 401
    assert 'refusée' in caplog.text and mauvaise not in caplog.text and 'nimportequoi' not in caplog.text


def test_api_site_cle_revoquee_401(client, cle):
    assert get(client, 'config/', cle).status_code == 200
    prefixe = cle.split('_')[1]
    call_command('revoquer_cle_site', prefixe, stdout=StringIO())
    assert get(client, 'config/', cle).status_code == 401
    assert CleSite.objects.get(prefixe=prefixe).revoquee_le is not None


def test_api_site_cle_stockee_hachee_et_deux_actives_au_plus(db):
    objet, cle = cles.creer_cle('A')
    assert cle.startswith(f'fsk_{objet.prefixe}_') and cle not in (objet.empreinte, objet.prefixe)
    assert objet.empreinte == cles.empreinte(cle) and len(objet.empreinte) == 64
    cles.creer_cle('B')
    with pytest.raises(cles.CleSiteErreur):
        cles.creer_cle('C')
    cles.revoquer_cle(objet.prefixe)
    cles.creer_cle('C')  # rotation : la place libérée par la révocation


def test_api_site_commandes_creer_et_revoquer(db):
    sortie = StringIO()
    call_command('creer_cle_site', '--nom', 'Site', stdout=sortie)
    cle = sortie.getvalue().strip().splitlines()[-1]
    assert cles.verifier(cle) is not None
    with pytest.raises(CommandError):
        call_command('revoquer_cle_site', 'zzzzzzzz', stdout=StringIO())
    with pytest.raises(CommandError):
        call_command('creer_cle_site', '--nom', '  ', stdout=StringIO())


def test_api_site_derniere_utilisation_une_fois_par_heure(client, cle):
    objet = CleSite.objects.get()
    assert objet.derniere_utilisation is None
    get(client, 'config/', cle)
    premiere = CleSite.objects.get().derniere_utilisation
    assert premiere is not None
    get(client, 'config/', cle)
    assert CleSite.objects.get().derniere_utilisation == premiere  # pas de nouvelle écriture dans l'heure
    CleSite.objects.update(derniere_utilisation=timezone.now() - timedelta(hours=2))
    get(client, 'config/', cle)
    assert CleSite.objects.get().derniere_utilisation > timezone.now() - timedelta(minutes=1)


def test_api_site_cle_de_developpement_seulement_en_debug(client, db):
    with override_settings(SITE_API_KEY='cle-dev-locale', DEBUG=False):
        assert get(client, 'config/', 'cle-dev-locale').status_code == 401
    with override_settings(SITE_API_KEY='cle-dev-locale', DEBUG=True):
        assert get(client, 'config/', 'cle-dev-locale').status_code == 200
    with override_settings(SITE_API_KEY='', DEBUG=True):
        assert get(client, 'config/', '').status_code == 401


# ---------------------------------------------------------------- limite, méthodes, verrou

def test_api_site_limite_429_retry_after(client, cle):
    with override_settings(SITE_API_LIMITE_GET=3):
        for _ in range(3):
            assert get(client, 'config/', cle).status_code == 200
        r = get(client, 'config/', cle)
    assert r.status_code == 429 and corps(r) == {'detail': 'Trop de requêtes.'}
    assert 1 <= int(r['Retry-After']) <= 61


def test_api_site_limite_par_cle_et_post_separe(client, db):
    _, cle_a = cles.creer_cle('A')
    _, cle_b = cles.creer_cle('B')
    with override_settings(SITE_API_LIMITE_GET=1, SITE_API_LIMITE_POST=1):
        assert get(client, 'config/', cle_a).status_code == 200
        assert get(client, 'config/', cle_a).status_code == 429
        assert get(client, 'config/', cle_b).status_code == 200  # autre clé, autre compteur
        assert client.post('/api/v1/site/config/', HTTP_X_SITE_KEY=cle_b).status_code == 405  # POST : son propre compteur
        assert client.post('/api/v1/site/config/', HTTP_X_SITE_KEY=cle_b).status_code == 429


def test_api_site_401_avant_429_et_sans_compteur(client, cle):
    with override_settings(SITE_API_LIMITE_GET=1):
        assert get(client, 'config/', cle).status_code == 200
        assert get(client, 'config/', 'mauvaise').status_code == 401  # une clé inconnue n'épuise pas le compteur d'une clé réelle
        assert get(client, 'config/', cle).status_code == 429


@pytest.mark.parametrize('methode', ['post', 'put', 'patch', 'delete'])
def test_api_site_405_hors_get(client, cle, methode):
    for chemin in POINTS + ['articles/un-slug/']:
        r = getattr(client, methode)('/api/v1/site/' + chemin, HTTP_X_SITE_KEY=cle)  # sans jeton CSRF : exempté
        assert r.status_code == 405 and r['Allow'] == 'GET' and 'detail' in corps(r)


def test_api_site_verrou_503_avant_la_cle(client, cle):
    su = Compte.objects.create_superuser('root', 'r@example.org', 'x')
    V.verrouiller(su, 'Maintenance.', 'motif interne')
    for entete in (None, cle):
        r = get(client, 'config/', entete)
        assert r.status_code == 503 and corps(r)['statut'] == 'suspendu'
    assert corps(get(client, 'config/'))['message'] == 'Maintenance.'


def test_api_site_route_inconnue_404_json_apres_la_cle(client, cle):
    assert get(client, 'nexiste-pas/').status_code == 401
    r = get(client, 'nexiste-pas/', cle)
    assert r.status_code == 404 and corps(r) == {'detail': 'Introuvable.'}


def test_api_site_aucun_cookie_et_no_cache(client, cle):
    article()
    for chemin in POINTS + ['articles/titre/', 'articles/inexistant/']:
        for entete in (cle, None):
            r = get(client, chemin, entete)
            assert 'Set-Cookie' not in r.headers and not r.cookies, chemin
            assert r['Cache-Control'] == 'no-cache'
            assert r['Content-Type'].startswith('application/json')


# ---------------------------------------------------------------- config

def test_api_site_config_nominale(client, cle):
    cfg = Config.instance()
    cfg.nom, cfg.slogant, cfg.welcome_text, cfg.adresse, cfg.gmail = 'Fédération X', 'Devise', 'Bienvenue', 'Kinshasa', 'contact@example.org'
    cfg.facebook, cfg.twitter, cfg.youtube = 'https://fb.example/fenamo', 'javascript:alert(1)', ''
    cfg.langues_actives, cfg.paiement_en_ligne_actif = 'ln,xx', True
    cfg.apk_version, cfg.apk_date, cfg.apk_notice = '1.2', timezone.localdate(), 'Notice'
    cfg.apk.save('app.apk', ContentFile(b'PK\x03\x04'), save=False)
    cfg.save()
    TelephoneSite.objects.create(numero='+243000000', libelle='Secrétariat', ordre=1)
    Partenaire.objects.create(nom='Ptn', lien='data:text/html,x', ordre=1)
    doc = DocumentPublic(titre='Charte', type='charte')
    doc.fichier.save('c.pdf', ContentFile(b'%PDF-1.4\n%%EOF'), save=False)
    doc.save()
    r = get(client, 'config/', cle)
    d = corps(r)
    assert r.status_code == 200
    assert d['nom'] == 'FENAMO-RDC' and d['nom_complet'] == 'Fédération X' and d['devise'] == 'Devise' and d['siege'] == 'Kinshasa'
    assert d['message_accueil'] == 'Bienvenue' and d['email'] == 'contact@example.org'
    assert d['telephones'] == [{'libelle': 'Secrétariat', 'numero': '+243000000'}]
    assert d['reseaux'] == {'facebook': 'https://fb.example/fenamo', 'x': None, 'youtube': None, 'instagram': None, 'linkedin': None}
    assert d['partenaires'] == [{'nom': 'Ptn', 'lien': None, 'logo': None}]
    assert d['langues_actives'] == ['fr', 'ln'] and d['paiement_en_ligne'] is True
    assert d['documents'][0]['titre'] == 'Charte' and d['documents'][0]['url'].startswith('http://testserver/media/documents/')
    assert d['documents'][0]['taille'] == len(b'%PDF-1.4\n%%EOF')
    assert d['application']['version'] == '1.2' and d['application']['url'].endswith('.apk')
    assert set(d) == {'nom', 'nom_complet', 'devise', 'message_accueil', 'logo', 'image_fond', 'siege', 'email', 'telephones', 'reseaux',
                      'partenaires', 'langues_actives', 'paiement_en_ligne', 'documents', 'application', 'mise_a_jour', 'donnees_reelles'}


def test_api_site_config_vide_application_nulle_et_adresses_publiques(client, cle):
    d = corps(get(client, 'config/', cle))
    assert d['application'] is None and d['paiement_en_ligne'] is False and d['langues_actives'] == ['fr']
    with override_settings(PUBLIC_MEDIA_BASE_URL='https://app.fenamordc.cd/media/'):
        cfg = Config.instance()
        cfg.logo.save('l.png', ContentFile(_png()), save=True)
        logo = corps(get(client, 'config/', cle))['logo']
    assert logo['url'].startswith('https://app.fenamordc.cd/media/') and logo['vignette'].startswith('https://app.fenamordc.cd/media/')
    assert logo['largeur'] and logo['hauteur']
    assert 'media_prive' not in json.dumps(logo)


def _png():
    from io import BytesIO
    from PIL import Image
    tampon = BytesIO()
    Image.new('RGB', (40, 30), 'red').save(tampon, 'PNG')
    return tampon.getvalue()


# ---------------------------------------------------------------- articles

def test_api_site_articles_publies_seulement_et_forme(client, cle):
    visible = article('Visible', resume='Rés')
    article('Brouillon', statut='brouillon')
    article('Futur', jours=3)
    Article.objects.create(titre='Sans date', statut='publie')
    r = get(client, 'articles/', cle)
    d = corps(r)
    assert r.status_code == 200 and d['total'] == 1 and d['page'] == 1 and d['pages'] == 1
    assert d['resultats'] == [{'slug': visible.slug, 'type': 'article', 'titre': 'Visible', 'resume': 'Rés', 'image': None,
                               'date_publication': d['resultats'][0]['date_publication'], 'langue': 'fr', 'traduit': True}]
    assert d['resultats'][0]['date_publication'].endswith('+02:00') or '+' in d['resultats'][0]['date_publication']
    assert 'Brouillon' not in r.content.decode() and 'Futur' not in r.content.decode()


def test_api_site_articles_tri_type_recherche(client, cle):
    article('Ancien communiqué', type='communique', jours=-10)
    article('Récent article', jours=-1)
    titres = [a['titre'] for a in corps(get(client, 'articles/', cle))['resultats']]
    assert titres == ['Récent article', 'Ancien communiqué']
    assert [a['titre'] for a in corps(get(client, 'articles/', cle, type='communique'))['resultats']] == ['Ancien communiqué']
    assert [a['titre'] for a in corps(get(client, 'articles/', cle, q='ENT ART'))['resultats']] == ['Récent article']
    assert corps(get(client, 'articles/', cle, q='%%'))['total'] == 0  # pas de joker


@pytest.mark.parametrize('params,champ', [({'type': 'autre'}, 'type'), ({'q': 'a'}, 'q'), ({'q': ' '}, 'q'), ({'q': 'x' * 101}, 'q'),
                                          ({'page': 'abc'}, 'page'), ({'page': '0'}, 'page'), ({'taille': '51'}, 'taille'),
                                          ({'taille': '0'}, 'taille'), ({'taille': '-1'}, 'taille')])
def test_api_site_articles_parametres_400_structures(client, cle, params, champ):
    r = get(client, 'articles/', cle, **params)
    d = corps(r)
    assert r.status_code == 400 and list(d) == [champ] and isinstance(d[champ], list) and isinstance(d[champ][0], str)


def test_api_site_pagination_et_page_hors_limite_404(client, cle):
    for i in range(5):
        article(f'Article {i}', jours=-i - 1)
    d = corps(get(client, 'articles/', cle, taille=2, page=3))
    assert d['total'] == 5 and d['pages'] == 3 and d['page'] == 3 and len(d['resultats']) == 1
    r = get(client, 'articles/', cle, taille=2, page=4)
    assert r.status_code == 404 and corps(r) == {'detail': 'Introuvable.'}
    assert get(client, 'articles/', cle, taille=50).status_code == 200


def test_api_site_liste_vide_page_un_valide(client, cle):
    assert corps(get(client, 'articles/', cle)) == {'total': 0, 'page': 1, 'pages': 0, 'resultats': []}
    assert get(client, 'articles/', cle, page=2).status_code == 404


def test_api_site_400_avant_404(client, cle):
    assert get(client, 'articles/', cle, page=99, taille=500).status_code == 400


def test_api_site_langue_repli_en_francais(client, cle):
    a = article('Titre fr', resume='Résumé fr', description='<p>Texte fr</p>')
    ArticleTraduction.objects.create(article=a, langue='ln', titre='Titre ln', resume='Résumé ln', texte='<p>Texte ln</p>')
    ArticleTraduction.objects.create(article=a, langue='sw', titre='Titre sw')
    cfg = Config.instance()
    cfg.langues_actives = 'ln,sw,lua'
    cfg.save()
    ln = corps(get(client, 'articles/', cle, lang='ln'))['resultats'][0]
    assert (ln['titre'], ln['resume'], ln['langue'], ln['traduit']) == ('Titre ln', 'Résumé ln', 'ln', True)
    lua = corps(get(client, 'articles/', cle, lang='lua'))['resultats'][0]  # active mais sans traduction
    assert (lua['titre'], lua['langue'], lua['traduit']) == ('Titre fr', 'fr', False)
    inconnue = corps(get(client, 'articles/', cle, lang='zz'))['resultats'][0]
    assert (inconnue['titre'], inconnue['langue'], inconnue['traduit']) == ('Titre fr', 'fr', True)
    detail = corps(get(client, f'articles/{a.slug}/', cle, lang='ln'))
    assert detail['texte'] == '<p>Texte ln</p>' and detail['langues_disponibles'] == ['fr', 'ln', 'sw']
    assert corps(get(client, f'articles/{a.slug}/', cle, lang='kg'))['texte'] == '<p>Texte fr</p>'
    cfg.langues_actives = 'sw'
    cfg.save()  # langue désactivée : repli en français
    assert corps(get(client, f'articles/{a.slug}/', cle, lang='ln'))['langue'] == 'fr'
    assert corps(get(client, f'articles/{a.slug}/', cle))['langues_disponibles'] == ['fr', 'sw']


def test_api_site_article_detail_html_nettoye_video_galerie(client, cle):
    a = article('Détail', description='<p>Bonjour</p><script>alert(1)</script><img src=x onerror=alert(1)>',
                lien_video='https://www.youtube.com/watch?v=dQw4w9WgXcQ', integration_code='<iframe src="x"></iframe>')
    Article.objects.filter(pk=a.pk).update(description='<p>Sale</p><script>alert(1)</script>')  # contourne le nettoyage à l'enregistrement
    visible = Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', legende='Vidéo', publie=True)
    cache1 = Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', publie=False)
    cache2 = Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', publie=True, is_delete=True)
    a.galery.add(visible, cache1, cache2)
    r = get(client, f'articles/{a.slug}/', cle)
    d = corps(r)
    texte = r.content.decode()
    assert r.status_code == 200 and '<script' not in d['texte'] and 'onerror' not in texte and 'integration_code' not in texte
    assert 'iframe' not in texte and d['video'] == {'fournisseur': 'youtube', 'identifiant': 'dQw4w9WgXcQ'}
    assert len(d['galerie']) == 1 and d['galerie'][0]['legende'] == 'Vidéo' and d['galerie'][0]['video']['identifiant'] == 'dQw4w9WgXcQ'
    assert d['langues_disponibles'] == ['fr'] and d['mise_a_jour']


def test_api_site_article_404_uniforme(client, cle):
    brouillon, futur, ok = article('B', statut='brouillon'), article('F', jours=2), article('Ok')
    reponses = [get(client, f'articles/{s}/', cle) for s in (brouillon.slug, futur.slug, 'inexistant', 'a b', '%00', str(ok.pk + 99))]
    assert {r.status_code for r in reponses} == {404}
    assert {r.content for r in reponses} == {json.dumps({'detail': 'Introuvable.'}).encode()}
    assert get(client, f'articles/{ok.slug}/', cle).status_code == 200
    assert get(client, f'articles/{ok.pk}/', cle).status_code == 404  # jamais par clé primaire


def test_api_site_video_formats():
    from api.serialiseurs import video
    assert video('https://youtu.be/dQw4w9WgXcQ?t=3') == {'fournisseur': 'youtube', 'identifiant': 'dQw4w9WgXcQ'}
    assert video('https://www.youtube.com/embed/dQw4w9WgXcQ')['identifiant'] == 'dQw4w9WgXcQ'
    assert video('https://www.facebook.com/x/videos/1')['fournisseur'] == 'facebook'
    for mauvais in ('http://youtu.be/dQw4w9WgXcQ', 'https://evil.example/watch?v=dQw4w9WgXcQ', 'https://youtube.com/watch?v=<x>', '', None):
        assert video(mauvais) is None


# ---------------------------------------------------------------- galerie, comité, coordinations, statistiques

def test_api_site_galerie_publie_seulement(client, cle):
    pub = article('Pub')
    photo = Galery.objects.create(type='photo', legende='Photo', publie=True, date=timezone.localdate(),
                                  image=SimpleUploadedFile('p.png', _png(), content_type='image/png'))
    pub.galery.add(photo)
    Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', publie=True, legende='V')
    Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', publie=False, legende='Brouillon')
    Galery.objects.create(type='photo', publie=True, legende='Sans fichier')
    Galery.objects.create(type='photo', publie=True, is_delete=True, legende='Supprimée',
                          image=SimpleUploadedFile('s.png', _png(), content_type='image/png'))
    Galery.objects.create(type='photo', publie=True, principale=True, legende='Principale',
                          image=SimpleUploadedFile('m.png', _png(), content_type='image/png'))
    r = get(client, 'galerie/', cle)
    d = corps(r)
    assert d['total'] == 2
    legendes = {e['legende'] for e in d['resultats']}
    assert legendes == {'Photo', 'V'} and d['pages'] == 1
    p = next(e for e in d['resultats'] if e['legende'] == 'Photo')
    assert p['type'] == 'photo' and p['video'] is None and p['article'] == pub.slug and p['image']['url'].endswith('.webp')
    assert p['image']['vignette'].endswith('_vignette.webp') and p['date'] == timezone.localdate().isoformat()
    v = next(e for e in d['resultats'] if e['legende'] == 'V')
    assert v['image'] is None and v['video'] == {'fournisseur': 'youtube', 'identifiant': 'dQw4w9WgXcQ'} and v['article'] is None
    assert [e['legende'] for e in corps(get(client, 'galerie/', cle, type='video'))['resultats']] == ['V']
    assert get(client, 'galerie/', cle, type='x').status_code == 400


def test_api_site_galerie_article_non_publie_non_expose(client, cle):
    brouillon = article('Caché', statut='brouillon')
    g = Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', publie=True)
    brouillon.galery.add(g)
    r = get(client, 'galerie/', cle)
    assert corps(r)['resultats'][0]['article'] is None and 'cach' not in r.content.decode().lower()


def test_api_site_comite_sans_donnee_personnelle(client, cle):
    MembreComite.objects.create(nom='B Dirigeant', fonction='Secrétaire', fonction_code='SEC', ordre=2)
    MembreComite.objects.create(nom='A Président', fonction='Président', fonction_code='PRES', ordre=1)
    r = get(client, 'comite/', cle)
    d = corps(r)
    assert d['mandat'] == {'debut': None, 'fin': None}
    assert [m['nom'] for m in d['membres']] == ['A Président', 'B Dirigeant']
    assert set(d['membres'][0]) == {'nom', 'fonction', 'fonction_code', 'photo', 'ordre'}
    assert 'MBR' not in r.content.decode()


def _vider_geographie():
    """La migration crée les 27 coordinations : les tests de géographie partent d'un état vide."""
    Antenne.objects.all().delete()
    Province.objects.all().delete()


def test_api_site_coordinations_et_antennes(client, cle):
    _vider_geographie()
    b = Province.objects.create(nom='Beta', code='BB', ordre=2)
    a = Province.objects.create(nom='Alpha', code='AA', ordre=1)
    Province.objects.create(nom='Sans code', ordre=3)
    Antenne.objects.create(nom='Gombe', code='GOM', coordination=a, type='commune')
    Antenne.objects.create(nom='Sans code', coordination=a, type='commune')
    Antenne.objects.create(nom='Orpheline', code='ORP', type='commune')
    r = get(client, 'coordinations/', cle)
    d = corps(r)
    assert [c['code'] for c in d] == ['AA', 'BB']
    assert d[0] == {'code': 'AA', 'nom': 'Alpha', 'ordre': 1, 'antennes': [{'code': 'GOM', 'nom': 'Gombe', 'type': 'commune'}]}
    assert d[1]['antennes'] == [] and b.nom == 'Beta'


def test_api_site_statistiques_agregats_seulement(client, cle):
    _vider_geographie()
    Province.objects.create(nom='Alpha', code='AA', ordre=1)
    r = get(client, 'statistiques/', cle)
    d = corps(r)
    assert set(d) == {'date_calcul', 'membres_actifs', 'engins_actifs', 'engins_par_type', 'associations_membres', 'coordinations',
                      'par_coordination'}
    assert d['engins_actifs'] is None and d['engins_par_type'] is None and d['coordinations'] == 1
    assert d['par_coordination'] == [{'code': 'AA', 'nom': 'Alpha', 'membres_actifs': 0, 'associations_membres': 0, 'antennes': 0,
                                      'engins_actifs': None}]
    assert d['date_calcul'][-6] in '+-'  # fuseau explicite


# ---------------------------------------------------------------- champs interdits, purge

def test_api_site_aucune_cle_interdite_dans_les_reponses(client, cle):
    a = article('Complet', lien_video='https://youtu.be/dQw4w9WgXcQ', integration_code='<b>x</b>', resume='r')
    ArticleTraduction.objects.create(article=a, langue='ln', titre='t')
    g = Galery.objects.create(type='video', lien_video='https://youtu.be/dQw4w9WgXcQ', publie=True)
    a.galery.add(g)
    MembreComite.objects.create(nom='N', fonction='F', ordre=1)
    TelephoneSite.objects.create(numero='+243', ordre=1)
    Partenaire.objects.create(nom='P', ordre=1)
    prov = Province.objects.create(nom='Alpha', code='AA', ordre=1)
    Antenne.objects.create(nom='Gombe', code='GOM', coordination=prov, type='commune')
    for chemin in POINTS + [f'articles/{a.slug}/']:
        donnees = corps(get(client, chemin, cle))
        trouvees = {k for k in cles_recursives(donnees)} & INTERDITS
        assert not trouvees, (chemin, trouvees)


def test_api_site_lectures_sans_effet_de_bord_ni_purge(client, cle, monkeypatch):
    appels = []
    monkeypatch.setattr('virtrine.services.purge.envoyer_purge', lambda: appels.append(1))
    article('X')
    avant = (Article.objects.count(), Config.objects.count())
    for chemin in POINTS:
        get(client, chemin, cle)
    assert (Article.objects.count(), Config.objects.count()) == (avant[0], avant[1] or 1) and appels == []
