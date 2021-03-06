from django.shortcuts import render_to_response
from django.template import RequestContext
from reduction_viewer.models import Setting

def get_admin_email():
    try:
        admin_email = Setting.objects.get(name='admin_email')
        return admin_email.value
    except:
        return ''

def handler400(request):
    response = render_to_response('400.html', {'admin_email' : get_admin_email()}, RequestContext(request))
    response.status_code = 400
    return response

def handler404(request):
    response = render_to_response('404.html', {'admin_email' : get_admin_email()}, RequestContext(request))
    response.status_code = 404
    return response

def handler403(request):
    response = render_to_response('403.html', {'admin_email' : get_admin_email()}, RequestContext(request))
    response.status_code = 403
    return response

def handler500(request):
    response = render_to_response('500.html', {'admin_email' : get_admin_email()}, RequestContext(request))
    response.status_code = 500
    return response