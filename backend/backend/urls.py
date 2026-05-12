from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('control/', include('control.urls')),
    path("api/auth/", include("authapp.urls")),

]
