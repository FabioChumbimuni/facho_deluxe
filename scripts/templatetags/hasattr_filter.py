from django import template
import builtins  # Importa el módulo de funciones incorporadas

register = template.Library()

@register.filter(name='hasattr')
def hasattr_filter(value, arg):
    """Devuelve True si 'value' tiene el atributo 'arg', usando la función incorporada."""
    return builtins.hasattr(value, arg)
