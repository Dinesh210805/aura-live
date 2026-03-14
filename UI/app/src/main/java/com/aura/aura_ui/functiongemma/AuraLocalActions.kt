package com.aura.aura_ui.functiongemma

/**
 * Routing decision for how a recognized action should be handled.
 */
enum class ActionRouting {
    /** Fully handled on-device, no backend round-trip needed. */
    LOCAL_ONLY,
    /** Action executed locally but backend needs context for follow-up interaction. */
    HYBRID,
    /** Not recognized by Function Gemma — pass entirely to backend. */
    BACKEND_ONLY,
}

/**
 * Recognized action from Function Gemma with routing metadata.
 */
sealed class AuraAction(
    val name: String,
    val routing: ActionRouting,
    val parameters: Map<String, String> = emptyMap(),
) {
    // ─── LOCAL-ONLY actions (fully handled on-device) ───

    class FlashlightOn : AuraAction("flashlight_on", ActionRouting.LOCAL_ONLY)
    class FlashlightOff : AuraAction("flashlight_off", ActionRouting.LOCAL_ONLY)

    class VolumeUp : AuraAction("volume_up", ActionRouting.LOCAL_ONLY)
    class VolumeDown : AuraAction("volume_down", ActionRouting.LOCAL_ONLY)
    class VolumeMute : AuraAction("volume_mute", ActionRouting.LOCAL_ONLY)

    class BrightnessUp : AuraAction("brightness_up", ActionRouting.LOCAL_ONLY)
    class BrightnessDown : AuraAction("brightness_down", ActionRouting.LOCAL_ONLY)

    class DndOn : AuraAction("dnd_on", ActionRouting.LOCAL_ONLY)
    class DndOff : AuraAction("dnd_off", ActionRouting.LOCAL_ONLY)

    class AutoRotateOn : AuraAction("auto_rotate_on", ActionRouting.LOCAL_ONLY)
    class AutoRotateOff : AuraAction("auto_rotate_off", ActionRouting.LOCAL_ONLY)

    class OpenWifiSettings : AuraAction("open_wifi_settings", ActionRouting.LOCAL_ONLY)
    class OpenBluetoothSettings : AuraAction("open_bluetooth_settings", ActionRouting.LOCAL_ONLY)

    class OpenApp(val appName: String) : AuraAction(
        "open_app", ActionRouting.LOCAL_ONLY,
        mapOf("app_name" to appName),
    )

    class ShowLocationOnMap(val location: String) : AuraAction(
        "show_location_on_map", ActionRouting.LOCAL_ONLY,
        mapOf("location" to location),
    )

    // ─── HYBRID actions (executed locally, backend handles follow-up) ───

    class SendEmail(val to: String, val subject: String, val body: String) : AuraAction(
        "send_email", ActionRouting.HYBRID,
        mapOf("to" to to, "subject" to subject, "body" to body),
    )

    class CreateContact(
        val firstName: String,
        val lastName: String,
        val phoneNumber: String,
        val email: String,
    ) : AuraAction(
        "create_contact", ActionRouting.HYBRID,
        mapOf(
            "first_name" to firstName,
            "last_name" to lastName,
            "phone_number" to phoneNumber,
            "email" to email,
        ),
    )

    class CreateCalendarEvent(val datetime: String, val title: String) : AuraAction(
        "create_calendar_event", ActionRouting.HYBRID,
        mapOf("datetime" to datetime, "title" to title),
    )

    class SetAlarm(val time: String, val label: String) : AuraAction(
        "set_alarm", ActionRouting.HYBRID,
        mapOf("time" to time, "label" to label),
    )

    class SetTimer(val durationSeconds: String) : AuraAction(
        "set_timer", ActionRouting.HYBRID,
        mapOf("duration_seconds" to durationSeconds),
    )

    // ─── COMPOUND actions (partial local, rest to backend with context) ───

    class OpenAppAndContinue(val appName: String, val remainingTask: String) : AuraAction(
        "open_app_and_continue", ActionRouting.HYBRID,
        mapOf("app_name" to appName, "remaining_task" to remainingTask),
    )
}
