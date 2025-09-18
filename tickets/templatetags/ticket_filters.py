from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def split(value, delimiter):
    """Разделяет строку по разделителю"""
    if not value:
        return []
    return value.split(delimiter)

@register.filter
def div(value, arg):
    """Делит значение на аргумент"""
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return 0

@register.filter
def mod(value, arg):
    """Возвращает остаток от деления"""
    try:
        return float(value) % float(arg)
    except (ValueError, ZeroDivisionError):
        return 0

@register.filter
def strip(value):
    """Удаляет пробелы в начале и конце строки"""
    if value is None:
        return ''
    return str(value).strip()


@register.filter
def format_timedelta(value):
    """Форматирует timedelta в человекочитаемый вид: "Хч Ym"""
    if not value or not isinstance(value, timedelta):
        return ''
    total_seconds = int(value.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    parts = []
    if hours:
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    return ' '.join(parts)
