from django.urls import path
from . import views

app_name = 'readings'

urlpatterns = [
    path('health/', views.health, name='health'),
]
