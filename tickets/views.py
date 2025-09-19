from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import HttpResponse
from .models import Ticket, Category, Client, Organization, TicketStatus, TicketComment, TicketTemplate, TicketAudit, TicketAttachment
from .forms import TicketForm, TicketCommentForm, ClientForm, TicketAttachmentForm


@login_required
def dashboard(request):
    """Главная страница с дашбордом"""
    # Статистика
    total_tickets = Ticket.objects.count()
    open_tickets = Ticket.objects.filter(status__is_final=False).count()
    my_tickets = Ticket.objects.filter(assigned_to=request.user, status__is_final=False).count()
    overdue_tickets = Ticket.objects.filter(
        status__is_final=False,
        created_at__lt=timezone.now() - timezone.timedelta(hours=24)
    ).count()
    
    # Последние обращения
    recent_tickets = Ticket.objects.select_related(
        'client', 'category', 'status', 'assigned_to'
    ).order_by('-created_at')[:10]
    
    # Обращения по статусам
    status_stats = TicketStatus.objects.annotate(
        ticket_count=Count('ticket')
    ).exclude(name='Закрыто').order_by('order')
    
    # Обращения по категориям
    category_stats = Category.objects.annotate(
        ticket_count=Count('ticket')
    ).filter(ticket_count__gt=0).order_by('-ticket_count')[:10]
    
    context = {
        'total_tickets': total_tickets,
        'open_tickets': open_tickets,
        'my_tickets': my_tickets,
        'overdue_tickets': overdue_tickets,
        'recent_tickets': recent_tickets,
        'status_stats': status_stats,
        'category_stats': category_stats,
    }
    
    return render(request, 'tickets/dashboard.html', context)


