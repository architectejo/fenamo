"""F-60 à F-66 (site public 2a) : modèles du contenu, nettoyage HTML, médias (WebP, PDF, APK), services journalisés, purge signée, statistiques."""
import io
import zipfile
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from PIL import Image

from compte import roles
from compte.models import Compte, JournalAction
from compte.services import verrou_application as verrou
from coptapp.models import Antenne, AssociationMembre, Membre, Province
from coptapp.services.statistiques_publiques import statistiques_publiques
from tests.test_F02_droits_roles import _compte, _nommer, acteurs_roles, monde  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import (
    Article, ArticleTraduction, Config, DocumentPublic, Galery, MembreComite, Partenaire, TelephoneSite, valider_lien_video,
)
from virtrine.services import contenu
from virtrine.services import purge
from virtrine.services.html_propre import lien_autorise, nettoyer_html
from virtrine.services.medias import valider_apk, valider_pdf_public

A = JournalAction.Action
PDF = b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n'


@pytest.fixture(autouse=True)
def media_temporaire(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def _image(format_='PNG', taille=(400, 300), nom='photo.png'):
    tampon = io.BytesIO()
    Image.new('RGB', taille, (30, 120, 200)).save(tampon, format_)
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type='image/png')


def _apk(avec_manifeste=True):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w') as archive:
        archive.writestr('AndroidManifest.xml' if avec_manifeste else 'autre.txt', b'x')
        archive.writestr('classes.dex', b'dex')
    return SimpleUploadedFile('fenamo.apk', tampon.getvalue(), content_type='application/vnd.android.package-archive')


@pytest.fixture
def editeur(monde):
    return _nommer(monde, roles.ED)


# ---------------------------------------------------------------- nettoyage HTML

@pytest.mark.parametrize('entree, attendu', [
    ('<p>Bonjour <strong>FENAMO</strong> <em>RDC</em></p>', '<p>Bonjour <strong>FENAMO</strong> <em>RDC</em></p>'),
    ('<script>alert(1)</script><p>ok</p>', '<p>ok</p>'),
    ('<p onclick="x()">texte</p>', '<p>texte</p>'),
    ('<a href="javascript:alert(1)">lien</a>', 'lien'),
    ('<a href=" JaVaScRiPt:alert(1)">lien</a>', 'lien'),
    ('<a href="data:text/html,x">lien</a>', 'lien'),
    ('<a href="//evil.example/x">lien</a>', 'lien'),
    ('<a href="https://fenamordc.cd/x" onclick="y()" target="_blank">lien</a>', '<a href="https://fenamordc.cd/x" rel="noopener noreferrer">lien</a>'),
    ('<img src=x onerror=alert(1)>texte', 'texte'),
    ('<iframe src="https://evil"></iframe>après', 'après'),
    ('<style>p{}</style><h2>Titre</h2><h3>Sous</h3>', '<h2>Titre</h2><h3>Sous</h3>'),
    ('<ul><li>un</li><li>deux</ul>', '<ul><li>un</li><li>deux</li></ul>'),
    ('a < b & c', 'a &lt; b &amp; c'),
    ('<p>un<br>deux<br/>trois', '<p>un<br>deux<br>trois</p>'),
    ('<!-- commentaire --><p>x</p>', '<p>x</p>'),
    ('<div><span>nu</span></div>', 'nu'),
    ('', ''), (None, ''),
])
def test_F60_nettoyage_html_liste_blanche(entree, attendu):
    assert nettoyer_html(entree) == attendu


def test_F60_liens_autorises_http_et_https_seulement():
    assert lien_autorise('https://fenamordc.cd') and lien_autorise('http://exemple.cd/a?b=1')
    for mauvais in ('javascript:alert(1)', 'ftp://x.cd', '/relatif', 'mailto:a@b.cd', '', None, 'https://' + 'a' * 2100):
        assert not lien_autorise(mauvais), mauvais


def test_F60_les_textes_sont_nettoyes_a_l_enregistrement(monde, editeur):
    article = Article.objects.create(titre='Titre', description='<p>ok</p><script>mal()</script>')
    assert article.description == '<p>ok</p>'
    traduction = ArticleTraduction.objects.create(article=article, langue='ln', titre='T', texte='<b onclick=x>gras</b><em>ok</em>')
    assert traduction.texte == 'gras<em>ok</em>'


