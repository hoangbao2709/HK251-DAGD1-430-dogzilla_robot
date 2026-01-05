from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "ok", "service": "dogzilla-backend"})

urlpatterns = [
    path('', health_check),
    path('health', health_check),
    path('admin/', admin.site.urls),
    path('control/', include('control.urls')),
    path("api/auth/", include("authapp.urls")),
]
