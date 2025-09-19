from django import forms
from .models import Ticket, TicketComment, Client, Category, TicketStatus, TicketAttachment, Organization


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class TicketForm(forms.ModelForm):
    # Поля для автокомплита (не модельные), реальные FK ставим во вьюхе из *_id
    category = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'form-control autocomplete-field'}))
    client = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'form-control autocomplete-field'}))
    assigned_to = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control autocomplete-field'}))
    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.gif,.txt,.zip,.rar'
        }),
        help_text='Можно выбрать несколько файлов'
    )
    
    class Meta:
        model = Ticket
        fields = [
            'title', 'description', 'priority', 'status', 'tags', 'external_message_id'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'tags': forms.TextInput(attrs={'class': 'form-control'}),
            'external_message_id': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Предзаполняем статус "Новое" (ID 1) для новых обращений
        if not self.instance.pk:  # Если это новое обращение
            try:
                default_status = TicketStatus.objects.get(id=1)
                self.fields['status'].initial = default_status
            except TicketStatus.DoesNotExist:
                pass
        
        # Добавляем атрибуты для autocomplete
        self.fields['category'].widget.attrs.update({
            'data-autocomplete-url': '/tickets/api/categories/',
            'data-autocomplete-min-length': '0',
            'class': 'form-control autocomplete-field',
            'placeholder': 'Начните вводить название категории...'
        })
        
        self.fields['client'].widget.attrs.update({
            'data-autocomplete-url': '/tickets/api/clients/',
            'data-autocomplete-min-length': '0',
            'class': 'form-control autocomplete-field',
            'placeholder': 'Начните вводить название клиента...'
        })
        
        self.fields['assigned_to'].widget.attrs.update({
            'data-autocomplete-url': '/tickets/api/users/',
            'data-autocomplete-min-length': '0',
            'class': 'form-control autocomplete-field',
            'placeholder': 'Начните вводить имя исполнителя...'
        })


class TicketCommentForm(forms.ModelForm):
    # Поле для выбора клиента (только для внешних комментариев)
    author_client_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control autocomplete-field',
            'placeholder': 'Начните вводить клиента...',
            'data-autocomplete-url': '/tickets/api/clients/',
            'data-autocomplete-min-length': '0',
        })
    )
    
    class Meta:
        model = TicketComment
        fields = ['content', 'is_internal', 'author_type']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_internal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'author_type': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Предзаполняем тип автора по умолчанию
        if not self.instance.pk:
            self.fields['author_type'].initial = 'user'


class ClientForm(forms.ModelForm):
    # Отдельное текстовое поле для автокомплита организации
    organization = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control autocomplete-field',
            'placeholder': 'Начните вводить...',
            'data-autocomplete-url': '/tickets/api/organizations/',
            'data-autocomplete-min-length': '0',
        })
    )
    class Meta:
        model = Client
        fields = [
            'name', 'contact_person', 'phone', 'email', 
            'external_id', 'notes', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'external_id': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TicketAttachmentForm(forms.ModelForm):
    class Meta:
        model = TicketAttachment
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].widget.attrs.update({
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.gif,.txt,.zip,.rar',
            'multiple': True
        })


class TicketFilterForm(forms.Form):
    PRIORITY_CHOICES = [
        ('', 'Все приоритеты'),
        ('low', 'Низкий'),
        ('normal', 'Обычный'),
        ('high', 'Высокий'),
        ('urgent', 'Срочный'),
    ]
    
    ASSIGNED_CHOICES = [
        ('', 'Все исполнители'),
        ('me', 'Мои обращения'),
        ('unassigned', 'Не назначенные'),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Поиск по заголовку, описанию, клиенту...'
        })
    )
    status = forms.ModelChoiceField(
        queryset=TicketStatus.objects.all(),
        required=False,
        empty_label="Все статусы",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label="Все категории",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    priority = forms.ChoiceField(
        choices=PRIORITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    assigned = forms.ChoiceField(
        choices=ASSIGNED_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
