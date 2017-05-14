from __future__ import unicode_literals
from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
from django.utils.html import urlize
from ..utils import viglink

register = template.Library()


@register.filter(is_safe=True, needs_autoescape=True)
@stringfilter
def urlise(value, autoescape=None):
    """Like the built-in Django urlize filter,
    but strips the 'http://' from the link text,
    and replaces Megabus URLs with venal Affiliate Window ones
    """
    megabus = 'https://www.awin1.com/awclick.php?mid=2678&amp;id=242611&amp;clickref=notes'
    markup = urlize(value, nofollow=True).replace('">https://', '">', 1).replace('">http://', '">', 1)
    markup = markup.replace('http://megabus.com', megabus, 1).replace('http://uk.megabus.com', megabus, 1)
    if 'nationalexpress' in markup:
        national_express = '{}'.format(viglink('http://www.nationalexpress.com'))
        markup = markup.replace('http://nationalexpress.com', national_express, 1)
        markup = markup.replace('http://www.nationalexpress.com', national_express, 1)
    return mark_safe(markup)
