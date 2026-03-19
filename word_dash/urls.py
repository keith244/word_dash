from django.urls import path
from . import views

urlpatterns = [
    path('', views.lobby, name='lobby'),
    path('search/', views.search_users, name='search_users'),
    path('match/start/<int:user_id>/', views.start_match, name='start_match'),
    path('match/<int:match_id>/', views.match_view, name='match'),
    path('challenge/<int:challenge_id>/accept/', views.accept_challenge, name='accept_challenge'),
    path('challenge/<int:challenge_id>/decline/', views.decline_challenge, name='decline_challenge'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('match/<int:match_id>/state/', views.match_state, name='match_state'),
]