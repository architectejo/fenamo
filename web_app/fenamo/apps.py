from django.contrib.admin.apps import AdminConfig


class FenamoAdminConfig(AdminConfig):
    default_site = 'fenamo.admin.SiteAdminFenamo'
