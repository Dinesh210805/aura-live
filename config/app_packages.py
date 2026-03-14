"""
App package name registry for open_app actions.

Keeps package names out of the system prompt, saving ~200 tokens per call.
Used by the coordinator/executor to resolve app names to package identifiers.
"""

APP_PACKAGES: dict[str, str] = {
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "spotify": "com.spotify.music",
    "apple music": "com.apple.android.music",
    "youtube": "com.google.android.youtube",
    "gmail": "com.google.android.gm",
    "chrome": "com.android.chrome",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "settings": "com.android.settings",
    "camera": "com.android.camera2",
    "messages": "com.google.android.apps.messaging",
    "phone": "com.google.android.dialer",
    "contacts": "com.google.android.contacts",
    "calendar": "com.google.android.calendar",
    "clock": "com.google.android.deskclock",
    "files": "com.google.android.documentsui",
    "play store": "com.android.vending",
    "photos": "com.google.android.apps.photos",
}


def resolve_package(app_name: str) -> str:
    """Resolve a human-readable app name to its Android package name.

    Returns the original app_name unchanged if no mapping is found,
    letting the executor attempt a fuzzy match.
    """
    return APP_PACKAGES.get(app_name.lower().strip(), app_name)
