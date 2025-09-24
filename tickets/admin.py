from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from .models import (
    Category, Client, Organization, TicketStatus, Ticket, TicketAudit, 
    TicketComment, TicketAttachment, TicketTemplate, UserTelegramAccess, TelegramMessage, TelegramGroup
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'sla_hours', 'ticket_count', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    # Даем возможность править название и родителя прямо в списке
    list_editable = ['name', 'parent', 'sla_hours', 'is_active']
    # Чтобы можно было редактировать 'name', ссылка на объект будет на другом поле
    list_display_links = ['ticket_count']
    autocomplete_fields = ['parent']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'parent', 'description')
        }),
        ('Настройки', {
            'fields': ('sla_hours', 'is_active')
        }),
    )
    
    def ticket_count(self, obj):
        return obj.ticket_set.count()
    ticket_count.short_description = 'Количество обращений'


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'contact_person', 'phone', 'email', 'ticket_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'organization', 'created_at']
    search_fields = ['name', 'organization__name', 'contact_person', 'phone', 'email', 'external_id']
    list_editable = ['is_active']
    autocomplete_fields = ['organization']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('organization', 'name', 'contact_person', 'phone', 'email')
        }),
        ('Дополнительно', {
            'fields': ('external_id', 'notes', 'is_active')
        }),
    )
    
    def ticket_count(self, obj):
        return obj.ticket_set.count()
    ticket_count.short_description = 'Количество обращений'


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'ticket_count', 'created_at']
    search_fields = ['name', 'comment']
    list_filter = ['is_active', 'created_at']
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'comment', 'is_active')
        }),
    )
    
    def ticket_count(self, obj):
        return obj.ticket_set.count()
    ticket_count.short_description = 'Количество обращений'


@admin.register(TicketStatus)
class TicketStatusAdmin(admin.ModelAdmin):
    list_display = ['name', 'color_display', 'is_working', 'is_final', 'order', 'ticket_count']
    list_editable = ['order', 'is_working', 'is_final']
    ordering = ['order']
    search_fields = ['name', 'description']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'order')
        }),
        ('Настройки', {
            'fields': ('color', 'is_working', 'is_final')
        }),
    )
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px;">{}</span>',
            obj.color, obj.color
        )
    color_display.short_description = 'Цвет'
    
    def ticket_count(self, obj):
        return obj.ticket_set.count()
    ticket_count.short_description = 'Количество обращений'


class TicketCommentInlineForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['author', 'content', 'is_internal', 'created_at']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 2, 'style': 'width: 60%;'}),
        }


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 0
    # Разрешаем редактировать автора, тип и клиента
    readonly_fields = []
    fields = ['author_type', 'author', 'author_client', 'content', 'is_internal', 'created_at']
    form = TicketCommentInlineForm
    autocomplete_fields = ['author_client', 'author']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author', 'author_client')


class TicketAuditInline(admin.TabularInline):
    model = TicketAudit
    extra = 0
    readonly_fields = ['user', 'timestamp', 'action', 'old_value', 'new_value', 'comment']
    fields = ['timestamp', 'user', 'action', 'old_value', 'new_value', 'comment']
    can_delete = False
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').order_by('-timestamp')


class TicketAttachmentInline(admin.TabularInline):
    model = TicketAttachment
    extra = 0
    readonly_fields = ['uploaded_by', 'uploaded_at', 'file_size']
    fields = ['filename', 'file', 'file_size', 'uploaded_by', 'uploaded_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by').order_by('-uploaded_at')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'title_short', 'client', 'organization', 'category', 'status_colored', 
        'assigned_to', 'priority', 'created_at', 'sla_status', 'working_time_display'
    ]
    list_filter = [
        'status', 'priority', 'category', 'organization', 'assigned_to', 'created_at',
        ('category__parent', admin.EmptyFieldListFilter),
    ]
    search_fields = ['title', 'description', 'client__name', 'tags']
    list_editable = ['assigned_to', 'priority']
    readonly_fields = ['created_by', 'updated_at', 'working_time_display', 'sla_status']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'description', 'category', 'client', 'organization', 'priority', 'tags')
        }),
        ('Статус и исполнитель', {
            'fields': ('status', 'assigned_to')
        }),
        ('Временные метки', {
            'fields': ('created_at', 'taken_at', 'resolved_at'),
            'classes': ('collapse',)
        }),
        ('Решение', {
            'fields': ('resolution', 'resolution_notes'),
            'classes': ('collapse',)
        }),
        ('Дополнительно', {
            'fields': ('external_message_id', 'created_by', 'updated_at', 'working_time_display', 'sla_status'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [TicketCommentInline, TicketAttachmentInline, TicketAuditInline]
    autocomplete_fields = ['client', 'organization', 'category', 'status', 'assigned_to']
    
    def title_short(self, obj):
        return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
    title_short.short_description = 'Заголовок'
    
    def status_colored(self, obj):
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px;">{}</span>',
            obj.status.color, obj.status.name
        )
    status_colored.short_description = 'Статус'
    
    def sla_status(self, obj):
        if obj.is_overdue:
            if obj.status.is_final:
                return format_html('<span style="color: red;">⚠ Просрочено</span>')
            else:
                return format_html('<span style="color: red;">⚠ Просрочено</span>')
        elif obj.status.is_final:
            return format_html('<span style="color: green;">✓ Завершено</span>')
        else:
            time_left = obj.time_to_deadline
            if time_left:
                hours_left = int(time_left.total_seconds() / 3600)
                return format_html('<span style="color: orange;">⏰ {}ч</span>', hours_left)
        return '-'
    sla_status.short_description = 'SLA'
    
    def working_time_display(self, obj):
        if obj.working_time:
            total_seconds = int(obj.working_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}ч {minutes}м"
        return '-'
    working_time_display.short_description = 'Время в работе'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'organization', 'category', 'status', 'assigned_to', 'created_by'
        ).prefetch_related('comments', 'audit_logs')
    
    def save_model(self, request, obj, form, change):
        if not change:  # Новое обращение
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        
        # Создаем запись аудита
        if change:
            TicketAudit.objects.create(
                ticket=obj,
                action='updated',
                user=request.user,
                comment='Обращение обновлено через админку'
            )


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'get_author_display', 'content_short', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'author_type', 'created_at', 'author', 'author_client']
    search_fields = ['content', 'ticket__title', 'author__username', 'author_client__name']
    # Разрешаем редактировать дату/время комментария
    readonly_fields = []
    autocomplete_fields = ['ticket', 'author_client']
    
    fieldsets = (
        ('Комментарий', {
            'fields': ('ticket', 'content', 'is_internal', 'created_at')
        }),
        ('Автор', {
            'fields': ('author_type', 'author', 'author_client')
        }),
    )
    
    def get_author_display(self, obj):
        return obj.get_author_name()
    get_author_display.short_description = 'Автор'
    
    def content_short(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
    content_short.short_description = 'Содержание'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)
        
        # Создаем запись аудита
        TicketAudit.objects.create(
            ticket=obj.ticket,
            action='comment_added',
            user=request.user,
            comment=f'Добавлен комментарий: {obj.content[:50]}...'
        )


