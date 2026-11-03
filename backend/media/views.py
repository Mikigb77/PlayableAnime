"""Serves picture files in local development, behind the same kind of expiring signed URL that
Cloud Storage gives in production. With `MEDIA_BUCKET` set, this view serves nothing."""

import mimetypes

from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

from lucid.errors import ApiError, ErrorCode, error_response
from media.storage import LocalStorage, get_storage, verify_local_signature


@require_GET
def local_file(request: HttpRequest, key: str) -> HttpResponse:
    storage = get_storage()
    expires = request.GET.get("expires", "")
    signature = request.GET.get("signature", "")
    if (
        settings.MEDIA_BUCKET
        or not isinstance(storage, LocalStorage)
        or not verify_local_signature(key, expires, signature)
    ):
        return error_response(ApiError(ErrorCode.NOT_FOUND))
    try:
        path = storage.path(key)
    except ValueError:
        return error_response(ApiError(ErrorCode.NOT_FOUND))
    if not path.is_file():
        return error_response(ApiError(ErrorCode.NOT_FOUND))
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = FileResponse(path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    return response