# ---------------------------------------------------------------- modèles : slug, vidéo, config

def test_F60_slug_unique_genere_du_titre_et_stable(monde):
    a = Article.objects.create(titre='Assemblée générale 2026')
    b = Article.objects.create(titre='Assemblée générale 2026')
    assert a.slug == 'assemblee-generale-2026' and b.slug == 'assemblee-generale-2026-2'
    a.titre = 'Nouveau titre'
    a.save()
    assert Article.objects.get(pk=a.pk).slug == 'assemblee-generale-2026'  # le slug ne change plus
    assert Article.objects.create(titre='').slug == 'article'


def test_F60_article_en_brouillon_par_defaut_et_integration_code_conserve(monde):
    article = Article.objects.create(titre='Ancien', integration_code='<iframe src=x></iframe>')
    assert article.statut == 'brouillon' and article.type == 'article' and article.date_publication is None
    assert Article.objects.get(pk=article.pk).integration_code == '<iframe src=x></iframe>'  # gardé en base, jamais exposé


@pytest.mark.parametrize('lien, valide', [
    ('https://www.youtube.com/watch?v=abc', True), ('https://youtu.be/abc', True), ('https://www.facebook.com/video/1', True),
    ('https://fb.watch/xyz', True), ('', True),
    ('http://www.youtube.com/watch?v=abc', False), ('https://evil.example/video', False), ('javascript:alert(1)', False),
    ('https://youtube.com.evil.example/x', False),
])
def test_F60_lien_video_youtube_ou_facebook_https_seulement(lien, valide):
    if valide:
        valider_lien_video(lien)
    else:
        with pytest.raises(ValidationError):
            valider_lien_video(lien)


def test_F64_config_unique_langues_et_paiement_desactive_par_defaut(monde):
    config = Config.instance()
    assert config.paiement_en_ligne_actif is False and config.langues() == ['fr'] and Config.instance().pk == config.pk
    with pytest.raises(ValidationError):
        Config().save()
    config.langues_actives = 'ln, kg, xx'
    assert config.langues() == ['fr', 'ln', 'kg']  # inconnues ignorées, français toujours actif


# ---------------------------------------------------------------- médias

def test_F60_image_convertie_en_webp_avec_vignette(monde):
    element = Galery.objects.create(image=_image('JPEG', (2400, 1800), 'grande.jpg'), publie=True)
    assert element.image.name.endswith('.webp') and element.vignette.name.endswith('_vignette.webp')
    with Image.open(element.image.path) as grande, Image.open(element.vignette.path) as petite:
        assert grande.format == 'WEBP' and max(grande.size) <= 1600 and petite.format == 'WEBP' and max(petite.size) <= 160


def test_F60_image_refusee_si_ce_n_est_pas_une_image(monde):
    with pytest.raises(ValidationError):
        Galery.objects.create(image=SimpleUploadedFile('x.png', b'<svg><script>1</script></svg>', content_type='image/png'))
    assert not Galery.objects.exists()


def test_F60_photo_du_comite_webp_et_remplacement_supprime_l_ancienne(monde, media_temporaire, django_capture_on_commit_callbacks):
    with transaction.atomic():
        membre = MembreComite.objects.create(nom='Dirigeant Fictif', fonction='Président', photo=_image())
    ancien = membre.photo.path
    assert membre.photo.name.endswith('.webp') and __import__('os').path.exists(ancien)
    membre.photo = _image('JPEG', nom='autre.jpg')
    with django_capture_on_commit_callbacks(execute=True):
        membre.save()
    assert not __import__('os').path.exists(ancien) and MembreComite.objects.get(pk=membre.pk).photo.name.endswith('.webp')


