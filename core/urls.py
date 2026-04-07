from django.urls import path
from .views import test
from . import views

urlpatterns = [
    path('test/', test),
    path('', views.home, name='home'),
]
