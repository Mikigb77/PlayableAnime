"""The newest build of the app, which the app downloads and installs itself (S12, T13).

Each deploy uploads the Android APK it publishes to the private releases bucket, and the app asks
`GET /v1/app/latest` for it on start and when it comes back. See `releases.service`.
"""