def test_F60_pdf_public_valide(settings):
    valider_pdf_public(SimpleUploadedFile('c.pdf', PDF, content_type='application/pdf'))
    for contenu_mauvais in (b'MZ pas un pdf', PDF.replace(b'%%EOF', b''), PDF.replace(b'/Type', b'/JavaScript')):
        with pytest.raises(ValidationError):
            valider_pdf_public(SimpleUploadedFile('c.pdf', contenu_mauvais, content_type='application/pdf'))
    settings.UPLOAD_PDF_MAX_MO = 0.00001
    with pytest.raises(ValidationError):
        valider_pdf_public(SimpleUploadedFile('c.pdf', PDF, content_type='application/pdf'))


def test_F60_apk_valide_et_taille_reglable(settings):
    valider_apk(_apk())
    for mauvais in (_apk(avec_manifeste=False), SimpleUploadedFile('x.apk', b'pas un zip'), SimpleUploadedFile('x.apk', b'')):
        with pytest.raises(ValidationError):
            valider_apk(mauvais)
    settings.UPLOAD_APK_MAX_MO = 0.0001
    with pytest.raises(ValidationError):
        valider_apk(_apk())


def test_F60_document_public_nom_aleatoire_et_extension_imposee(monde):
    document = DocumentPublic.objects.create(titre='Charte', type='charte', fichier=SimpleUploadedFile('../../evil.php', PDF))
    assert document.fichier.name.startswith('documents/') and document.fichier.name.endswith('.pdf') and 'evil' not in document.fichier.name
    with pytest.raises(ValidationError):
        DocumentPublic.objects.create(titre='Faux', fichier=SimpleUploadedFile('faux.pdf', b'MZ'))


# ---------------------------------------------------------------- services : droits et journal

def test_F60_seuls_editeur_et_super_utilisateur_ecrivent(monde, acteurs_roles, editeur):
    article = Article(titre='Test')
    for role in ('PR', 'VN', 'VP', 'VA', 'AT', 'VI'):
        with pytest.raises(PermissionDenied):
            contenu.enregistrer(acteurs_roles[role], Article(titre='X'), {'titre': 'X'})
    assert contenu.enregistrer(editeur, article, {'titre': 'Test', 'resume': 'Court'}).pk
    assert contenu.enregistrer(monde['compte'], Partenaire(), {'nom': 'Ministère des Transports'}).pk


def test_F60_enregistrer_journalise_creation_et_modification(monde, editeur):
    article = contenu.enregistrer(editeur, Article(titre='Premier titre', user=editeur), {'titre': 'Premier titre', 'type': 'communique'})
    creation = JournalAction.objects.get(action=A.MODIFICATION, objet_id=article.pk)
    assert creation.auteur == editeur and creation.apres['creation'] is True and creation.apres['type'] == 'communique'
    contenu.enregistrer(editeur, article, {'resume': 'Un résumé'})
    derniere = JournalAction.objects.filter(action=A.MODIFICATION, objet_id=article.pk).latest('id')
    assert derniere.apres['champs_modifies'] == ['resume'] and 'resume' not in derniere.apres.get('resume', {})
    avant = JournalAction.objects.count()
    contenu.enregistrer(editeur, article, {'resume': 'Un résumé'})  # rien ne change : rien n'est écrit
    assert JournalAction.objects.count() == avant


def test_F60_liste_blanche_des_champs_et_integration_code_inaccessible(monde, editeur):
    with pytest.raises(ValueError):
        contenu.enregistrer(editeur, Article(titre='X'), {'titre': 'X', 'integration_code': '<script>1</script>'})
    with pytest.raises(ValueError):
        contenu.enregistrer(editeur, Article(titre='X'), {'statut': 'publie'})  # la publication a son propre service


def test_F60_contenu_invalide_n_ecrit_rien(monde, editeur):
    avant = Article.objects.count()
    with pytest.raises(ValidationError):
        contenu.enregistrer(editeur, Article(titre='X'), {'titre': 'X', 'lien_video': 'https://evil.example/v'})
    assert Article.objects.count() == avant and not JournalAction.objects.filter(action=A.MODIFICATION).exists()


