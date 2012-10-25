"""
Custom fields.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES
from django.forms.fields import CharField
#from django.forms import ModelMultipleChoiceField
from django.utils.translation import ugettext_lazy as _


class BasicCommaSeparatedUserField(CharField):
    """
    An internal base class for CommaSeparatedUserField.

    This class is not intended to be used directly in forms.
    Use CommaSeparatedUserField instead,
    to benefit from the auto-complete fonctionality if available.

    """
    default_error_messages = {
        'unknown': _("Some usernames are unknown or no more active: {users}."),
        'max': _("Ensure this value has at most {limit_value} distinct items (it has {show_value})."),
        'min': _("Ensure this value has at least {limit_value} distinct items (it has {show_value})."),
        'filtered': _("Some usernames are rejected: {users}."),
        'filtered_user': _("{user.username}"),
        'filtered_user_with_reason': _("{user.username} ({reason})"),
    }

    def __init__(self, max=None, min=None, user_filter=None, *args, **kwargs):
        self.max, self.min, self.user_filter = max, min, user_filter
        label = kwargs.get('label')
        if isinstance(label, tuple):
            self.pluralized_labels = label
            kwargs.update(label=label[max == 1])
        super(BasicCommaSeparatedUserField, self).__init__(*args, **kwargs)

    def set_max(self, max):
        """Supersede the max value and ajust accordingly the label."""
        pluralized_labels = getattr(self, 'pluralized_labels', None)
        if pluralized_labels:
            self.label = pluralized_labels[max == 1]
        self.max = max

    def to_python(self, value):
        """Normalize data to an unordered list of distinct, non empty, whitespace-stripped strings."""
        value = super(BasicCommaSeparatedUserField, self).to_python(value)
        if value in EMPTY_VALUES: # Return an empty list if no useful input was given.
            return []
        return list(set([name.strip() for name in value.split(',') if name and not name.isspace()]))

    def validate(self, value):
        """Check the limits."""
        super(BasicCommaSeparatedUserField, self).validate(value)
        if value in EMPTY_VALUES:
            return
        count = len(value)
        if self.max and count > self.max:
            raise ValidationError(self.error_messages['max'].format(limit_value=self.max, show_value=count))
        if self.min and count < self.min:
            raise ValidationError(self.error_messages['min'].format(limit_value=self.min, show_value=count))

    def clean(self, value):
        """Check names are valid and filter them."""
        #import ipdb; ipdb.set_trace()
        names = super(BasicCommaSeparatedUserField, self).clean(value)

        # another hack
        names = [la.replace("u'", "") for la in names]
        names = [la.replace("']", "") for la in names]
        names = [la.replace("[", "") for la in names]
        names = [la.replace("'", "") for la in names]

        #print names
        if not names:
            return []
        users = list(User.objects.filter(is_active=True, username__in=names))
        unknown_names = set(names) ^ set([u.username for u in users])
        errors = []
        if unknown_names:
            errors.append(self.error_messages['unknown'].format(users=', '.join(unknown_names)))
        if self.user_filter:
            filtered_names = []
            for u in users[:]:
                try:
                    reason = self.user_filter(u)
                    if reason is not None:
                        users.remove(u)
                        filtered_names.append(
                            self.error_messages[
                                'filtered_user_with_reason' if reason else 'filtered_user'
                            ].format(user=u, reason=reason)
                        )
                except ValidationError, e:
                    users.remove(u)
                    errors.extend(e.messages)
            if filtered_names:
                errors.append(self.error_messages['filtered'].format(users=', '.join(filtered_names)))
        if errors:
            raise ValidationError(errors)
        return users

###############################################################################
###############################################################################

from django import forms
from django.core.urlresolvers import reverse
from django.forms.util import flatatt

#from django.utils import simplejson
from django.utils.safestring import mark_safe

from django.template.loader import render_to_string
from django.template.defaultfilters import escapejs

from ajax_select import get_lookup
from ajax_select.fields import bootstrap

#from ajax_select.fields import AutoCompleteSelectMultipleField
#from ajax_select.widgets import AutoCompleteSelectMultipleWidget


class CommaAutoCompleteSelectMultipleWidget(forms.widgets.SelectMultiple):

    """ widget to select multiple models """

    add_link = None

    def __init__(self,
                 channel,
                 help_text='',
                 show_help_text=False,
                 *args, **kwargs):
        super(CommaAutoCompleteSelectMultipleWidget,
              self).__init__(*args, **kwargs)
        self.channel = channel

        self.help_text = help_text or _('Enter text to search.')
        self.show_help_text = show_help_text

    def render(self, name, value, attrs=None):

        if value is None:
            value = []

        final_attrs = self.build_attrs(attrs)
        self.html_id = final_attrs.pop('id', name)

        lookup = get_lookup(self.channel)

        # eg. value = [3002L, 1194L]
        if value:
            # pk,pk, of current
            current_ids = "," + ",".join(str(pk) for pk in value) + ","
        else:
            current_ids = ","

        #######################################################################
        # names hack
        aux_value = value
        #value = User.objects.get(username__in=value
                                        #).values_list('id', flat=True)

        ## hack inside the hack: if there's only one recipient, here arrive
        ## the string with the username instead of a list of usernames with
        ## just this name. Hence, I make this a one-element list:
        if isinstance(value, unicode):
            value = [value, ]

        import ipdb; ipdb.set_trace()
        value = [User.objects.get(username=v).id for v in value]
        objects = lookup.get_objects(value)
        value = aux_value
        #######################################################################

        # text repr of currently selected items
        current_repr_json = []
        for obj in objects:
            display = lookup.format_item_display(obj)
            current_repr_json.append(
                        """new Array("%s",%s)""" % (escapejs(display), obj.pk))
        current_reprs = mark_safe(
                                "new Array(%s)" % ",".join(current_repr_json))

        if self.show_help_text:
            help_text = self.help_text
        else:
            help_text = ''

        context = {
            'name': name,
            'html_id': self.html_id,
            'min_length': getattr(lookup, 'min_length', 1),
            'lookup_url': reverse('ajax_lookup',
                                  kwargs={'channel': self.channel}),
            'current': value,
            'current_ids': current_ids,
            'current_reprs': current_reprs,
            'help_text': help_text,
            'extra_attrs': mark_safe(flatatt(final_attrs)),
            'func_slug': self.html_id.replace("-", ""),
            'add_link': self.add_link,
        }
        context.update(bootstrap())

        return mark_safe(
                 render_to_string(
                     ('autocompleteselectmultiple_%s.html' % self.channel,
                      'autocompleteselectmultiple.html'), context
                 )
               )

    def value_from_datadict(self, data, files, name):
        # eg. u'members': [u'229,4688,190']
        #import ipdb; ipdb.set_trace()
        return [val for val in data.get(name, '').split(',') if val]

    def id_for_label(self, id_):
        return '%s_text' % id_


class CommaAutoCompleteSelectMultipleField(forms.fields.CharField):
    """  asdf """

    def __init__(self, channel, *args, **kwargs):
        as_default_help = u'Enter text to search.'
        help_text = kwargs.get('help_text')
        if not (help_text is None):
            try:
                en_help = help_text.translate('en')
            except AttributeError:
                pass
            else:
                # monkey patch the django default help text to the ajax selects default help text
                django_default_help = u'Hold down "Control", or "Command" on a Mac, to select more than one.'
                if django_default_help in en_help:
                    en_help = en_help.replace(django_default_help,'').strip()
                    # probably will not show up in translations
                    if en_help:
                        help_text = _(en_help)
                    else:
                        help_text = _(as_default_help)
        else:
            help_text = _(as_default_help)

        # admin will also show help text, so by default do not show it in widget
        # if using in a normal form then set to True so the widget shows help
        show_help_text = kwargs.pop('show_help_text',False)

        kwargs['widget'] = CommaAutoCompleteSelectMultipleWidget(
                                channel=channel, help_text=help_text,
                                show_help_text=show_help_text)

        super(CommaAutoCompleteSelectMultipleField,
              self).__init__(channel, *args, **kwargs)


###############################################################################
###############################################################################

d = getattr(settings, 'POSTMAN_AUTOCOMPLETER_APP', {})
app_name = d.get('name', 'ajax_select')
field_name = d.get('field', 'AutoCompleteField')
#print field_name
arg_name = d.get('arg_name', 'channel')
arg_default = d.get('arg_default') # the minimum to declare to enable the feature

autocompleter_app = {}
if app_name in settings.INSTALLED_APPS and arg_default:
    autocompleter_app['is_active'] = True
    autocompleter_app['name'] = app_name
    autocompleter_app['version'] = getattr(__import__(app_name, globals(), locals(), ['__version__']), '__version__', None)
    # does something like "from ajax_select.fields import AutoCompleteField"
    auto_complete_field = getattr(__import__(app_name + '.fields', globals(), locals(), [field_name]), field_name)

    class CommaSeparatedUserField(BasicCommaSeparatedUserField, auto_complete_field):
        def __init__(self, *args, **kwargs):
            if not args and arg_name not in kwargs:
                kwargs.update([(arg_name,arg_default)])
            super(CommaSeparatedUserField, self).__init__(*args, **kwargs)

        def set_arg(self, value):
            """Same as it is done in ajax_select.fields.py for Fields and Widgets."""
            if hasattr(self, arg_name):
                setattr(self, arg_name, value)
            if hasattr(self.widget, arg_name):
                setattr(self.widget, arg_name, value)

    #class CommaSeparatedUserField(ModelMultipleChoiceField, auto_complete_field):
            #def __init__(self, *args, **kwargs):
                #if not args and arg_name not in kwargs:
                    #kwargs.update([(arg_name,arg_default)])
                #kwargs['queryset'] = User.objects.all()
                #super(CommaSeparatedUserField, self).__init__(*args, **kwargs)
    #
            #def set_arg(self, value):
                #"""Same as it is done in ajax_select.fields.py for Fields and Widgets."""
                #if hasattr(self, arg_name):
                    #setattr(self, arg_name, value)
                #if hasattr(self.widget, arg_name):
                    #setattr(self.widget, arg_name, value)

else:
    autocompleter_app['is_active'] = False
    CommaSeparatedUserField = BasicCommaSeparatedUserField
