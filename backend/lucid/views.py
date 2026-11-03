from django.http import HttpRequest, JsonResponse


# Not /healthz: Cloud Run reserves some paths ending in "z". It never touches the database (T3),
# so probes don't keep the Neon compute awake or wait for it to wake up.
async def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})
