from django.core.exceptions import PermissionDenied
from apps.facilities.models import FacilityMembership
from .models import User

SEARCH_ROLES = {User.Role.DOCTOR, User.Role.NURSE}
DISPENSE_ROLES = {User.Role.NURSE, User.Role.PHARMACY, User.Role.DISPENSER}
INVENTORY_ROLES = {User.Role.PHARMACY, User.Role.INVENTORY, User.Role.FACILITY_ADMIN}
CLINICAL_ROLES = SEARCH_ROLES | DISPENSE_ROLES | INVENTORY_ROLES


def require_staff(user, roles):
    if (not user.is_authenticated or not user.is_active or user.primary_role not in roles
            or not getattr(getattr(user, 'staff_profile', None), 'active', False)):
        raise PermissionDenied


def memberships(user, roles):
    require_staff(user, roles)
    return FacilityMembership.objects.select_related('facility').filter(
        user=user, role=user.primary_role, active=True, facility__status='active',
    )


def require_membership(user, roles, facility=None):
    available = memberships(user, roles)
    if facility is not None:
        available = available.filter(facility=facility)
    membership = available.order_by('facility__name', 'pk').first()
    if membership is None:
        raise PermissionDenied
    return membership
