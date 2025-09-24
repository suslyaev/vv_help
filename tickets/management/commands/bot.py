from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from asgiref.sync import sync_to_async

from tickets.models import Ticket, Category, Client, TicketStatus, UserTelegramAccess, TelegramMessage, TelegramGroup, TicketComment
from django.contrib.auth.models import User

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import logging


def get_setting(name: str, default: str = "") -> str:
    return getattr(settings, name, default)


class Command(BaseCommand):
    help = 'Runs Telegram bot that creates tickets from forwarded messages.'

    def add_arguments(self, parser):
        parser.add_argument('--token', type=str, help='Telegram bot token (overrides settings.TELEGRAM_BOT_TOKEN)')

    def handle(self, *args, **options):
        token = options.get('token') or get_setting('TELEGRAM_BOT_TOKEN')
        if not token:
            self.stderr.write(self.style.ERROR('TELEGRAM_BOT_TOKEN is not set. Provide via settings or --token.'))
            return

        application = Application.builder().token(token).build()

        # Обрабатываем /start только в личных чатах
        application.add_handler(CommandHandler('start', self.start, filters=filters.ChatType.PRIVATE))
        # Логируем любые сообщения
        application.add_handler(MessageHandler(filters.ALL, self.on_message))

        self.stdout.write(self.style.SUCCESS('Telegram bot started. Press Ctrl+C to stop.'))
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Обрабатывать команду только в личке, и отвечать только авторизованным
        if update.effective_chat and (update.effective_chat.type or '').lower() != 'private':
            return
        user = update.effective_user
        if not await self._is_allowed_user(user.id):
            # Не отвечаем неавторизованным
            return
        await update.message.reply_text('Бот готов. Перешлите сообщение клиента, чтобы создать обращение.')

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.effective_message
        user = update.effective_user
        try:
            logging.info(
                "tg_update: chat_type=%s chat_id=%s user_id=%s username=%s msg_id=%s",
                getattr(update.effective_chat, 'type', None),
                getattr(update.effective_chat, 'id', None),
                getattr(user, 'id', None),
                getattr(user, 'username', None),
                getattr(message, 'message_id', None),
            )
        except Exception:
            pass

        if not message:
            return

        # Определяем текст и тип медиа для лога
        media_type = 'text'
        text = message.text or message.caption or ''
        if not text:
            if message.photo:
                media_type, text = 'photo', 'Фото'
            elif message.video:
                media_type, text = 'video', 'Видео'
            elif message.document:
                media_type, text = 'document', 'Файл'
            elif getattr(message, 'audio', None):
                media_type, text = 'audio', 'Аудио'
            elif getattr(message, 'voice', None):
                media_type, text = 'voice', 'Голосовое'
            elif getattr(message, 'sticker', None):
                media_type, text = 'sticker', 'Стикер'
            else:
                media_type, text = 'other', 'Другое'

        # Исходная дата — если есть (forward_date), иначе дата самого сообщения
        created_at = None
        if getattr(message, 'forward_date', None):
            created_at = timezone.make_aware(message.forward_date) if timezone.is_naive(message.forward_date) else message.forward_date
        else:
            created_at = timezone.make_aware(message.date) if timezone.is_naive(message.date) else message.date

        # Внешний ID клиента из пересланного сообщения, если доступно
        external_id = None
        if getattr(message, 'forward_from', None):
            # Переслано от пользователя
            external_id = str(message.forward_from.id)
        elif getattr(message, 'forward_from_chat', None):
            # Переслано из канала/группы
            external_id = str(message.forward_from_chat.id)

        # Решаем: логировать ли сообщение в поток
        chat_type = (message.chat.type or '').lower()
        should_log = await sync_to_async(self._should_log_to_stream)(message)
        if should_log:
            await sync_to_async(self._log_message_sync)(message, text, media_type)
        try:
            logging.info("tg_logged: chat_type=%s msg_id=%s", getattr(message.chat, 'type', None), getattr(message, 'message_id', None))
        except Exception:
            pass

        # Создаём тикет только для личных чатов. В группах/каналах — только логируем
        if chat_type != 'private':
            try:
                logging.info("tg_skip_create_ticket_non_private: chat_type=%s", chat_type)
            except Exception:
                pass
            return

        # В личных чатах — проверяем право доступа; не отвечаем, если нет доступа
        if not await self._is_allowed_user(user.id):
            try:
                logging.info("tg_skip_create_ticket_unauthorized: user_id=%s", getattr(user, 'id', None))
            except Exception:
                pass
            return

        # Создаём тикет (заголовок будет сформирован по шаблону маршрута)
        ticket = await sync_to_async(self._create_ticket_sync)(
            author_telegram_id=str(user.id),
            text=text,
            external_client_id=external_id,
            created_at_override=created_at,
            message_id=str(message.message_id),
            chat_id=str(message.chat.id),
            chat_title=message.chat.title or message.chat.username or '',
            override_title=None,  # Не передаем override_title, чтобы использовался шаблон маршрута
        )

        await message.reply_text(f'Обращение #{ticket.id} создано.')
        try:
            logging.info("tg_ticket_created: ticket_id=%s", ticket.id)
        except Exception:
            pass

    async def _is_allowed_user(self, telegram_user_id: int) -> bool:
        telegram_id_str = str(telegram_user_id)
        def _check():
            return UserTelegramAccess.objects.filter(telegram_user_id=telegram_id_str, is_allowed=True).exists()
        return await sync_to_async(_check)()

    def _create_ticket_sync(self, author_telegram_id: str, text: str, external_client_id: str | None, created_at_override, message_id: str | None, chat_id: str | None = None, chat_title: str | None = None, override_title: str | None = None):
        with transaction.atomic():
            # Пользователь-создатель — по профилю телеграм
            # Пытаемся найти по множественным доступам
            creator = None
            access = UserTelegramAccess.objects.filter(telegram_user_id=author_telegram_id, is_allowed=True).select_related('user').first()
            if access:
                creator = access.user
            # fallback больше не используем UserProfile
            if not creator:
                # Фолбэк: берём первого суперпользователя/админа
                creator = User.objects.filter(is_staff=True).first() or User.objects.first()

            # Определяем клиента
            client = None
            if external_client_id:
                client = Client.objects.filter(external_id=external_client_id).first()

            if not client:
                # Используем существующего клиента "Неизвестный клиент" или создаём один раз
                client = Client.objects.filter(name='Неизвестный клиент').first()
                if not client:
                    client = Client.objects.create(name='Неизвестный клиент')

            # Определяем группу Telegram
            telegram_group = None
            if chat_id:
                from tickets.models import TelegramGroup
                telegram_group = TelegramGroup.objects.filter(chat_id=chat_id).first()

            # Ищем подходящий маршрут
            from tickets.models import TelegramRoute
            route = TelegramRoute.find_route(telegram_group=telegram_group, client=client, organization=None)

            # Определяем категорию и приоритет из маршрута или используем значения по умолчанию
            if route:
                category = route.category
                priority = route.priority
                # Формируем заголовок по шаблону маршрута
                if not override_title:
                    client_name = client.name if client else 'Неизвестный клиент'
                    group_name = chat_title or 'Неизвестная группа'
                    message_id_str = message_id or 'N/A'
                    message_date = created_at_override or timezone.now()
                    
                    title = route.format_title(
                        group_name=group_name,
                        client_name=client_name,
                        message_id=message_id_str,
                        message_date=message_date
                    )
                else:
                    title = override_title
            else:
                # Используем значения по умолчанию
                category = (
                    Category.objects.filter(name__icontains='Обращения от поставщиков', parent__isnull=True).first()
                    or Category.objects.first()
                )
                priority = 'normal'
                title = (override_title if override_title else (text[:100] if text else 'Сообщение из Telegram'))

            # Статус новый — возьмём первый не финальный
            status = TicketStatus.objects.filter(is_final=False).order_by('order').first() or TicketStatus.objects.first()

            ticket = Ticket(
                title=title,
                description=text,
                category=category,
                client=client,
                status=status,
                priority=priority,
                created_by=creator,
            )
            if message_id:
                ticket.external_message_id = message_id
            if chat_id:
                ticket.telegram_chat_id = chat_id
            if chat_title:
                ticket.telegram_chat_title = chat_title
            if created_at_override:
                ticket.created_at = created_at_override
            ticket.save()

            return ticket

    def _log_message_sync(self, message, text: str, media_type: str):
        chat = message.chat
        chat_id = str(chat.id)
        chat_title = chat.title or chat.username or ''
        from_user = message.from_user
        # Получаем ID сообщения, на которое отвечают (если есть)
        reply_to_message_id = ''
        if getattr(message, 'reply_to_message', None):
            reply_to_message_id = str(message.reply_to_message.message_id)

        # Проверяем, существует ли уже сообщение с таким ID
        existing_message = TelegramMessage.objects.filter(
            message_id=str(message.message_id),
            chat_id=chat_id
        ).first()

        if existing_message:
            # Обновляем существующее сообщение
            existing_message.text = text
            existing_message.media_type = media_type
            existing_message.from_username = (from_user.username if from_user and from_user.username else '')
            existing_message.from_fullname = (from_user.full_name if from_user else '')
            existing_message.message_date = (timezone.make_aware(message.date) if timezone.is_naive(message.date) else message.date)
            existing_message.save()
            telegram_message = existing_message
            logging.info(f"Updated existing Telegram message: {message.message_id} in chat {chat_id}")
        else:
            # Создаем новое сообщение в потоке
            telegram_message = TelegramMessage.objects.create(
                message_id=str(message.message_id),
                reply_to_message_id=reply_to_message_id,
                chat_id=chat_id,
                chat_title=chat_title,
                from_user_id=str(from_user.id) if from_user else '',
                from_username=(from_user.username if from_user and from_user.username else ''),
                from_fullname=(from_user.full_name if from_user else ''),
                text=text,
                media_type=media_type,
                message_date=(timezone.make_aware(message.date) if timezone.is_naive(message.date) else message.date),
            )
            logging.info(f"Created new Telegram message: {message.message_id} in chat {chat_id}")

        # Если это ответ на сообщение, проверяем, связано ли исходное сообщение с комментарием
        if reply_to_message_id:
            self._check_and_link_reply_to_comment(telegram_message, reply_to_message_id, chat_id)

    def _check_and_link_reply_to_comment(self, telegram_message, reply_to_message_id: str, chat_id: str):
        """Проверяет, является ли ответ на сообщение, связанное с комментарием, и если да - добавляет ответ как комментарий"""
        try:
            # Ищем исходное сообщение в потоке
            original_message = TelegramMessage.objects.filter(
                message_id=reply_to_message_id,
                chat_id=chat_id
            ).first()
            
            if not original_message:
                return
            
            # Проверяем, связано ли исходное сообщение с обращением через комментарий
            # Ищем комментарий, который имеет telegram_message_id равный ID исходного сообщения
            original_comment = TicketComment.objects.filter(
                telegram_message_id=reply_to_message_id
            ).first()
            
            if not original_comment:
                return
            
            # Если нашли комментарий, создаем новый комментарий для ответа
            # Определяем автора комментария
            author_type = 'client'
            author_client = None
            author_user = None
            
            # Сначала проверяем, является ли отправитель системным пользователем
            if telegram_message.from_user_id:
                try:
                    # Проверяем, есть ли пользователь в UserTelegramAccess
                    from tickets.models import UserTelegramAccess
                    telegram_access = UserTelegramAccess.objects.filter(
                        telegram_user_id=telegram_message.from_user_id,
                        is_allowed=True
                    ).select_related('user').first()
                    
                    if telegram_access:
                        # Это системный пользователь
                        author_type = 'user'
                        author_user = telegram_access.user
                        logging.info(f"Reply from system user: {telegram_access.user.username}")
                    else:
                        # Это клиент, ищем по external_id
                        author_client = Client.objects.filter(external_id=telegram_message.from_user_id).first()
                        if not author_client:
                            # Если клиент не найден, ищем существующего "Неизвестного клиента" или создаем нового
                            existing_unknown = Client.objects.filter(
                                name='Неизвестный клиент',
                                external_id=telegram_message.from_user_id
                            ).first()
                            
                            if existing_unknown:
                                author_client = existing_unknown
                            else:
                                # Создаем нового клиента с уникальным именем
                                author_client = Client.objects.create(
                                    name=f'Неизвестный клиент ({telegram_message.from_username or telegram_message.from_user_id})',
                                    external_id=telegram_message.from_user_id,
                                    contact_person=telegram_message.from_fullname or telegram_message.from_username or 'Не указано'
                                )
                except Exception as e:
                    # Если произошла любая ошибка, создаем комментарий от неизвестного клиента
                    logging.warning(f"Error determining author type for external_id {telegram_message.from_user_id}: {e}")
                    try:
                        author_client = Client.objects.create(
                            name=f'Неизвестный клиент ({telegram_message.from_username or telegram_message.from_user_id})',
                            external_id=telegram_message.from_user_id,
                            contact_person=telegram_message.from_fullname or telegram_message.from_username or 'Не указано'
                        )
                    except Exception as create_error:
                        logging.error(f"Failed to create client: {create_error}")
                        author_client = None
            
            # Создаем новый комментарий
            new_comment = TicketComment.objects.create(
                ticket=original_comment.ticket,
                author=author_user,
                author_type=author_type,
                author_client=author_client,
                content=telegram_message.text,
                is_internal=False,
                telegram_message_id=telegram_message.message_id,
                created_at=telegram_message.message_date
            )
            
            # Обновляем сообщение в потоке, связывая его с обращением
            telegram_message.linked_ticket = original_comment.ticket
            telegram_message.linked_action = 'add_comment'
            telegram_message.save()
            
            logging.info(f"Auto-linked reply to comment: message_id={telegram_message.message_id}, comment_id={new_comment.id}, ticket_id={original_comment.ticket.id}")
            
        except Exception as e:
            logging.error(f"Failed to auto-link reply to comment: {e}", exc_info=True)

    def _should_log_to_stream(self, message) -> bool:
        """Определяет, нужно ли писать сообщение в поток.
        - Личные чаты: не логируем
        - Группы/каналы: логируем только если группа не заблокирована и включена запись в поток
        При первом попадании неизвестной группы — создаём запись с write_to_stream=True по умолчанию.
        """
        chat = message.chat
        chat_type = (chat.type or '').lower()
        if chat_type == 'private':
            return False
        chat_id = str(chat.id)
        title = chat.title or chat.username or ''
        grp, created = TelegramGroup.objects.get_or_create(chat_id=chat_id, defaults={
            'title': title,
            'is_blocked': False,
            'write_to_stream': True,
        })
        # Обновим название при необходимости
        if not created and title and grp.title != title:
            grp.title = title
            grp.save(update_fields=['title', 'updated_at'])
        return (not grp.is_blocked) and grp.write_to_stream


