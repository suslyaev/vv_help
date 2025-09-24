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
    path('tickets/<int:ticket_id>/edit-resolution/', views.edit_resolution, name='edit_resolution'),
    path('tickets/<int:ticket_id>/delete-resolution/', views.delete_resolution, name='delete_resolution'),
    path('comments/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('comments/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    
    # Вложения
    path('attachments/<int:attachment_id>/delete/', views.delete_attachment, name='delete_attachment'),
    
    # Клиенты
    path('clients/', views.client_list, name='client_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:client_id>/', views.client_detail, name='client_detail'),
    path('clients/<int:client_id>/edit/', views.client_edit, name='client_edit'),
    
    # Организации
    path('organizations/', views.organization_list, name='organization_list'),
    path('organizations/create/', views.organization_create, name='organization_create'),
    path('organizations/<int:organization_id>/', views.organization_detail, name='organization_detail'),
    path('organizations/<int:organization_id>/edit/', views.organization_edit, name='organization_edit'),
    
    # Аналитика
    path('analytics/', views.analytics, name='analytics'),
    path('analytics/export/', views.analytics_export_xlsx, name='analytics_export_xlsx'),
    # Поток Telegram
    path('stream/', views.stream, name='stream'),
    
    # Очередь дел
    path('queue/', views.queue_view, name='queue'),
    
    # AJAX
    path('api/template/<int:template_id>/', views.get_template_content, name='get_template_content'),
    path('api/categories/', views.autocomplete_categories, name='autocomplete_categories'),
    path('api/clients/', views.autocomplete_clients, name='autocomplete_clients'),
    path('api/users/', views.autocomplete_users, name='autocomplete_users'),
    path('api/organizations/', views.autocomplete_organizations, name='autocomplete_organizations'),
    path('api/organizations/create/', views.create_organization, name='create_organization'),
    path('api/groups/', views.autocomplete_groups, name='autocomplete_groups'),
    path('api/tickets/active/', views.get_active_tickets, name='get_active_tickets'),
    path('api/tickets/all/', views.get_all_tickets, name='get_all_tickets'),
    path('api/tickets/unresolved/', views.get_unresolved_tickets, name='get_unresolved_tickets'),
    path('api/tickets/working/', views.get_working_tickets, name='get_working_tickets'),
    path('api/tickets/waiting/', views.get_waiting_tickets, name='get_waiting_tickets'),
]
