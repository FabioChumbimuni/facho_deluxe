# scripts/templatetags/hasattr_filter.py
from django import template
import builtins

register = template.Library()

@register.filter(name='hasattr')
def hasattr_filter(value, arg):
    """Devuelve True si 'value' tiene el atributo 'arg' utilizando la función incorporada."""
    return builtins.hasattr(value, arg)
