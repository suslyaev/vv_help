from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from tickets.models import Category, Client, TicketStatus, TicketTemplate


class Command(BaseCommand):
    help = 'Заполняет базу данных начальными данными'

    def handle(self, *args, **options):
        self.stdout.write('Создание начальных данных...')
        
        # Создаем статусы
        statuses_data = [
            {'name': 'Новое', 'color': '#28a745', 'is_working': False, 'is_final': False, 'order': 1},
            {'name': 'В работе', 'color': '#007bff', 'is_working': True, 'is_final': False, 'order': 2},
            {'name': 'Ожидает ответа', 'color': '#ffc107', 'is_working': True, 'is_final': False, 'order': 3},
            {'name': 'Решено', 'color': '#17a2b8', 'is_working': False, 'is_final': True, 'order': 4},
        ]
        
        for status_data in statuses_data:
            status, created = TicketStatus.objects.get_or_create(
                name=status_data['name'],
                defaults=status_data
            )
            if created:
                self.stdout.write(f'Создан статус: {status.name}')
        
        # Создаем категории
        categories_data = [
            # Родительские категории
            {'name': 'Карточки продуктов', 'parent': None, 'sla_hours': 4},
            {'name': 'Поставки', 'parent': None, 'sla_hours': 2},
            {'name': 'Документооборот', 'parent': None, 'sla_hours': 8},
            {'name': 'Технические вопросы', 'parent': None, 'sla_hours': 24},
            {'name': 'Прочее', 'parent': None, 'sla_hours': 48},
            
            # Подкатегории для "Карточки продуктов"
            {'name': 'Корректировка данных', 'parent': 'Карточки продуктов', 'sla_hours': 2},
            {'name': 'Добавление фото', 'parent': 'Карточки продуктов', 'sla_hours': 4},
            {'name': 'Изменение цен', 'parent': 'Карточки продуктов', 'sla_hours': 1},
            {'name': 'Описание продукта', 'parent': 'Карточки продуктов', 'sla_hours': 4},
            
            # Подкатегории для "Поставки"
            {'name': 'График поставок', 'parent': 'Поставки', 'sla_hours': 2},
            {'name': 'Качество товара', 'parent': 'Поставки', 'sla_hours': 1},
            {'name': 'Логистика', 'parent': 'Поставки', 'sla_hours': 4},
            {'name': 'Оплата', 'parent': 'Поставки', 'sla_hours': 8},
            
            # Подкатегории для "Документооборот"
            {'name': 'Сертификаты', 'parent': 'Документооборот', 'sla_hours': 24},
            {'name': 'Договоры', 'parent': 'Документооборот', 'sla_hours': 48},
            {'name': 'Акты', 'parent': 'Документооборот', 'sla_hours': 8},
        ]
        
        for cat_data in categories_data:
            parent = None
            if cat_data['parent']:
                try:
                    parent = Category.objects.get(name=cat_data['parent'])
                except Category.DoesNotExist:
                    continue
            
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                parent=parent,
                defaults={'sla_hours': cat_data['sla_hours']}
            )
            if created:
                self.stdout.write(f'Создана категория: {category.name}')
        
        # Создаем клиента по умолчанию
        default_client, created = Client.objects.get_or_create(
            name='Неизвестный клиент',
            defaults={
                'contact_person': 'Не указано',
                'notes': 'Клиент по умолчанию для новых обращений'
            }
        )
        if created:
            self.stdout.write('Создан клиент по умолчанию')
        
        # Создаем шаблоны решений
        templates_data = [
            {
                'name': 'Стандартный ответ по корректировке',
                'category': 'Корректировка данных',
                'title_template': 'Корректировка карточки продукта #{ticket_id}',
                'content_template': '''Здравствуйте!

Ваша заявка на корректировку карточки продукта принята к обработке.

Детали:
- Номер заявки: #{ticket_id}
- Категория: {category}
- Дата создания: {created_at}

Мы обработаем вашу заявку в течение {sla_hours} часов.

С уважением,
Команда поддержки ВкусВилл'''
            },
            {
                'name': 'Ответ по изменению цен',
                'category': 'Изменение цен',
                'title_template': 'Изменение цены продукта #{ticket_id}',
                'content_template': '''Здравствуйте!

Ваша заявка на изменение цены продукта принята к обработке.

Новая цена будет активирована в течение {sla_hours} часов.

Номер заявки: #{ticket_id}

С уважением,
Команда поддержки ВкусВилл'''
            },
            {
                'name': 'Ответ по качеству товара',
                'category': 'Качество товара',
                'title_template': 'Вопрос по качеству товара #{ticket_id}',
                'content_template': '''Здравствуйте!

Ваше обращение по качеству товара принято к рассмотрению.

Мы свяжемся с вами в течение {sla_hours} часов для уточнения деталей.

Номер заявки: #{ticket_id}

С уважением,
Команда поддержки ВкусВилл'''
            }
        ]
        
        # Гарантируем наличие пользователя для поля created_by у шаблонов
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.filter(is_staff=True).first() or User.objects.first()
        if not admin_user:
            # Создаем технического пользователя, если в системе нет пользователей
            admin_user = User.objects.create_user(
                username='system',
                password=User.objects.make_random_password(),
                is_superuser=True,
                is_staff=True
            )
            self.stdout.write('Создан технический пользователь: system')

        for template_data in templates_data:
            try:
                category = Category.objects.get(name=template_data['category'])
                template, created = TicketTemplate.objects.get_or_create(
                    name=template_data['name'],
                    category=category,
                    defaults={
                        'title_template': template_data['title_template'],
                        'content_template': template_data['content_template'],
                        'created_by': admin_user
                    }
                )
                if created:
                    self.stdout.write(f'Создан шаблон: {template.name}')
            except Category.DoesNotExist:
                self.stdout.write(f'Категория "{template_data["category"]}" не найдена')
        
        # Группа прав "Исполнитель"
        performer_group, created = Group.objects.get_or_create(name='Исполнитель')
        if created:
            self.stdout.write('Создана группа: Исполнитель')

        # Сбрасываем и назначаем точный набор прав согласно БД
        performer_group.permissions.clear()

        # Точный список прав согласно текущей БД (как в админке):
        wanted = [
            # Пользователи
            'view_user',
            # Категории
            'add_category', 'change_category', 'delete_category', 'view_category',
            # Клиенты (без delete)
            'add_client', 'change_client', 'view_client',
            # Обращения (без delete)
            'add_ticket', 'change_ticket', 'view_ticket',
            # Вложения (все)
            'add_ticketattachment', 'change_ticketattachment', 'delete_ticketattachment', 'view_ticketattachment',
            # Аудит (только просмотр)
            'view_ticketaudit',
            # Комментарии (все)
            'add_ticketcomment', 'change_ticketcomment', 'delete_ticketcomment', 'view_ticketcomment',
            # Статусы (только просмотр)
            'view_ticketstatus',
            # Шаблоны решений (все)
            'add_tickettemplate', 'change_tickettemplate', 'delete_tickettemplate', 'view_tickettemplate',
        ]
        added = 0
        for code in wanted:
            perm = Permission.objects.filter(codename=code).first()
            if perm:
                performer_group.permissions.add(perm)
                added += 1
        performer_group.save()
        self.stdout.write(f'Группе "Исполнитель" назначено прав: {added}')
        
        self.stdout.write(
            self.style.SUCCESS('Начальные данные успешно созданы!')
        )
