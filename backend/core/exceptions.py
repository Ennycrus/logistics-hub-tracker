"""
One consistent shape for every API error:

    {
        "error":   "A short message you can show to the user",
        "details": { "field_name": ["what is wrong"], ... }   (may be empty)
    }

Our services raise Django's ValidationError. DRF doesn't know that type,
so without this handler those errors would become a 500 "server error".
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    # 1. Errors raised by our services (Django's ValidationError).
    if isinstance(exc, DjangoValidationError):
        details = exc.message_dict if hasattr(exc, 'error_dict') else {}
        return Response(
            {'error': ' '.join(exc.messages), 'details': details},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Everything DRF already handles (404, 403, serializer errors...).
    response = exception_handler(exc, context)
    if response is None:
        return None  # a real bug: let Django show its error page

    data = response.data
    if isinstance(data, dict) and 'detail' in data:
        response.data = {'error': str(data['detail']), 'details': {}}
    elif isinstance(data, dict):
        first = next(iter(data.values()), '')
        message = first[0] if isinstance(first, list) and first else str(first)
        response.data = {'error': str(message), 'details': data}
    else:
        response.data = {'error': ' '.join(str(item) for item in data), 'details': {}}
    return response