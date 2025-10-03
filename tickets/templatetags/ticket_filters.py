from django import template

register = template.Library()

@register.filter
def split(value, delimiter=','):
    """Разделяет строку по разделителю и возвращает список"""
    if not value:
        return []
    return [item.strip() for item in str(value).split(delimiter) if item.strip()]