from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from asgiref.sync import sync_to_async

from tickets.models import Ticket, Category, Client, UserProfile, TicketStatus
from django.contrib.auth.models import User

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters


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

        application.add_handler(CommandHandler('start', self.start))
        application.add_handler(MessageHandler(filters.ALL, self.on_message))

        self.stdout.write(self.style.SUCCESS('Telegram bot started. Press Ctrl+C to stop.'))
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        is_allowed = await self._is_allowed_user(user.id)
        if not is_allowed:
            await update.message.reply_text('Доступ запрещён.')
            return
        await update.message.reply_text('Бот готов. Перешлите сообщение клиента, чтобы создать обращение.')

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.effective_message
        user = update.effective_user

        # Проверяем право доступа
        if not await self._is_allowed_user(user.id):
            return

        # Обрабатываем только пересланные сообщения
        if not message or not (message.forward_date or message.forward_from or getattr(message, 'forward_from_chat', None)):
            return

        text = message.text or message.caption or ''
        if not text:
            await message.reply_text('Пустое сообщение — ничего не создано.')
            return

        # Исходная дата — если есть
        created_at = None
        if message.forward_date:
            created_at = timezone.make_aware(message.forward_date) if timezone.is_naive(message.forward_date) else message.forward_date

        # Внешний ID клиента из пересланного сообщения, если доступно
        external_id = None
        if message.forward_from:
            # Переслано от пользователя
            external_id = str(message.forward_from.id)
        elif getattr(message, 'forward_from_chat', None):
            # Переслано из канала/группы
            external_id = str(message.forward_from_chat.id)

        # Создаём тикет
        ticket = await sync_to_async(self._create_ticket_sync)(
            author_telegram_id=str(user.id),
            text=text,
            external_client_id=external_id,
            created_at_override=created_at,
            message_id=str(message.message_id),
        )

        await message.reply_text(f'Обращение #{ticket.id} создано.')

    async def _is_allowed_user(self, telegram_user_id: int) -> bool:
        return await sync_to_async(
            lambda: UserProfile.objects.filter(
                telegram_user_id=str(telegram_user_id), can_use_telegram_bot=True
            ).exists()
        )()

    def _create_ticket_sync(self, author_telegram_id: str, text: str, external_client_id: str | None, created_at_override, message_id: str | None):
        with transaction.atomic():
            # Пользователь-создатель — по профилю телеграм
            creator = (
                User.objects.filter(
                    profile__telegram_user_id=author_telegram_id,
                    profile__can_use_telegram_bot=True,
                ).first()
            )
            if not creator:
                # Фолбэк: берём первого суперпользователя/админа
                creator = User.objects.filter(is_staff=True).first() or User.objects.first()

            # Категория — родительская "Обращения от поставщиков"
            category = (
                Category.objects.filter(name__icontains='Обращения от поставщиков', parent__isnull=True).first()
                or Category.objects.first()
            )

            # Статус новый — возьмём первый не финальный
            status = TicketStatus.objects.filter(is_final=False).order_by('order').first() or TicketStatus.objects.first()

            client = None
            if external_client_id:
                client = Client.objects.filter(external_id=external_client_id).first()

            if not client:
                # Используем существующего клиента "Неизвестный клиент" или создаём один раз
                client = Client.objects.filter(name='Неизвестный клиент').first()
                if not client:
                    client = Client.objects.create(name='Неизвестный клиент')

            ticket = Ticket(
                title='Создано из Telegram',
                description=text,
                category=category,
                client=client,
                status=status,
                priority='normal',
                created_by=creator,
            )
            if message_id:
                ticket.external_message_id = message_id
            if created_at_override:
                ticket.created_at = created_at_override
            ticket.save()

            return ticket


