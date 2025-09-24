from django.core.management.base import BaseCommand
from tickets.models import TelegramMessage, TicketComment
from tickets.management.commands.bot import Command
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Связывает ответные сообщения в потоке с комментариями обращений'

    def add_arguments(self, parser):
        parser.add_argument(
            '--message-id',
            type=str,
            help='ID конкретного сообщения для обработки'
        )
        parser.add_argument(
            '--chat-id',
            type=str,
            help='ID чата для обработки сообщений'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Обработать все необработанные ответные сообщения'
        )

    def handle(self, *args, **options):
        if options['message_id']:
            # Обрабатываем конкретное сообщение
            self.process_specific_message(options['message_id'], options['chat_id'])
        elif options['all']:
            # Обрабатываем все необработанные ответные сообщения
            self.process_all_unprocessed_replies()
        else:
            self.stdout.write(
                self.style.ERROR('Укажите --message-id или --all для обработки')
            )

    def process_specific_message(self, message_id, chat_id):
        """Обрабатывает конкретное сообщение"""
        try:
            message = TelegramMessage.objects.get(message_id=message_id, chat_id=chat_id)
            
            if not message.reply_to_message_id:
                self.stdout.write(
                    self.style.WARNING(f'Сообщение {message_id} не является ответом')
                )
                return
            
            self.stdout.write(f'Обрабатываем сообщение {message_id}...')
            
            # Вызываем автосвязывание напрямую
            self._check_and_link_reply_to_comment(
                message, 
                message.reply_to_message_id, 
                message.chat_id
            )
            
            # Проверяем результат
            comment = TicketComment.objects.filter(telegram_message_id=message_id).first()
            if comment:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Сообщение {message_id} связано с комментарием {comment.id} в обращении #{comment.ticket.id}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'❌ Сообщение {message_id} не было связано')
                )
                
        except TelegramMessage.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Сообщение {message_id} не найдено')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Ошибка при обработке сообщения {message_id}: {e}')
            )

    def process_all_unprocessed_replies(self, bot_command):
        """Обрабатывает все необработанные ответные сообщения"""
        # Находим все ответные сообщения, которые еще не связаны с комментариями
        reply_messages = TelegramMessage.objects.filter(
            reply_to_message_id__isnull=False,
            linked_ticket__isnull=True  # Не связаны с обращениями
        ).order_by('created_at')
        
        self.stdout.write(f'Найдено {reply_messages.count()} необработанных ответных сообщений')
        
        processed = 0
        linked = 0
        
        for message in reply_messages:
            try:
                self.stdout.write(f'Обрабатываем сообщение {message.message_id}...')
                
                # Вызываем автосвязывание
                bot_command._check_and_link_reply_to_comment(
                    message, 
                    message.reply_to_message_id, 
                    message.chat_id
                )
                
                processed += 1
                
                # Проверяем результат
                comment = TicketComment.objects.filter(telegram_message_id=message.message_id).first()
                if comment:
                    linked += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ Связано с комментарием {comment.id} в обращении #{comment.ticket.id}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING('❌ Не связано')
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Ошибка при обработке сообщения {message.message_id}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Обработка завершена: {processed} обработано, {linked} связано'
            )
        )
