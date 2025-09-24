from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator


class Category(models.Model):
    """Классификатор категорий обращений (2 уровня)"""
    name = models.CharField('Название', max_length=200)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Родительская категория')
    description = models.TextField('Описание', blank=True)
    sla_hours = models.PositiveIntegerField('SLA в часах', default=24, help_text='Контрольный срок обработки в часах')
    is_active = models.BooleanField('Активна', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['parent__name', 'name']
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name
    
    @property
    def is_parent(self):
        return self.parent is None
    
    @property
    def is_child(self):
        return self.parent is not None


class Client(models.Model):
    """Клиенты (поставщики)"""
    name = models.CharField('Имя', max_length=200, default='Неизвестный клиент')
    organization = models.ForeignKey('Organization', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Организация')
    phone = models.CharField('Телефон', max_length=20, blank=True)
    external_id = models.CharField('Внешний ID', max_length=100, blank=True, help_text='ID в внешней системе (например, Telegram)')
    email = models.EmailField('Email', blank=True)
    contact_person = models.CharField('Контактное лицо', max_length=200, blank=True)
    notes = models.TextField('Заметки', blank=True)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'
        ordering = ['name']
    
    def __str__(self):
        if self.organization:
            return f"{self.name} ({self.organization.name})"
        return self.name


class Organization(models.Model):
    """Организация (юр.лицо)"""
    name = models.CharField('Организация', max_length=255, unique=True)
    comment = models.TextField('Комментарий', blank=True, help_text='Дополнительная информация об организации')
    is_active = models.BooleanField('Активна', default=True, help_text='Активные организации отображаются в списках')
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Организация'
        verbose_name_plural = 'Организации'
        ordering = ['name']

    def __str__(self):
        return self.name


class TicketStatus(models.Model):
    """Статусы обращений"""
    name = models.CharField('Название', max_length=100)
    color = models.CharField('Цвет', max_length=7, default='#007bff', help_text='HEX код цвета')
    is_final = models.BooleanField('Финальный статус', default=False, help_text='Обращение завершено')
    is_working = models.BooleanField('В работе', default=False, help_text='Обращение взято в работу')
    order = models.PositiveIntegerField('Порядок', default=0)
    description = models.TextField('Описание', blank=True)
    
    class Meta:
        verbose_name = 'Статус'
        verbose_name_plural = 'Статусы'
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name


class Ticket(models.Model):
    """Обращения поставщиков"""
    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('normal', 'Обычный'),
        ('high', 'Высокий'),
        ('urgent', 'Срочный'),
    ]
    
    # Основная информация
    title = models.CharField('Заголовок', max_length=300)
    description = models.TextField('Описание')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='Категория')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, verbose_name='Клиент')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, verbose_name='Организация', null=True, blank=True)
    priority = models.CharField('Приоритет', max_length=10, choices=PRIORITY_CHOICES, default='normal')
    
    # Статус и исполнители
    status = models.ForeignKey(TicketStatus, on_delete=models.PROTECT, verbose_name='Статус')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Исполнитель')
    
    # Временные метки (корректируемые)
    created_at = models.DateTimeField('Создано', default=timezone.now)
    taken_at = models.DateTimeField('Взято в работу', null=True, blank=True)
    resolved_at = models.DateTimeField('Решено', null=True, blank=True)
    closed_at = models.DateTimeField('Закрыто', null=True, blank=True)
    
    # Решение
    resolution = models.TextField('Решение', blank=True)
    resolution_notes = models.TextField('Заметки к решению', blank=True)
    
    # Дополнительная информация
    external_message_id = models.CharField('ID сообщения', max_length=100, blank=True, help_text='ID сообщения в чате')
    telegram_chat_id = models.CharField('ID чата Telegram', max_length=100, blank=True, help_text='ID чата в Telegram')
    telegram_chat_title = models.CharField('Название чата Telegram', max_length=255, blank=True, help_text='Название чата в Telegram')
    tags = models.CharField('Теги', max_length=500, blank=True, help_text='Через запятую')
    
    # Системные поля
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_tickets', verbose_name='Создано пользователем')
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Обращение'
        verbose_name_plural = 'Обращения'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"#{self.id} - {self.title}"
    
    @property
    def is_overdue(self):
        """Проверка просрочки по SLA"""
        sla_deadline = self.created_at + timezone.timedelta(hours=self.category.sla_hours)
        
        # Для завершенных обращений сравниваем с фактическим временем завершения
        if self.status.is_final and (self.resolved_at or self.closed_at):
            end_time = self.resolved_at or self.closed_at
            return end_time > sla_deadline
        
        # Для активных обращений сравниваем с текущим временем
        return timezone.now() > sla_deadline
    
    @property
    def time_to_deadline(self):
        """Время до дедлайна"""
        if self.status.is_final:
            return None
        
        sla_deadline = self.created_at + timezone.timedelta(hours=self.category.sla_hours)
        return sla_deadline - timezone.now()
    
    @property
    def reaction_time(self):
        """Время реакции (от создания до взятия в работу)"""
        if not self.taken_at:
            return None
        return self.taken_at - self.created_at
    
    @property
    def working_time(self):
        """Время в работе"""
        if not self.taken_at:
            return None
        
        end_time = self.resolved_at or self.closed_at or timezone.now()
        return end_time - self.taken_at


