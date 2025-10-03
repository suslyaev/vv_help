from django import template

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