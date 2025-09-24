#!/usr/bin/env python
"""
Скрипт для заполнения поля organization в обращениях из организации клиента.

Запуск:
python fill_organizations.py

Или через Django shell:
python manage.py shell < fill_organizations.py
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vv_help_system.settings')
django.setup()

from tickets.models import Ticket, Client, Organization
from django.db import transaction

def fill_organizations():
    """Заполняет поле organization в обращениях из организации клиента"""
    
    print("🔍 Начинаем заполнение организаций в обращениях...")
    
    # Получаем все обращения без организации
    tickets_without_org = Ticket.objects.filter(organization__isnull=True)
    total_tickets = tickets_without_org.count()
    
    print(f"📊 Найдено обращений без организации: {total_tickets}")
    
    if total_tickets == 0:
        print("✅ Все обращения уже имеют организацию!")
        return
    
    # Статистика
    updated_count = 0
    skipped_count = 0
    errors = []
    
    with transaction.atomic():
        for ticket in tickets_without_org:
            try:
                # Проверяем, есть ли у клиента организация
                if ticket.client and ticket.client.organization:
                    old_org = ticket.organization
                    ticket.organization = ticket.client.organization
                    ticket.save()
                    updated_count += 1
                    
                    print(f"✅ #{ticket.id}: {ticket.client.name} → {ticket.client.organization.name}")
                else:
                    skipped_count += 1
                    print(f"⏭️  #{ticket.id}: {ticket.client.name if ticket.client else 'Без клиента'} (нет организации у клиента)")
                    
            except Exception as e:
                error_msg = f"❌ #{ticket.id}: Ошибка - {str(e)}"
                errors.append(error_msg)
                print(error_msg)
    
    # Итоговая статистика
    print("\n" + "="*50)
    print("📈 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"✅ Обновлено обращений: {updated_count}")
    print(f"⏭️  Пропущено обращений: {skipped_count}")
    print(f"❌ Ошибок: {len(errors)}")
    
    if errors:
        print("\n🚨 ОШИБКИ:")
        for error in errors:
            print(f"   {error}")
    
    print("\n🎉 Заполнение завершено!")
    
    # Дополнительная статистика
    remaining_without_org = Ticket.objects.filter(organization__isnull=True).count()
    print(f"📊 Осталось обращений без организации: {remaining_without_org}")

def show_statistics():
    """Показывает статистику по организациям в обращениях"""
    
    print("\n📊 СТАТИСТИКА ПО ОРГАНИЗАЦИЯМ:")
    
    total_tickets = Ticket.objects.count()
    tickets_with_org = Ticket.objects.filter(organization__isnull=False).count()
    tickets_without_org = total_tickets - tickets_with_org
    
    print(f"📋 Всего обращений: {total_tickets}")
    print(f"✅ С организацией: {tickets_with_org}")
    print(f"❌ Без организации: {tickets_without_org}")
    
    # Топ организаций по обращениям
    from django.db.models import Count
    top_orgs = (Ticket.objects
                .filter(organization__isnull=False)
                .values('organization__name')
                .annotate(count=Count('id'))
                .order_by('-count')[:5])
    
    print("\n🏆 ТОП-5 ОРГАНИЗАЦИЙ ПО ОБРАЩЕНИЯМ:")
    for org_data in top_orgs:
        print(f"   {org_data['organization__name']}: {org_data['count']} обращений")

if __name__ == "__main__":
    print("🚀 СКРИПТ ЗАПОЛНЕНИЯ ОРГАНИЗАЦИЙ В ОБРАЩЕНИЯХ")
    print("="*50)
    
    # Показываем текущую статистику
    show_statistics()
    
    # Спрашиваем подтверждение
    print("\n❓ Продолжить заполнение? (y/N): ", end="")
    if len(sys.argv) > 1 and sys.argv[1] == "--yes":
        confirm = "y"
        print("y (автоподтверждение)")
    else:
        confirm = input().strip().lower()
    
    if confirm in ['y', 'yes', 'да', 'д']:
        fill_organizations()
        show_statistics()
    else:
        print("❌ Операция отменена пользователем")