class TicketAudit(models.Model):
    """Аудит изменений обращений"""
    ACTION_CHOICES = [
        ('created', 'Создано'),
        ('status_changed', 'Изменен статус'),
        ('assigned', 'Назначен исполнитель'),
        ('taken', 'Взято в работу'),
        ('returned_to_work', 'Возвращено в работу'),
        ('resolved', 'Решено'),
        ('updated', 'Обновлено'),
        ('comment_added', 'Добавлен комментарий'),
    ]
    
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='audit_logs', verbose_name='Обращение')
    action = models.CharField('Действие', max_length=20, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Пользователь')
    timestamp = models.DateTimeField('Время', default=timezone.now)
    
    # Детали изменения
    old_value = models.TextField('Старое значение', blank=True)
    new_value = models.TextField('Новое значение', blank=True)
    comment = models.TextField('Комментарий', blank=True)
    
    class Meta:
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Записи аудита'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.ticket} - {self.get_action_display()} ({self.timestamp})"


class TicketComment(models.Model):
    """Комментарии к обращениям"""
    AUTHOR_TYPE_CHOICES = [
        ('user', 'Пользователь системы'),
        ('client', 'Клиент'),
    ]
    
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments', verbose_name='Обращение')
    author = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Автор (пользователь)', null=True, blank=True)
    author_type = models.CharField('Тип автора', max_length=10, choices=AUTHOR_TYPE_CHOICES, default='user')
    author_client = models.ForeignKey(Client, on_delete=models.PROTECT, verbose_name='Автор (клиент)', null=True, blank=True)
    content = models.TextField('Содержание')
    is_internal = models.BooleanField('Внутренний комментарий', default=False, help_text='Не виден клиенту')
    created_at = models.DateTimeField('Создано', default=timezone.now)
    
    class Meta:
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'
        ordering = ['created_at']
    
    def get_author_name(self):
        """Получить имя автора комментария"""
        if self.author_type == 'client' and self.author_client:
            return self.author_client.name
        elif self.author_type == 'user' and self.author:
            return self.author.get_full_name() or self.author.username
        return 'Неизвестный автор'
    
    def __str__(self):
        return f"Комментарий к #{self.ticket.id} от {self.get_author_name()}"


class TicketAttachment(models.Model):
    """Вложения к обращениям"""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='attachments', verbose_name='Обращение')
    file = models.FileField('Файл', upload_to='ticket_attachments/%Y/%m/%d/')
    filename = models.CharField('Имя файла', max_length=255)
    file_size = models.PositiveIntegerField('Размер файла')
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Загружено пользователем')
    uploaded_at = models.DateTimeField('Загружено', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.filename} к #{self.ticket.id}"


