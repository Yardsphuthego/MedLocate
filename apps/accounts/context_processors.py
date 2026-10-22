from .access import CLINICAL_ROLES
from apps.facilities.models import FacilityMembership


def staff_facilities(request):
    user = request.user
    if not user.is_authenticated or user.primary_role not in CLINICAL_ROLES:
        return {}
    if not getattr(getattr(user, 'staff_profile', None), 'active', False):
        return {}
    available = list(FacilityMembership.objects.select_related('facility').filter(
        user=user, role=user.primary_role, active=True, facility__status='active'
    ).order_by('facility__name', 'pk'))
    chosen = request.session.get('active_facility')
    if chosen not in [m.facility_id for m in available]:
        chosen = available[0].facility_id if available else None
    return {'staff_facilities': available, 'active_facility_id': chosen}