def test_F60_publication_depublication_journalisees(monde, editeur):
    article = contenu.enregistrer(editeur, Article(titre='À publier'), {'titre': 'À publier'})
    contenu.publier_article(editeur, article)
    article.refresh_from_db()
    assert article.statut == 'publie' and article.date_publication is not None
    premiere = article.date_publication
    contenu.publier_article(editeur, article)  # idempotent
    assert JournalAction.objects.filter(action=A.MODIFICATION, objet_id=article.pk, motif='Publication').count() == 1
    contenu.depublier_article(editeur, article, 'Erreur de date')
    article.refresh_from_db()
    assert article.statut == 'brouillon' and article.date_publication == premiere
    assert JournalAction.objects.filter(action=A.MODIFICATION, objet_id=article.pk, motif='Erreur de date').exists()
    sans_titre = Article.objects.create(titre='')
    with pytest.raises(ValidationError):
        contenu.publier_article(editeur, sans_titre)


def test_F60_traductions_une_par_langue(monde, editeur):
    article = contenu.enregistrer(editeur, Article(titre='Bonjour'), {'titre': 'Bonjour'})
    contenu.enregistrer_traduction(editeur, article, 'ln', 'Mbote', texte='<p>Mbote</p>')
    contenu.enregistrer_traduction(editeur, article, 'ln', 'Mbote 2')
    assert ArticleTraduction.objects.filter(article=article).count() == 1 and ArticleTraduction.objects.get().titre == 'Mbote 2'
    with pytest.raises(ValidationError):
        contenu.enregistrer_traduction(editeur, article, 'fr', 'Bonjour')  # le français est l'article lui-même


def test_F60_suppression_journalisee(monde, editeur):
    element = contenu.enregistrer(editeur, TelephoneSite(), {'numero': '+243 81 000 00 01'})
    identifiant = contenu.supprimer(editeur, element)
    assert not TelephoneSite.objects.filter(pk=identifiant).exists()
    assert JournalAction.objects.filter(action=A.SUPPRESSION, objet_id=identifiant).exists()
    with pytest.raises(ValueError):
        contenu.supprimer(editeur, Config.instance())


def test_F64_F65_langues_et_paiement_reserves_au_super_utilisateur(monde, acteurs_roles, editeur):
    for compte in (editeur, acteurs_roles['PR'], acteurs_roles['VA']):
        with pytest.raises(PermissionDenied):
            contenu.definir_langues_actives(compte, ['ln'])
        with pytest.raises(PermissionDenied):
            contenu.definir_paiement_en_ligne(compte, True)
    su = monde['compte']
    config = contenu.definir_langues_actives(su, ['kg', 'ln', 'zz'])
    assert config.langues() == ['fr', 'ln', 'kg']
    ligne = JournalAction.objects.filter(action=A.MODIFICATION, apres__champs_modifies=['langues_actives']).get()
    assert ligne.auteur == su and ligne.avant == {'langues_actives': 'fr'} and ligne.apres['langues_actives'] == 'fr,ln,kg'
    assert contenu.definir_paiement_en_ligne(su, True).paiement_en_ligne_actif is True
    ligne = JournalAction.objects.filter(apres__champs_modifies=['paiement_en_ligne_actif']).get()
    assert ligne.avant == {'paiement_en_ligne_actif': False} and ligne.apres['paiement_en_ligne_actif'] is True
    contenu.definir_paiement_en_ligne(su, True)  # inchangé : pas de seconde ligne
    assert JournalAction.objects.filter(apres__champs_modifies=['paiement_en_ligne_actif']).count() == 1


def test_F61_apk_televerse_avec_version_et_journalise(monde, editeur):
    config = contenu.televerser_apk(editeur, _apk(), ' 1.4.0 ', 'Installer en autorisant les sources inconnues.')
    config.refresh_from_db()
    assert config.apk.name.startswith('application/') and config.apk.name.endswith('.apk') and config.apk_version == '1.4.0'
    assert config.apk_date == date.today() and 'sources inconnues' in config.apk_notice
    with pytest.raises(ValidationError):
        contenu.televerser_apk(editeur, _apk(avec_manifeste=False), '1.5.0')
    assert Config.objects.get().apk_version == '1.4.0'


# ---------------------------------------------------------------- purge signée

