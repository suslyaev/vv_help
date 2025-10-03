from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def split(value, delimiter=','):
    """Разделяет строку по разделителю и возвращает список"""
    if not value:
        return []
    return [item.strip() for item in str(value).split(delimiter) if item.strip()]

@register.filter
def div(value, arg):
    """Делит значение на аргумент"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def strip(value):
    """Убирает пробелы в начале и конце строки"""
    if value is None:
        return ''
    return str(value).strip()

@register.filter
def format_timedelta(value):
    """Форматирует timedelta в читаемый вид"""
    if not value or not isinstance(value, timedelta):
        return ''
    
    total_seconds = int(value.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds} сек"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if seconds > 0:
            return f"{minutes} мин {seconds} сек"
        else:
            return f"{minutes} мин"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes > 0:
            return f"{hours} ч {minutes} мин"
        else:
            return f"{hours} ч"
    else:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        if hours > 0:
            return f"{days} дн {hours} ч"
        else:
            return f"{days} дн"