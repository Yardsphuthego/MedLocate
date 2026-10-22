import csv
from datetime import timedelta
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from apps.accounts.access import CLINICAL_ROLES, DISPENSE_ROLES, INVENTORY_ROLES, memberships
from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.facilities.models import Facility
from apps.inventory.models import InventoryItem, InventoryAdjustment
from apps.medicines.models import Medicine
from apps.prescriptions.models import Prescription, DispenseEvent

LABELS = {'stock': 'Stock and expiry', 'activity': 'Inventory activity', 'prescriptions': 'Issued prescriptions',
          'dispensing': 'Dispensing history', 'verification': 'Verification history'}


class ReportFilters(forms.Form):
    report = forms.ChoiceField()
    facility = forms.ModelChoiceField(queryset=Facility.objects.none(), required=False)
    medicine = forms.ModelChoiceField(queryset=Medicine.objects.order_by('name'), required=False)
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Start date must be on or before end date.')
        return data


def _dates(queryset, field, data):
    if data.get('start'):
        queryset = queryset.filter(**{f'{field}__date__gte': data['start']})
    if data.get('end'):
        queryset = queryset.filter(**{f'{field}__date__lte': data['end']})
    return queryset


@login_required
def staff_reports(request):
    user = request.user
    role = user.primary_role
    if user.is_superuser or role == User.Role.PLATFORM_ADMIN:
        facilities = Facility.objects.all()
        allowed = ['stock', 'activity']
    else:
        facilities = Facility.objects.filter(pk__in=memberships(user, CLINICAL_ROLES).values('facility_id'))
        allowed = []
        if role == User.Role.DOCTOR:
            allowed.append('prescriptions')
        if role in DISPENSE_ROLES:
            allowed.extend(['dispensing', 'verification'])
        if role in INVENTORY_ROLES:
            allowed.extend(['stock', 'activity'])
    if not allowed:
        raise PermissionDenied
    data = request.GET.copy()
    if not data.get('report'):
        data['report'] = allowed[0]
    form = ReportFilters(data)
    form.fields['report'].choices = [(key, LABELS[key]) for key in allowed]
    form.fields['facility'].queryset = facilities.order_by('name')
    rows, headers = [], []
    if form.is_valid():
        filters = form.cleaned_data
        kind = filters['report']
        if filters['facility']:
            facilities = facilities.filter(pk=filters['facility'].pk)
        medicine = filters['medicine']
        if kind == 'stock':
            headers = ['Facility', 'Medicine', 'Code', 'Batch', 'Quantity', 'Expiry', 'Stock status', 'Updated']
            qs = InventoryItem.objects.filter(facility__in=facilities).select_related('facility', 'medicine')
            if medicine:
                qs = qs.filter(medicine=medicine)
            for item in _dates(qs, 'updated_at', filters):
                status = 'Expired' if item.is_expired else 'Out of stock' if item.quantity == 0 else 'Low stock' if item.quantity <= item.low_stock_threshold else 'Available'
                if not item.is_expired and item.expiry_date and item.expiry_date <= timezone.localdate() + timedelta(days=30):
                    status += ' · Expiring soon'
                rows.append([item.facility.name, str(item.medicine), item.medicine.code, item.batch_number, item.quantity, item.expiry_date or 'Not recorded', status, timezone.localtime(item.updated_at).strftime('%d %b %Y %H:%M')])
        elif kind == 'activity':
            headers = ['Facility', 'Medicine', 'Previous quantity', 'New quantity', 'Updated']
            qs = InventoryAdjustment.objects.filter(item__facility__in=facilities).select_related('item__facility', 'item__medicine').order_by('-created_at')
            if medicine:
                qs = qs.filter(item__medicine=medicine)
            rows = [[r.item.facility.name, str(r.item.medicine), r.previous_quantity, r.new_quantity, timezone.localtime(r.created_at).strftime('%d %b %Y %H:%M')] for r in _dates(qs, 'created_at', filters)]
        elif kind == 'prescriptions':
            headers = ['Prescription reference', 'Issued', 'Valid until', 'Status', 'Prescribed units', 'Dispensed units']
            qs = Prescription.objects.filter(prescriber=user).prefetch_related('items')
            if filters['facility']:
                qs = qs.filter(issuing_facility=filters['facility'])
            if medicine:
                qs = qs.filter(items__medicine=medicine).distinct()
            for rx in _dates(qs, 'issued_at', filters):
                items = list(rx.items.all())
                rows.append([str(rx.uuid), timezone.localtime(rx.issued_at).strftime('%d %b %Y %H:%M'), timezone.localtime(rx.valid_until).strftime('%d %b %Y %H:%M'), rx.status_label, sum(i.prescribed_quantity for i in items), sum(i.dispensed_quantity for i in items)])
        elif kind == 'dispensing':
            headers = ['Facility', 'Prescription reference', 'Medicine', 'Quantity dispensed', 'Status', 'Valid until', 'Dispensed at']
            qs = DispenseEvent.objects.filter(facility__in=facilities).select_related('facility', 'item__medicine', 'item__prescription').order_by('-timestamp')
            if medicine:
                qs = qs.filter(item__medicine=medicine)
            rows = [[e.facility.name, str(e.item.prescription.uuid), str(e.item.medicine), e.quantity, e.item.prescription.status_label, timezone.localtime(e.item.prescription.valid_until).strftime('%d %b %Y %H:%M'), timezone.localtime(e.timestamp).strftime('%d %b %Y %H:%M')] for e in _dates(qs, 'timestamp', filters)]
        else:
            headers = ['Facility', 'Prescription record', 'Outcome', 'Current status', 'Valid until', 'Verified at']
            qs = AuditEvent.objects.filter(facility__in=facilities, action__in=['prescription.verified', 'dispensing.rejected', 'verification.rejected']).select_related('facility')
            if medicine:
                ids = [str(pk) for pk in Prescription.objects.filter(items__medicine=medicine).values_list('pk', flat=True)]
                qs = qs.filter(object_id__in=ids)
            events = list(_dates(qs, 'timestamp', filters))
            records = {str(rx.pk): rx for rx in Prescription.objects.filter(pk__in=[int(e.object_id) for e in events if e.object_id.isdecimal()])}
            for event in events:
                rx = records.get(event.object_id)
                outcome = {'prescription.verified': 'Verified', 'dispensing.rejected': 'Dispensing rejected', 'verification.rejected': 'Verification rejected'}[event.action]
                rows.append([event.facility.name, str(rx.uuid) if rx else 'Unknown reference', outcome,
                             rx.status_label if rx else 'Unknown', timezone.localtime(rx.valid_until).strftime('%d %b %Y %H:%M') if rx else '—',
                             timezone.localtime(event.timestamp).strftime('%d %b %Y %H:%M')])
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="medlocate-{kind}.csv"'
            writer = csv.writer(response)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(["'" + str(value) if str(value).lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value for value in row])
            return response
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    params.pop('export', None)
    return render(request, 'dashboard/reports.html', {
        'form': form, 'headers': headers, 'page': page,
        'params': params.urlencode(), 'row_count': len(rows),
        'workspace_name': 'History & reports', 'reports_page': True,
        'dashboard_role': 'Platform administrator' if user.is_superuser else user.get_primary_role_display(),
    })