class _Reponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_F60_purge_signee_hmac_apres_le_commit(monde, editeur, settings, monkeypatch, django_capture_on_commit_callbacks):
    settings.SITE_PURGE_URL, settings.SITE_PURGE_SECRET = 'https://fenamordc.cd/purge/', 'secret-fictif'
    appels = []
    monkeypatch.setattr(purge.urllib.request, 'urlopen', lambda requete, timeout: appels.append((requete, timeout)) or _Reponse())
    with django_capture_on_commit_callbacks(execute=False) as rappels:
        contenu.enregistrer(editeur, Article(titre='Urgent'), {'titre': 'Urgent'})
    assert appels == [] and len(rappels) >= 1  # rien n'est envoyé avant le commit
    for rappel in rappels:
        rappel()
    requete, delai = appels[0]
    assert delai == 3 and requete.get_method() == 'POST' and requete.full_url == 'https://fenamordc.cd/purge/'
    horodatage = requete.get_header('X-purge-horodatage')
    assert horodatage.isdigit() and requete.get_header('X-purge-signature') == purge.signer(horodatage, 'secret-fictif')
    assert len(purge.signer('1', 'x')) == 64


def test_F60_purge_echec_journalise_sans_bloquer(monde, settings, monkeypatch, caplog):
    import urllib.error
    settings.SITE_PURGE_URL, settings.SITE_PURGE_SECRET = 'https://fenamordc.cd/purge/', 's'

    def panne(requete, timeout):
        raise urllib.error.URLError('hors ligne')

    monkeypatch.setattr(purge.urllib.request, 'urlopen', panne)
    assert purge.envoyer_purge() is False
    assert 'Purge du site échouée' in caplog.text


def test_F60_purge_ignoree_sans_reglage_schema_inconnu_ou_verrou(monde, settings, monkeypatch):
    appels = []
    monkeypatch.setattr(purge.urllib.request, 'urlopen', lambda *a, **k: appels.append(1) or _Reponse())
    assert purge.envoyer_purge() is False  # non configurée
    settings.SITE_PURGE_SECRET = 's'
    settings.SITE_PURGE_URL = 'file:///etc/passwd'
    assert purge.envoyer_purge() is False
    settings.SITE_PURGE_URL = 'https://fenamordc.cd/purge/'
    verrou.verrouiller(monde['compte'], 'Maintenance')
    assert purge.envoyer_purge() is False  # pas de purge pendant le verrou F-07
    assert appels == []
    verrou.deverrouiller(monde['compte'])
    assert purge.envoyer_purge() is True and appels == [1]


# ---------------------------------------------------------------- statistiques publiques

def test_F60_statistiques_membres_actifs_seuls_engins_masques(monde, django_assert_num_queries):
    P, Q = monde['P'], monde['Q']
    Province.objects.filter(pk=P.pk).update(code='ZP1')
    P.refresh_from_db()
    AssociationMembre.objects.create(nom='Asso P', antenne=monde['antenne_p'], province=P)
    for etat in ('actif', 'actif', 'valide_antenne', 'a_renouveler', 'saisi', 'renvoye'):
        Membre.objects.create(nom=f'M {etat}', antenne=monde['antenne_p'], province=P, etat=etat)
    Membre.objects.create(nom='Sans antenne', province=Q, etat='actif')
    Membre.objects.create(nom='Supprimé', antenne=monde['antenne_p'], province=P, etat='supprime', etat_precedent='actif')
    with django_assert_num_queries(4):  # une requête par série
        stats = statistiques_publiques()
    par_code = {c['code']: c for c in stats['coordinations']}
    base_p = Membre.objects.filter(etat='actif', antenne__coordination=P).count()
    assert par_code[P.code]['membres_actifs'] == base_p >= 2
    assert par_code[Q.code]['membres_actifs'] >= 1
    assert par_code[P.code]['associations'] >= 1 and par_code[P.code]['antennes'] >= 1
    assert stats['national']['membres_actifs'] == sum(c['membres_actifs'] for c in stats['coordinations'])
    assert stats['national']['engins'] is None and all(c['engins'] is None for c in stats['coordinations'])


def test_F60_statistiques_sans_donnee_personnelle(monde):
    Membre.objects.create(nom='Nom Secret', telephone='+243999', antenne=monde['antenne_p'], province=monde['P'], etat='actif')
    texte = str(statistiques_publiques())
    assert 'Secret' not in texte and '243999' not in texte
