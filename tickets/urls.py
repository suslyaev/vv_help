from django.urls import path
from . import views

app_name = 'tickets'

urlpatterns = [
    # Главная страница
    path('', views.dashboard, name='dashboard'),
    
    # Обращения
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/create/', views.ticket_create, name='ticket_create'),
    path('tickets/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:ticket_id>/edit/', views.ticket_edit, name='ticket_edit'),
    path('tickets/<int:ticket_id>/take/', views.take_ticket, name='take_ticket'),
    path('tickets/<int:ticket_id>/resolve/', views.resolve_ticket, name='resolve_ticket'),
    path('tickets/<int:ticket_id>/waiting/', views.set_waiting, name='set_waiting'),
    path('tickets/<int:ticket_id>/return_to_work/', views.return_to_work, name='return_to_work'),
    path('tickets/<int:ticket_id>/close/', views.close_ticket, name='close_ticket'),
    
    # Вложения
    path('attachments/<int:attachment_id>/delete/', views.delete_attachment, name='delete_attachment'),
    
    # Клиенты
    path('clients/', views.client_list, name='client_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:client_id>/', views.client_detail, name='client_detail'),
    
    # Аналитика
    path('analytics/', views.analytics, name='analytics'),
    
    # Очередь дел
    path('queue/', views.queue_view, name='queue'),
    
    # AJAX
    path('api/template/<int:template_id>/', views.get_template_content, name='get_template_content'),
    path('api/categories/', views.autocomplete_categories, name='autocomplete_categories'),
    path('api/clients/', views.autocomplete_clients, name='autocomplete_clients'),
    path('api/users/', views.autocomplete_users, name='autocomplete_users'),
]