@login_required
def ticket_list(request):
    """Список обращений с фильтрацией"""
    tickets = Ticket.objects.select_related(
        'client', 'category', 'status', 'assigned_to'
    ).order_by('-created_at')
    
    # Фильтры
    status_filter = request.GET.get('status')
    # Поддержка нового autocomplete: приходят category_id и текст category
    category_filter = request.GET.get('category_id') or request.GET.get('category')
    if category_filter in (None, '', 'None', 'null', 'NULL'):
        category_filter = None
    assigned_filter = request.GET.get('assigned')
    priority_filter = request.GET.get('priority')
    search_query = request.GET.get('search')
    
    if status_filter:
        tickets = tickets.filter(status_id=status_filter)
    
    if category_filter:
        try:
            tickets = tickets.filter(category_id=int(category_filter))
        except (TypeError, ValueError):
            pass
    
    if assigned_filter == 'me':
        tickets = tickets.filter(assigned_to=request.user)
    elif assigned_filter == 'unassigned':
        tickets = tickets.filter(assigned_to__isnull=True)
    
    if priority_filter:
        tickets = tickets.filter(priority=priority_filter)
    
    if search_query:
        tickets = tickets.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(client__name__icontains=search_query) |
            Q(tags__icontains=search_query)
        )
    
    # Пагинация
    paginator = Paginator(tickets, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Данные для фильтров (категории больше не нужны для select)
    statuses = TicketStatus.objects.exclude(name='Закрыто').order_by('order')
    
    context = {
        'page_obj': page_obj,
        # 'categories': categories,  # не требуется из-за autocomplete
        'statuses': statuses,
        'current_filters': {
            'status': status_filter,
            'category': category_filter,
            'assigned': assigned_filter,
            'priority': priority_filter,
            'search': search_query,
        }
    }
    
    return render(request, 'tickets/ticket_list.html', context)


@login_required
def ticket_detail(request, ticket_id):
    """Детальная страница обращения"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    comments = ticket.comments.select_related('author').order_by('created_at')
    attachments = ticket.attachments.select_related('uploaded_by').order_by('-uploaded_at')
    
    if request.method == 'POST':
        # Проверяем, какой тип формы отправлен
        if 'comment' in request.POST:
            form = TicketCommentForm(request.POST)
            if form.is_valid():
                comment = form.save(commit=False)
                comment.ticket = ticket
                comment.author = request.user
                comment.save()
                
                # Создаем запись аудита
                TicketAudit.objects.create(
                    ticket=ticket,
                    action='comment_added',
                    user=request.user,
                    comment=f'Добавлен комментарий: {comment.content[:50]}...'
                )
                
                messages.success(request, 'Комментарий добавлен')
                return redirect('tickets:ticket_detail', ticket_id=ticket.id)
        elif 'attachment' in request.FILES:
            form = TicketAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                files = request.FILES.getlist('file')
                uploaded_count = 0
                
                for file in files:
                    attachment = TicketAttachment(
                        ticket=ticket,
                        file=file,
                        filename=file.name,
                        file_size=file.size,
                        uploaded_by=request.user
                    )
                    attachment.save()
                    uploaded_count += 1
                
                # Создаем запись аудита
                TicketAudit.objects.create(
                    ticket=ticket,
                    action='updated',
                    user=request.user,
                    comment=f'Загружено {uploaded_count} файлов'
                )
                
                messages.success(request, f'Загружено {uploaded_count} файлов')
                return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    else:
        comment_form = TicketCommentForm()
        attachment_form = TicketAttachmentForm()
    
    context = {
        'ticket': ticket,
        'comments': comments,
        'attachments': attachments,
        'comment_form': comment_form,
        'attachment_form': attachment_form,
    }
    
    return render(request, 'tickets/ticket_detail.html', context)


@login_required
def ticket_create(request):
    """Создание нового обращения"""
    if request.method == 'POST':
        form = TicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.created_by = request.user
            
            # Обрабатываем autocomplete поля
            category_id = request.POST.get('category_id')
            client_id = request.POST.get('client_id')
            assigned_to_text = (request.POST.get('assigned_to') or '').strip()
            assigned_to_id_raw = (request.POST.get('assigned_to_id') or '').strip()
            
            if category_id:
                try:
                    ticket.category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    pass
            
            if client_id:
                try:
                    ticket.client = Client.objects.get(id=client_id)
                except Client.DoesNotExist:
                    pass
            
            if not assigned_to_text:
                ticket.assigned_to = None
            elif assigned_to_id_raw.isdigit():
                try:
                    ticket.assigned_to = User.objects.get(id=int(assigned_to_id_raw))
                except User.DoesNotExist:
                    ticket.assigned_to = None
            else:
                # Если hidden assigned_to_id отсутствует (пользователь очистил поле) — снимаем исполнителя
                ticket.assigned_to = None
            
            ticket.save()
            
            # Обрабатываем вложения
            files = request.FILES.getlist('attachments')
            uploaded_count = 0
            
            for file in files:
                attachment = TicketAttachment(
                    ticket=ticket,
                    file=file,
                    filename=file.name,
                    file_size=file.size,
                    uploaded_by=request.user
                )
                attachment.save()
                uploaded_count += 1
            
            # Создаем запись аудита
            audit_comment = 'Обращение создано'
            if uploaded_count > 0:
                audit_comment += f' с {uploaded_count} вложениями'
            
            TicketAudit.objects.create(
                ticket=ticket,
                action='created',
                user=request.user,
                comment=audit_comment
            )
            
            messages.success(request, f'Обращение #{ticket.id} создано')
            return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    else:
        form = TicketForm()
        # Предзаполнение исполнителя текущим пользователем в UI (без фиксации на сервере)
        # Текстовое значение — имя/логин, скрытый id будет создан JS при первом выборе из списка,
        # поэтому сервер учтёт очистку/замену корректно.
        form.fields['assigned_to'].initial = request.user.get_full_name() or request.user.username
    
    context = {
        'form': form,
        'categories_for_sla': Category.objects.filter(is_active=True).order_by('sla_hours', 'name')[:6],
    }
    
    return render(request, 'tickets/ticket_form.html', context)


@login_required
def ticket_edit(request, ticket_id):
    """Редактирование обращения"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    if request.method == 'POST':
        form = TicketForm(request.POST, instance=ticket)
        if form.is_valid():
            old_status = ticket.status
            old_assigned = ticket.assigned_to
            
            ticket = form.save(commit=False)
            
            # Обрабатываем autocomplete поля
            category_id = request.POST.get('category_id')
            client_id = request.POST.get('client_id')
            assigned_to_text = (request.POST.get('assigned_to') or '').strip()
            assigned_to_id_raw = (request.POST.get('assigned_to_id') or '').strip()
            
            if category_id:
                try:
                    ticket.category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    pass
            
            if client_id:
                try:
                    ticket.client = Client.objects.get(id=client_id)
                except Client.DoesNotExist:
                    pass
            
            if not assigned_to_text:
                ticket.assigned_to = None
            elif assigned_to_id_raw.isdigit():
                try:
                    ticket.assigned_to = User.objects.get(id=int(assigned_to_id_raw))
                except User.DoesNotExist:
                    ticket.assigned_to = None
            else:
                ticket.assigned_to = None
            
            ticket.save()
            
            # Создаем записи аудита для изменений
            if old_status != ticket.status:
                TicketAudit.objects.create(
                    ticket=ticket,
                    action='status_changed',
                    user=request.user,
                    old_value=old_status.name,
                    new_value=ticket.status.name,
                    comment='Статус изменен'
                )
            
            if old_assigned != ticket.assigned_to:
                TicketAudit.objects.create(
                    ticket=ticket,
                    action='assigned',
                    user=request.user,
                    old_value=old_assigned.username if old_assigned else 'Не назначен',
                    new_value=ticket.assigned_to.username if ticket.assigned_to else 'Не назначен',
                    comment='Исполнитель изменен'
                )
            
            messages.success(request, f'Обращение #{ticket.id} обновлено')
            return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    else:
        form = TicketForm(instance=ticket)
        # Предзаполняем текстовые поля и скрытые id значения
        if ticket.category:
            form.fields['category'].initial = str(ticket.category)
        if ticket.client:
            form.fields['client'].initial = ticket.client.name
        if ticket.assigned_to:
            form.fields['assigned_to'].initial = ticket.assigned_to.get_full_name() or ticket.assigned_to.username
    
    context = {
        'form': form,
        'ticket': ticket,
        'categories_for_sla': Category.objects.filter(is_active=True).order_by('sla_hours', 'name')[:6],
    }
    
    return render(request, 'tickets/ticket_form.html', context)


@login_required
def take_ticket(request, ticket_id):
    """Взять обращение в работу"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    if ticket.assigned_to and ticket.assigned_to != request.user:
        messages.error(request, 'Обращение уже назначено другому исполнителю')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    
    # Находим статус "В работе"
    working_status = TicketStatus.objects.filter(is_working=True).first()
    if not working_status:
        messages.error(request, 'Статус "В работе" не найден')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    
    ticket.assigned_to = request.user
    ticket.status = working_status
    ticket.taken_at = timezone.now()
    ticket.save()
    
    # Создаем запись аудита
    TicketAudit.objects.create(
        ticket=ticket,
        action='taken',
        user=request.user,
        comment='Взято в работу'
    )
    
    messages.success(request, f'Обращение #{ticket.id} взято в работу')
    return redirect('tickets:ticket_detail', ticket_id=ticket.id)


@login_required
def resolve_ticket(request, ticket_id):
    """Решить обращение"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    if request.method == 'POST':
        resolution = request.POST.get('resolution', '')
        resolution_notes = request.POST.get('resolution_notes', '')
        
        # Находим статус "Решено"
        resolved_status = TicketStatus.objects.filter(name='Решено').first()
        if not resolved_status:
            messages.error(request, 'Статус "Решено" не найден')
            return redirect('tickets:ticket_detail', ticket_id=ticket.id)
        
        ticket.status = resolved_status
        ticket.resolution = resolution
        ticket.resolution_notes = resolution_notes
        ticket.resolved_at = timezone.now()
        ticket.save()
        
        # Создаем запись аудита
        TicketAudit.objects.create(
            ticket=ticket,
            action='resolved',
            user=request.user,
            comment=f'Решено: {resolution[:50]}...' if resolution else 'Решено'
        )
        
        messages.success(request, f'Обращение #{ticket.id} решено')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    
    # Показываем форму решения
    templates = TicketTemplate.objects.filter(
        category=ticket.category,
        is_active=True
    )
    
    context = {
        'ticket': ticket,
        'templates': templates,
    }
    
    return render(request, 'tickets/ticket_resolve.html', context)


@login_required
def close_ticket(request, ticket_id):
    """Закрыть обращение (подтверждено заявителем) → считаем как Решено"""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    # Находим статус "Решено" (единственный финальный)
    resolved_status = TicketStatus.objects.filter(name='Решено').first()
    if not resolved_status:
        resolved_status = TicketStatus.objects.filter(is_final=True).first()
    if not resolved_status:
        messages.error(request, 'Финальный статус "Решено" не найден')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    
    # Обновляем обращение
    ticket.status = resolved_status
    if not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
    ticket.save()
    
    # Аудит
    TicketAudit.objects.create(
        ticket=ticket,
        action='resolved',
        user=request.user,
        comment='Обращение подтверждено заявителем (Решено)'
    )
    
    messages.success(request, f'Обращение #{ticket.id} решено')
    return redirect('tickets:ticket_detail', ticket_id=ticket.id)


@login_required
def set_waiting(request, ticket_id):
    """Перевести статус в "Ожидает ответа". Разрешено только из статусов с is_working=True и если уже не в этом статусе."""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    if not ticket.status.is_working:
        messages.error(request, 'Перевод возможен только из статуса "В работе"')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    waiting_status = TicketStatus.objects.filter(name='Ожидает ответа').first()
    if not waiting_status:
        messages.error(request, 'Статус "Ожидает ответа" не найден')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    if ticket.status == waiting_status:
        messages.info(request, 'Статус уже "Ожидает ответа"')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    old_status = ticket.status
    ticket.status = waiting_status
    ticket.save()
    TicketAudit.objects.create(
        ticket=ticket,
        action='status_changed',
        user=request.user,
        old_value=old_status.name,
        new_value=waiting_status.name,
        comment='Переведено в статус Ожидает ответа'
    )
    messages.success(request, f'Обращение #{ticket.id} переведено в статус "Ожидает ответа"')
    return redirect('tickets:ticket_detail', ticket_id=ticket.id)


@login_required
def return_to_work(request, ticket_id):
    """Вернуть из "Ожидает ответа" в рабочий статус."""
    ticket = get_object_or_404(Ticket, id=ticket_id)
    if ticket.status and ticket.status.name != 'Ожидает ответа':
        messages.error(request, 'Возврат возможен только из статуса "Ожидает ответа"')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    working_status = TicketStatus.objects.filter(is_working=True).exclude(name='Ожидает ответа').first()
    if not working_status:
        messages.error(request, 'Рабочий статус не найден')
        return redirect('tickets:ticket_detail', ticket_id=ticket.id)
    old_status = ticket.status
    ticket.status = working_status
    # taken_at оставляем как есть; исполнитель не меняется
    ticket.save()
    TicketAudit.objects.create(
        ticket=ticket,
        action='status_changed',
        user=request.user,
        old_value=old_status.name if old_status else '',
        new_value=working_status.name,
        comment='Возвращено в работу из статуса Ожидает ответа'
    )
    messages.success(request, f'Обращение #{ticket.id} возвращено в работу')
    return redirect('tickets:ticket_detail', ticket_id=ticket.id)

@login_required
def client_list(request):
    """Список клиентов"""
    clients = Client.objects.filter(is_active=True).annotate(
        ticket_count=Count('ticket')
    ).order_by('name')
    
    search_query = request.GET.get('search')
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) |
            Q(contact_person__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(organization__name__icontains=search_query)
        )
    
    paginator = Paginator(clients, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    
    return render(request, 'tickets/client_list.html', context)


@login_required
def client_detail(request, client_id):
    """Детальная страница клиента"""
    client = get_object_or_404(Client, id=client_id)
    tickets = client.ticket_set.select_related(
        'category', 'status', 'assigned_to'
    ).order_by('-created_at')
    # Статистика
    total_tickets = tickets.count()
    open_tickets = tickets.filter(status__is_final=False).count()
    
    context = {
        'client': client,
        'tickets': tickets,
        'total_tickets': total_tickets,
        'open_tickets': open_tickets,
    }
    
    return render(request, 'tickets/client_detail.html', context)


@login_required
def client_create(request):
    """Создание нового клиента"""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            # Обработка autocomplete Organization
            org_id = (request.POST.get('organization_id') or '').strip()
            org_name_text = (request.POST.get('organization') or '').strip()
            if org_id.isdigit():
                client.organization = Organization.objects.filter(id=int(org_id)).first()
            elif org_name_text:
                # Если ввели текст без выбора — создадим/привяжем организацию по имени
                client.organization, _ = Organization.objects.get_or_create(name=org_name_text)
            client.save()
            messages.success(request, f'Клиент "{client.name}" создан')
            return redirect('tickets:client_detail', client_id=client.id)
    else:
        form = ClientForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'tickets/client_form.html', context)


