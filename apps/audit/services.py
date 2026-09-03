from .models import AuditEvent


def record_event(*, actor, action, obj=None, facility=None, metadata=None):
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label if obj else "",
        object_id=str(obj.pk) if obj else "",
        facility=facility,
        metadata=metadata or {},
    )