@admin.register(TicketAudit)
class TicketAuditAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'action', 'user', 'timestamp', 'comment_short']
    list_filter = ['action', 'timestamp', 'user']
    search_fields = ['ticket__title', 'comment', 'user__username']
    readonly_fields = ['ticket', 'action', 'user', 'timestamp', 'old_value', 'new_value', 'comment']
    date_hierarchy = 'timestamp'
    
    def comment_short(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
    comment_short.short_description = 'Комментарий'
    
    def has_add_permission(self, request):
        return False  # Записи аудита создаются автоматически


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'filename', 'file_size_display', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at', 'uploaded_by']
    search_fields = ['filename', 'ticket__title']
    readonly_fields = ['uploaded_by', 'uploaded_at', 'file_size']
    autocomplete_fields = ['ticket']
    
    def file_size_display(self, obj):
        size_kb = obj.file_size / 1024
        if size_kb < 1024:
            return f"{size_kb:.1f} KB"
        else:
            size_mb = size_kb / 1024
            return f"{size_mb:.1f} MB"
    file_size_display.short_description = 'Размер'


@admin.register(TicketTemplate)
class TicketTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active', 'created_by', 'created_at']
    list_filter = ['is_active', 'category', 'created_at']
    search_fields = ['name', 'content_template']
    list_editable = ['is_active']
    autocomplete_fields = ['category']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'category', 'is_active')
        }),
        ('Шаблоны', {
            'fields': ('title_template', 'content_template')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserTelegramAccess)
class UserTelegramAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'telegram_user_id', 'is_allowed', 'comment']
    list_filter = ['is_allowed']
    search_fields = ['user__username', 'user__email', 'telegram_user_id', 'comment']
    autocomplete_fields = ['user']


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = ['message_date', 'chat_title', 'from_username', 'from_user_id', 'media_type', 'text_short', 'linked_ticket']
    list_filter = ['media_type', 'chat_title']
    search_fields = ['text', 'from_username', 'from_user_id', 'chat_title', 'chat_id']
    readonly_fields = ['message_id', 'chat_id', 'chat_title', 'from_user_id', 'from_username', 'from_fullname', 'text', 'media_type', 'message_date', 'created_at', 'linked_ticket', 'linked_action', 'processed_at']
    ordering = ['-message_date']

    def text_short(self, obj):
        return obj.text[:80] + '...' if len(obj.text) > 80 else obj.text
    text_short.short_description = 'Текст'


@admin.register(TelegramGroup)
class TelegramGroupAdmin(admin.ModelAdmin):
    list_display = ['title', 'chat_id', 'is_blocked', 'write_to_stream', 'updated_at']
    list_filter = ['is_blocked', 'write_to_stream']
    search_fields = ['title', 'chat_id']

# Кастомные действия для админки
@admin.action(description='Взять в работу')
def take_tickets(modeladmin, request, queryset):
    working_status = TicketStatus.objects.filter(is_working=True).first()
    if working_status:
        for ticket in queryset:
            ticket.assigned_to = request.user
            ticket.status = working_status
            ticket.taken_at = timezone.now()
            ticket.save()
            
            TicketAudit.objects.create(
                ticket=ticket,
                action='taken',
                user=request.user,
                comment='Взято в работу через админку'
            )


@admin.action(description='Закрыть обращения')
def close_tickets(modeladmin, request, queryset):
    closed_status = TicketStatus.objects.filter(is_final=True).first()
    if closed_status:
        for ticket in queryset:
            ticket.status = closed_status
            ticket.closed_at = timezone.now()
            ticket.save()
            
            TicketAudit.objects.create(
                ticket=ticket,
                action='resolved',
                user=request.user,
                comment='Решено через админку'
            )


# Добавляем действия к админке обращений
TicketAdmin.actions = [take_tickets, close_tickets]