from django.core.management.base import BaseCommand
from django.db import transaction
from tickets.models import Ticket
from django.db.models import Count


class Command(BaseCommand):
    help = 'Заполняет поле organization в обращениях из организации клиента'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет сделано без изменений',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Автоподтверждение без запроса',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        auto_confirm = options['yes']

        self.stdout.write(
            self.style.SUCCESS('🚀 СКРИПТ ЗАПОЛНЕНИЯ ОРГАНИЗАЦИЙ В ОБРАЩЕНИЯХ')
        )
        self.stdout.write('=' * 50)

        # Показываем текущую статистику
        self.show_statistics()

        # Получаем все обращения без организации
        tickets_without_org = Ticket.objects.filter(organization__isnull=True)
        total_tickets = tickets_without_org.count()

        if total_tickets == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ Все обращения уже имеют организацию!')
            )
            return

        self.stdout.write(f'📊 Найдено обращений без организации: {total_tickets}')

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 РЕЖИМ ПРОСМОТРА (--dry-run):'))
            for ticket in tickets_without_org[:10]:  # Показываем первые 10
                if ticket.client and ticket.client.organization:
                    self.stdout.write(
                        f'✅ #{ticket.id}: {ticket.client.name} → {ticket.client.organization.name}'
                    )
                else:
                    self.stdout.write(
                        f'⏭️  #{ticket.id}: {ticket.client.name if ticket.client else "Без клиента"} (нет организации у клиента)'
                    )
            if total_tickets > 10:
                self.stdout.write(f'... и еще {total_tickets - 10} обращений')
            return

        # Спрашиваем подтверждение
        if not auto_confirm:
            confirm = input('\n❓ Продолжить заполнение? (y/N): ').strip().lower()
            if confirm not in ['y', 'yes', 'да', 'д']:
                self.stdout.write(
                    self.style.ERROR('❌ Операция отменена пользователем')
                )
                return

        # Выполняем заполнение
        self.fill_organizations()

        # Показываем итоговую статистику
        self.show_statistics()

    def fill_organizations(self):
        """Заполняет поле organization в обращениях из организации клиента"""
        
        self.stdout.write('🔍 Начинаем заполнение организаций в обращениях...')

        tickets_without_org = Ticket.objects.filter(organization__isnull=True)
        
        # Статистика
        updated_count = 0
        skipped_count = 0
        errors = []

        with transaction.atomic():
            for ticket in tickets_without_org:
                try:
                    # Проверяем, есть ли у клиента организация
                    if ticket.client and ticket.client.organization:
                        ticket.organization = ticket.client.organization
                        ticket.save()
                        updated_count += 1

                        if updated_count <= 20:  # Показываем первые 20
                            self.stdout.write(
                                f'✅ #{ticket.id}: {ticket.client.name} → {ticket.client.organization.name}'
                            )
                        elif updated_count == 21:
                            self.stdout.write('... (продолжаем без вывода)')
                            
                    else:
                        skipped_count += 1
                        if skipped_count <= 10:  # Показываем первые 10 пропущенных
                            self.stdout.write(
                                f'⏭️  #{ticket.id}: {ticket.client.name if ticket.client else "Без клиента"} (нет организации у клиента)'
                            )

                except Exception as e:
                    error_msg = f'❌ #{ticket.id}: Ошибка - {str(e)}'
                    errors.append(error_msg)
                    self.stdout.write(self.style.ERROR(error_msg))

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write('📈 ИТОГОВАЯ СТАТИСТИКА:')
        self.stdout.write(f'✅ Обновлено обращений: {updated_count}')
        self.stdout.write(f'⏭️  Пропущено обращений: {skipped_count}')
        self.stdout.write(f'❌ Ошибок: {len(errors)}')

        if errors:
            self.stdout.write('\n🚨 ОШИБКИ:')
            for error in errors:
                self.stdout.write(f'   {error}')

        self.stdout.write('\n🎉 Заполнение завершено!')

        # Дополнительная статистика
        remaining_without_org = Ticket.objects.filter(organization__isnull=True).count()
        self.stdout.write(f'📊 Осталось обращений без организации: {remaining_without_org}')

    def show_statistics(self):
        """Показывает статистику по организациям в обращениях"""
        
        self.stdout.write('\n📊 СТАТИСТИКА ПО ОРГАНИЗАЦИЯМ:')
        
        total_tickets = Ticket.objects.count()
        tickets_with_org = Ticket.objects.filter(organization__isnull=False).count()
        tickets_without_org = total_tickets - tickets_with_org
        
        self.stdout.write(f'📋 Всего обращений: {total_tickets}')
        self.stdout.write(f'✅ С организацией: {tickets_with_org}')
        self.stdout.write(f'❌ Без организации: {tickets_without_org}')
        
        # Топ организаций по обращениям
        top_orgs = (Ticket.objects
                    .filter(organization__isnull=False)
                    .values('organization__name')
                    .annotate(count=Count('id'))
                    .order_by('-count')[:5])
        
        if top_orgs:
            self.stdout.write('\n🏆 ТОП-5 ОРГАНИЗАЦИЙ ПО ОБРАЩЕНИЯМ:')
            for org_data in top_orgs:
                self.stdout.write(f'   {org_data["organization__name"]}: {org_data["count"]} обращений')