@login_required
def client_edit(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            client = form.save(commit=False)
            org_id = (request.POST.get('organization_id') or '').strip()
            org_name_text = (request.POST.get('organization') or '').strip()
            if org_id.isdigit():
                client.organization = Organization.objects.filter(id=int(org_id)).first()
            elif org_name_text:
                client.organization, _ = Organization.objects.get_or_create(name=org_name_text)
            else:
                client.organization = None
            client.save()
            messages.success(request, f'Клиент "{client.name}" обновлён')
            return redirect('tickets:client_detail', client_id=client.id)
    else:
        form = ClientForm(instance=client)
        if client.organization:
            form.fields['organization'].initial = client.organization.name
    return render(request, 'tickets/client_form.html', {'form': form, 'client': client})


@login_required
def get_template_content(request, template_id):
    """AJAX запрос для получения содержимого шаблона"""
    template = get_object_or_404(TicketTemplate, id=template_id)
    
    return JsonResponse({
        'title': template.title_template,
        'content': template.content_template
    })


@login_required
def autocomplete_categories(request):
    """AJAX autocomplete для категорий"""
    query = request.GET.get('q', '')
    base_qs = Category.objects.filter(is_active=True)
    if len(query) >= 1:
        base_qs = base_qs.filter(Q(name__icontains=query) | Q(description__icontains=query))
    categories = base_qs.order_by('parent__name', 'name')[:10]
    
    results = []
    for category in categories:
        results.append({
            'id': category.id,
            'text': str(category),
            'parent': category.parent.name if category.parent else None
        })
    
    return JsonResponse({'results': results})


@login_required
def autocomplete_clients(request):
    """AJAX autocomplete для клиентов"""
    query = request.GET.get('q', '')
    base_qs = Client.objects.filter(is_active=True)
    if len(query) >= 1:
        base_qs = base_qs.filter(
            Q(name__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query) |
            Q(organization__name__icontains=query)
        )
    clients = base_qs.select_related('organization').order_by('name')[:10]
    
    results = []
    for client in clients:
        display = client.name
        if client.organization:
            display = f"{client.organization.name} — {client.name}"
        results.append({
            'id': client.id,
            'text': display,
            'contact_person': client.contact_person,
            'phone': client.phone,
            'email': client.email
        })
    
    return JsonResponse({'results': results})


@login_required
def autocomplete_organizations(request):
    """AJAX autocomplete для организаций"""
    query = request.GET.get('q', '')
    base_qs = Organization.objects.all()
    if len(query) >= 1:
        base_qs = base_qs.filter(name__icontains=query)
    orgs = base_qs.order_by('name')[:10]
    results = [{'id': o.id, 'text': o.name} for o in orgs]
    return JsonResponse({'results': results})


@login_required
def create_organization(request):
    """Создание организации (AJAX). Принимает name, возвращает {id, name}."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Введите название организации'}, status=400)
    org, created = Organization.objects.get_or_create(name=name)
    return JsonResponse({'id': org.id, 'name': org.name, 'created': created})


@login_required
def autocomplete_users(request):
    """AJAX autocomplete для пользователей"""
    query = request.GET.get('q', '')
    base_qs = User.objects.filter(is_active=True)
    if len(query) >= 1:
        base_qs = base_qs.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )
    users = base_qs.order_by('username')[:10]
    
    results = []
    for user in users:
        full_name = user.get_full_name()
        display_name = full_name if full_name else user.username
        results.append({
            'id': user.id,
            'text': display_name,
            'username': user.username,
            'email': user.email
        })
    
    return JsonResponse({'results': results})


@login_required
def delete_attachment(request, attachment_id):
    """Удаление вложения"""
    attachment = get_object_or_404(TicketAttachment, id=attachment_id)
    ticket_id = attachment.ticket.id
    
    # Проверяем права доступа
    if attachment.uploaded_by != request.user and not request.user.is_staff:
        messages.error(request, 'У вас нет прав для удаления этого файла')
        return redirect('tickets:ticket_detail', ticket_id=ticket_id)
    
    # Создаем запись аудита
    TicketAudit.objects.create(
        ticket=attachment.ticket,
        action='updated',
        user=request.user,
        comment=f'Удален файл: {attachment.filename}'
    )
    
    attachment.delete()
    messages.success(request, f'Файл "{attachment.filename}" удален')
    return redirect('tickets:ticket_detail', ticket_id=ticket_id)


@login_required
def queue_view(request):
    """Очередь дел"""
    # Не назначенные обращения
    unassigned_tickets = Ticket.objects.filter(
        assigned_to__isnull=True,
        status__is_final=False
    ).select_related('client', 'category', 'status').order_by('created_at')
    
    # Мои обращения
    my_tickets = Ticket.objects.filter(
        assigned_to=request.user,
        status__is_final=False
    ).select_related('client', 'category', 'status').order_by('created_at')
    
    # Просроченные обращения
    overdue_tickets = Ticket.objects.filter(
        status__is_final=False,
        created_at__lt=timezone.now() - timezone.timedelta(hours=24)
    ).select_related('client', 'category', 'status', 'assigned_to').order_by('created_at')
    
    context = {
        'unassigned_tickets': unassigned_tickets,
        'my_tickets': my_tickets,
        'overdue_tickets': overdue_tickets,
    }
    
    return render(request, 'tickets/queue.html', context)


@login_required
def analytics(request):
    """Страница аналитики обращений"""
    # Утилита для извлечения первого ненулевого значения параметра (учитывая дубли)
    def first_non_empty(param_name):
        values = request.GET.getlist(param_name)
        for v in values:
            if v not in (None, '', 'None', 'null', 'NULL'):
                return v
        return None

    # Фильтры
    category_id = first_non_empty('category_id')
    category_text = first_non_empty('category')
    client_id = first_non_empty('client_id') or first_non_empty('client')
    assigned_to_id = first_non_empty('assigned_to_id') or first_non_empty('assigned_to')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    chart_type = request.GET.get('chart_type', 'tags')  # tags или organizations

    # Даты по умолчанию: текущий месяц
    from django.utils import timezone as dj_tz
    today = dj_tz.localdate()
    if not date_from:
        first_day = today.replace(day=1)
        date_from = first_day.isoformat()
    if not date_to:
        date_to = today.isoformat()

    tickets_qs = Ticket.objects.select_related('category', 'client', 'client__organization', 'status', 'assigned_to').all()

    if category_id and str(category_id).isdigit():
        cid = int(category_id)
        tickets_qs = tickets_qs.filter(Q(category_id=cid) | Q(category__parent_id=cid))
    elif category_text:
        tickets_qs = tickets_qs.filter(
            Q(category__name__icontains=category_text) |
            Q(category__parent__name__icontains=category_text)
        )
    if client_id and str(client_id).isdigit():
        tickets_qs = tickets_qs.filter(client_id=int(client_id))
    if assigned_to_id and str(assigned_to_id).isdigit():
        tickets_qs = tickets_qs.filter(assigned_to_id=int(assigned_to_id))
    if date_from:
        tickets_qs = tickets_qs.filter(created_at__date__gte=date_from)
    if date_to:
        tickets_qs = tickets_qs.filter(created_at__date__lte=date_to)

    # Агрегации (без extra, чтобы избежать конфликтов алиасов)
    by_day = (
        tickets_qs
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .order_by('day')
        .annotate(cnt=Count('id'))
    )
    # Подсчет тегов или организаций в зависимости от chart_type
    if chart_type == 'organizations':
        from collections import Counter
        org_counter = Counter()
        for ticket in tickets_qs.select_related('client__organization'):
            if ticket.client and ticket.client.organization:
                org_counter[ticket.client.organization.name] += 1
        top_orgs = sorted(org_counter.items(), key=lambda x: x[1], reverse=True)[:20]
        chart_data = [{'name': k, 'count': v} for k, v in top_orgs]
    else:  # tags
        by_tags = []
        # Разбор тегов по запятым
        for t in tickets_qs.exclude(tags="").values_list('tags', flat=True):
            for tag in [x.strip() for x in t.split(',') if x.strip()]:
                by_tags.append(tag)
        from collections import Counter
        tags_counter = Counter(by_tags)
        top_tags = sorted(tags_counter.items(), key=lambda x: x[1], reverse=True)[:20]
        chart_data = [{'name': k, 'count': v} for k, v in top_tags]

    # Сериализация для фронта
    by_day_list = list(by_day)
    by_day_serialized = [
        {'day': (item['day'].isoformat() if item['day'] else None), 'cnt': item['cnt']}
        for item in by_day_list
    ]
    import json
    chart_by_day_json = json.dumps(by_day_serialized)
    chart_data_json = json.dumps(chart_data)

    # Краткая сводка для подписи под графиком
    total_count = tickets_qs.count()
    day_count = len(by_day_list)
    avg_per_day = round(total_count / day_count, 1) if day_count else 0

    # Пагинация списка
    paginator = Paginator(tickets_qs.order_by('-created_at'), 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Тексты выбранных значений для автозаполнения
    category_name = None
    client_name = None
    assigned_to_name = None
    if category_id and str(category_id).isdigit():
        c = Category.objects.filter(id=int(category_id)).first()
        if c:
            category_name = str(c)
    if client_id and str(client_id).isdigit():
        cl = Client.objects.filter(id=int(client_id)).first()
        if cl:
            client_name = cl.name
    if assigned_to_id and str(assigned_to_id).isdigit():
        u = User.objects.filter(id=int(assigned_to_id)).first()
        if u:
            assigned_to_name = u.get_full_name() or u.username

    context = {
        'page_obj': page_obj,
        'filters': {
            'category_id': category_id or '',
            'category_name': category_name or category_text or '',
            'client_id': client_id or '',
            'client_name': client_name or '',
            'assigned_to_id': assigned_to_id or '',
            'assigned_to_name': assigned_to_name or '',
            'date_from': date_from or '',
            'date_to': date_to or '',
        },
        'chart_by_day_json': chart_by_day_json,
        'chart_data_json': chart_data_json,
        'chart_type': chart_type,
        'analytics_summary': {
            'total_count': total_count,
            'day_count': day_count,
            'avg_per_day': avg_per_day,
        },
    }

    return render(request, 'tickets/analytics.html', context)


@login_required
def analytics_export_xlsx(request):
    """Экспорт выборки аналитики в XLSX по текущим фильтрам."""
    # Повторяем фильтрацию как в analytics
    def first_non_empty(param_name):
        values = request.GET.getlist(param_name)
        for v in values:
            if v not in (None, '', 'None', 'null', 'NULL'):
                return v
        return None

    category_id = first_non_empty('category_id')
    category_text = first_non_empty('category')
    client_id = first_non_empty('client_id') or first_non_empty('client')
    assigned_to_id = first_non_empty('assigned_to_id') or first_non_empty('assigned_to')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    qs = Ticket.objects.select_related('category', 'client', 'client__organization', 'status', 'assigned_to')
    if category_id and str(category_id).isdigit():
        cid = int(category_id)
        qs = qs.filter(Q(category_id=cid) | Q(category__parent_id=cid))
    elif category_text:
        qs = qs.filter(Q(category__name__icontains=category_text) | Q(category__parent__name__icontains=category_text))
    if client_id and str(client_id).isdigit():
        qs = qs.filter(client_id=int(client_id))
    if assigned_to_id and str(assigned_to_id).isdigit():
        qs = qs.filter(assigned_to_id=int(assigned_to_id))
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Формируем XLSX
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Обращения'
    headers = ['ID', 'Заголовок', 'Клиент', 'Организация', 'Категория', 'Статус', 'Исполнитель', 'Создано']
    ws.append(headers)
    for t in qs.order_by('-created_at'):
        ws.append([
            t.id,
            t.title,
            t.client.name if t.client else '',
            t.client.organization.name if t.client and t.client.organization else '',
            t.category.name if t.category else '',
            t.status.name if t.status else '',
            (t.assigned_to.get_full_name() or t.assigned_to.username) if t.assigned_to else '',
            t.created_at.strftime('%d.%m.%Y %H:%M'),
        ])

    # Автоширина
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            max_len = max(max_len, len(str(cell.value)) if cell.value else 0)
        ws.column_dimensions[col_letter].width = min(max(10, max_len + 2), 60)

    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="analytics_export.xlsx"'
    wb.save(resp)
    return resp