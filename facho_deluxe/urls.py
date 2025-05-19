# facho/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('scripts.urls')),  
    path('scripts/', include('scripts.urls')), 

]
