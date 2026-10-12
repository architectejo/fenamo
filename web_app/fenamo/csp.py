"""En-tête Content-Security-Policy-Report-Only (Django 5.2 n'a pas de CSP intégrée)."""
from django.conf import settings


class CspReportOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        politique = getattr(settings, 'CSP_REPORT_ONLY_POLICY', '')
        if politique and 'Content-Security-Policy-Report-Only' not in response.headers:
            response.headers['Content-Security-Policy-Report-Only'] = politique
        return response
