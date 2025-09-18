from django import template

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