class TicketTemplate(models.Model):
    """Шаблоны решений для быстрого ответа"""
    name = models.CharField('Название', max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name='Категория')
    title_template = models.CharField(
        'Шаблон заголовка',
        max_length=300,
        blank=True,
        help_text=(
            'Доступные плейсхолдеры: #{ticket_id}, {category}, {created_at}, {sla_hours}. '
            'Формат {created_at}: ДД.ММ.ГГГГ ЧЧ:ММ'
        )
    )
    content_template = models.TextField(
        'Шаблон содержания',
        help_text=(
            'Доступные плейсхолдеры: #{ticket_id}, {category}, {created_at}, {sla_hours}. '
            'Формат {created_at}: ДД.ММ.ГГГГ ЧЧ:ММ'
        )
    )
    is_active = models.BooleanField('Активен', default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Создано пользователем')
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Шаблон решения'
        verbose_name_plural = 'Шаблоны решений'
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category})"


## Удалено: UserProfile (заменено на UserTelegramAccess)


class UserTelegramAccess(models.Model):
    """Допуски Telegram: несколько аккаунтов Telegram на одного пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='telegram_accesses', verbose_name='Пользователь')
    telegram_user_id = models.CharField('Telegram user id', max_length=32, unique=True)
    comment = models.CharField('Комментарий', max_length=255, blank=True)
    is_allowed = models.BooleanField('Разрешен доступ к боту', default=True)

    class Meta:
        verbose_name = 'Доступ Telegram'
        verbose_name_plural = 'Доступы Telegram'
        ordering = ['user__username', 'telegram_user_id']

    def __str__(self):
        return f"{self.user.username} — {self.telegram_user_id}"


class TelegramMessage(models.Model):
    """Поток сообщений из Telegram-групп/чатов"""
    MEDIA_TEXT_CHOICES = [
        ('text', 'Текст'),
        ('photo', 'Фото'),
        ('video', 'Видео'),
        ('document', 'Файл'),
        ('audio', 'Аудио'),
        ('voice', 'Голосовое'),
        ('sticker', 'Стикер'),
        ('other', 'Другое'),
    ]

    message_id = models.CharField('ID сообщения', max_length=64)
    chat_id = models.CharField('ID чата', max_length=64)
    chat_title = models.CharField('Название чата', max_length=255, blank=True)
    from_user_id = models.CharField('ID отправителя', max_length=64, blank=True)
    from_username = models.CharField('Username отправителя', max_length=64, blank=True)
    from_fullname = models.CharField('Имя отправителя', max_length=255, blank=True)
    text = models.TextField('Текст сообщения')
    media_type = models.CharField('Тип', max_length=16, choices=MEDIA_TEXT_CHOICES, default='text')
    message_date = models.DateTimeField('Время сообщения')
    created_at = models.DateTimeField('Загружено', auto_now_add=True)

    # Результат обработки
    linked_ticket = models.ForeignKey('Ticket', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Связанный тикет')
    linked_action = models.CharField('Действие', max_length=16, blank=True, help_text='new/resolve/comment')
    processed_at = models.DateTimeField('Обработано', null=True, blank=True)

    class Meta:
        verbose_name = 'Сообщение Telegram'
        verbose_name_plural = 'Поток Telegram'
        ordering = ['-message_date', '-id']
        indexes = [
            models.Index(fields=['chat_id', 'message_id']),
            models.Index(fields=['from_user_id']),
            models.Index(fields=['message_date']),
        ]

    def __str__(self):
        return f"[{self.chat_title or self.chat_id}] {self.from_username or self.from_fullname}: {self.text[:40]}"


class TelegramGroup(models.Model):
    """Группы/каналы Telegram, в которых бот читает сообщения
    Используется для управления доступом и записью сообщений в поток.
    """
    chat_id = models.CharField('ID чата', max_length=64, unique=True)
    title = models.CharField('Название группы', max_length=255, blank=True)
    is_blocked = models.BooleanField('Заблокировано', default=False)
    write_to_stream = models.BooleanField('Записывать сообщения в поток', default=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Группа Telegram'
        verbose_name_plural = 'Группы Telegram'
        ordering = ['title', 'chat_id']
        indexes = [
            models.Index(fields=['chat_id']),
        ]

    def __str__(self) -> str:
        return f"{self.title or self.chat_id}"