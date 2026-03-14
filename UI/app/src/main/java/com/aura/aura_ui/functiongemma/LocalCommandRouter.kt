package com.aura.aura_ui.functiongemma

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.AlarmClock
import android.provider.CalendarContract
import android.provider.ContactsContract
import android.util.Log
import com.aura.aura_ui.accessibility.AuraAccessibilityService
import org.json.JSONObject

private const val TAG = "LocalCommandRouter"

/**
 * Result of routing a command through the local Function Gemma model.
 */
sealed class RoutingResult {
    /** Fully handled locally — do not send to backend. */
    data class Local(val action: AuraAction, val message: String) : RoutingResult()

    /** Executed locally but backend needs follow-up context. */
    data class Hybrid(val action: AuraAction, val contextForBackend: JSONObject) : RoutingResult()

    /** Not recognized locally — pass entirely to backend. */
    object Backend : RoutingResult()
}

/**
 * Routes user commands through Function Gemma and executes local actions.
 * Decides whether a command is LOCAL_ONLY, HYBRID, or BACKEND_ONLY.
 */
class LocalCommandRouter(
    private val context: Context,
    private val engine: FunctionGemmaEngine,
) {

    /**
     * Instant keyword-only routing — no model inference, no coroutine needed.
     * Used by the voice pipeline to intercept Whisper transcripts before waiting for the server LLM.
     * Returns null if the text doesn't match any quick pattern (fall through to normal path).
     */
    fun tryQuickRoute(text: String): RoutingResult? {
        val action = quickMatch(text) ?: return null
        return when (action.routing) {
            ActionRouting.LOCAL_ONLY -> executeLocal(action)
            ActionRouting.HYBRID -> executeHybrid(action, text)
            ActionRouting.BACKEND_ONLY -> RoutingResult.Backend
        }
    }

    /**
     * Process a user command: run through Function Gemma, execute if local, return routing result.
     * Keyword matching runs first (instant, no model), then falls through to Function Gemma for
     * NLU tasks requiring parameter extraction (contacts, email, location, calendar).
     */
    suspend fun route(userText: String): RoutingResult {
        // Compound/multi-step commands always go to backend for full automation
        if (isCompoundCommand(userText.lowercase())) {
            Log.i(TAG, "☁️ Compound command detected, routing to backend: ${userText.take(60)}")
            return RoutingResult.Backend
        }

        // Fast path: keyword matching — covers device controls the model wasn't fine-tuned on
        quickMatch(userText)?.let { action ->
            Log.i(TAG, "⚡ Keyword-matched: ${action.name}")
            return when (action.routing) {
                ActionRouting.LOCAL_ONLY -> executeLocal(action)
                ActionRouting.HYBRID -> executeHybrid(action, userText)
                ActionRouting.BACKEND_ONLY -> RoutingResult.Backend
            }
        }

        // Slow path: Function Gemma for NLU (flashlight, WiFi, contacts, email, location, calendar)
        if (!engine.isReady) return RoutingResult.Backend

        val action = engine.processCommand(userText) ?: return RoutingResult.Backend

        Log.i(TAG, "Recognized action: ${action.name} routing=${action.routing}")

        return when (action.routing) {
            ActionRouting.LOCAL_ONLY -> executeLocal(action)
            ActionRouting.HYBRID -> executeHybrid(action, userText)
            ActionRouting.BACKEND_ONLY -> RoutingResult.Backend
        }
    }

    private fun executeLocal(action: AuraAction): RoutingResult {
        return when (action) {
            // System toggles via AccessibilityService
            is AuraAction.FlashlightOn -> {
                executeSystemAction("flashlight_on")
                RoutingResult.Local(action, "Flashlight turned on")
            }
            is AuraAction.FlashlightOff -> {
                executeSystemAction("flashlight_off")
                RoutingResult.Local(action, "Flashlight turned off")
            }
            is AuraAction.VolumeUp -> {
                executeSystemAction("volume_up")
                RoutingResult.Local(action, "Volume increased")
            }
            is AuraAction.VolumeDown -> {
                executeSystemAction("volume_down")
                RoutingResult.Local(action, "Volume decreased")
            }
            is AuraAction.VolumeMute -> {
                executeSystemAction("mute")
                RoutingResult.Local(action, "Volume muted")
            }
            is AuraAction.BrightnessUp -> {
                executeSystemAction("brightness_up")
                RoutingResult.Local(action, "Brightness increased")
            }
            is AuraAction.BrightnessDown -> {
                executeSystemAction("brightness_down")
                RoutingResult.Local(action, "Brightness decreased")
            }
            is AuraAction.DndOn -> {
                executeSystemAction("dnd_on")
                RoutingResult.Local(action, "Do Not Disturb enabled")
            }
            is AuraAction.DndOff -> {
                executeSystemAction("dnd_off")
                RoutingResult.Local(action, "Do Not Disturb disabled")
            }
            is AuraAction.AutoRotateOn -> {
                executeSystemAction("auto_rotate_on")
                RoutingResult.Local(action, "Auto-rotate enabled")
            }
            is AuraAction.AutoRotateOff -> {
                executeSystemAction("auto_rotate_off")
                RoutingResult.Local(action, "Auto-rotate disabled")
            }
            is AuraAction.OpenWifiSettings -> {
                executeSystemAction("open_wifi_settings")
                RoutingResult.Local(action, "WiFi settings opened")
            }
            is AuraAction.OpenBluetoothSettings -> {
                executeSystemAction("open_bluetooth_settings")
                RoutingResult.Local(action, "Bluetooth settings opened")
            }
            is AuraAction.OpenApp -> {
                launchApp(action.appName)
                RoutingResult.Local(action, "Opening ${action.appName}")
            }
            is AuraAction.ShowLocationOnMap -> {
                showOnMap(action.location)
                RoutingResult.Local(action, "Showing ${action.location} on map")
            }
            // Hybrid/Backend actions should not reach here
            else -> RoutingResult.Backend
        }
    }

    private fun executeHybrid(action: AuraAction, originalText: String): RoutingResult {
        val ctx = JSONObject()
        ctx.put("original_command", originalText)
        ctx.put("action_name", action.name)
        ctx.put("action_parameters", JSONObject(action.parameters))

        when (action) {
            is AuraAction.SendEmail -> {
                launchEmailCompose(action.to, action.subject, action.body)
                ctx.put("local_status", "email_compose_opened")
                ctx.put("needs_user_action", "User must review and tap Send")
            }
            is AuraAction.CreateContact -> {
                launchCreateContact(action.firstName, action.lastName, action.phoneNumber, action.email)
                ctx.put("local_status", "contact_form_opened")
                ctx.put("needs_user_action", "User must review and tap Save")
            }
            is AuraAction.CreateCalendarEvent -> {
                launchCalendarEvent(action.datetime, action.title)
                ctx.put("local_status", "calendar_event_opened")
                ctx.put("needs_user_action", "User must review and tap Save")
            }
            is AuraAction.SetAlarm -> {
                launchSetAlarm(action.time, action.label)
                ctx.put("local_status", "alarm_set")
                ctx.put("needs_user_action", "none")
            }
            is AuraAction.SetTimer -> {
                launchSetTimer(action.durationSeconds)
                ctx.put("local_status", "timer_set")
                ctx.put("needs_user_action", "none")
            }
            is AuraAction.OpenAppAndContinue -> {
                launchApp(action.appName)
                ctx.put("local_status", "app_opened")
                ctx.put("app_already_opened", true)
                ctx.put("remaining_task", action.remainingTask)
            }
            else -> {
                ctx.put("local_status", "unknown_hybrid")
            }
        }

        return RoutingResult.Hybrid(action, ctx)
    }

    // ─── Execution helpers ───

    private fun executeSystemAction(action: String) {
        AuraAccessibilityService.instance?.executeSystemAction(action)
            ?: Log.w(TAG, "AccessibilityService not available for $action")
    }

    private fun launchApp(appName: String) {
        val pm = context.packageManager
        // Try direct package name first
        var intent = pm.getLaunchIntentForPackage(appName)
        if (intent == null) {
            // Search installed apps by label
            val apps = pm.getInstalledApplications(0)
            val match = apps.firstOrNull {
                pm.getApplicationLabel(it).toString().equals(appName, ignoreCase = true)
            }
            if (match != null) {
                intent = pm.getLaunchIntentForPackage(match.packageName)
            }
        }
        if (intent != null) {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            Log.i(TAG, "Launched app: $appName")
        } else {
            Log.w(TAG, "App not found: $appName")
        }
    }

    private fun showOnMap(location: String) {
        val encoded = Uri.encode(location)
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=$encoded")).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    private fun launchEmailCompose(to: String, subject: String, body: String) {
        val intent = Intent(Intent.ACTION_SENDTO).apply {
            data = Uri.parse("mailto:")
            putExtra(Intent.EXTRA_EMAIL, arrayOf(to))
            putExtra(Intent.EXTRA_SUBJECT, subject)
            putExtra(Intent.EXTRA_TEXT, body)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    private fun launchCreateContact(firstName: String, lastName: String, phone: String, email: String) {
        val intent = Intent(ContactsContract.Intents.Insert.ACTION).apply {
            type = ContactsContract.RawContacts.CONTENT_TYPE
            putExtra(ContactsContract.Intents.Insert.NAME, "$firstName $lastName")
            putExtra(ContactsContract.Intents.Insert.PHONE, phone)
            putExtra(ContactsContract.Intents.Insert.EMAIL, email)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    private fun launchCalendarEvent(datetime: String, title: String) {
        val intent = Intent(Intent.ACTION_INSERT).apply {
            data = CalendarContract.Events.CONTENT_URI
            putExtra(CalendarContract.Events.TITLE, title)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        // Try to parse datetime for begin time
        try {
            val dt = java.time.LocalDateTime.parse(datetime)
            val millis = dt.atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
            intent.putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, millis)
            intent.putExtra(CalendarContract.EXTRA_EVENT_END_TIME, millis + 3600000) // 1hr default
        } catch (e: Exception) {
            Log.w(TAG, "Could not parse datetime: $datetime")
        }
        context.startActivity(intent)
    }

    private fun launchSetAlarm(time: String, label: String) {
        try {
            val parts = time.split(":")
            val hour = parts[0].toInt()
            val minute = parts.getOrNull(1)?.toInt() ?: 0
            val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
                putExtra(AlarmClock.EXTRA_HOUR, hour)
                putExtra(AlarmClock.EXTRA_MINUTES, minute)
                putExtra(AlarmClock.EXTRA_MESSAGE, label)
                putExtra(AlarmClock.EXTRA_SKIP_UI, false)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to set alarm: $time", e)
        }
    }

    // ─── Keyword intent matching — runs before model, no inference needed ───

    /**
     * Words that indicate a compound/multi-step command requiring backend processing.
     * If the text after the primary keyword contains any of these, return null so the
     * command falls through to the backend for full LLM-driven automation.
     */
    private val compoundIndicators = setOf(
        " and ", " then ", " after that ",
        " search ", " send ", " message ", " call ", " type ", " write ",
        " navigate ", " scroll ", " tap ", " click ", " select ", " swipe ",
        " find ", " look for ", " go to ", " play ", " share ", " post ",
        " reply ", " forward ", " download ", " upload ", " delete ",
        " using ", " with sim ", " use sim ",
    )

    /** True when the text contains words suggesting a multi-step task. */
    private fun isCompoundCommand(text: String): Boolean =
        compoundIndicators.any { text.contains(it) }

    private fun quickMatch(text: String): AuraAction? {
        val t = text.lowercase()

        // If the command looks compound (multi-step), skip local matching entirely
        // so the backend handles the full automation.
        if (isCompoundCommand(t)) return null

        return when {
            // Flashlight
            (t.contains("torch") || t.contains("flashlight")) && t.contains("off") -> AuraAction.FlashlightOff()
            t.contains("torch") || t.contains("flashlight") -> AuraAction.FlashlightOn()

            // Volume
            t.contains("louder") || t.contains("volume up") ||
                    (t.contains("volume") && (t.contains("up") || t.contains("increase") || t.contains("raise"))) ->
                AuraAction.VolumeUp()
            t.contains("quieter") || t.contains("volume down") ||
                    (t.contains("volume") && (t.contains("down") || t.contains("lower") || t.contains("decrease") || t.contains("reduce"))) ->
                AuraAction.VolumeDown()
            t.contains("mute") && !t.contains("unmute") -> AuraAction.VolumeMute()

            // Brightness
            t.contains("brighter") || t.contains("brightness up") ||
                    (t.contains("brightness") && (t.contains("increase") || t.contains("up"))) ->
                AuraAction.BrightnessUp()
            t.contains("darker") || t.contains("brightness down") || t.contains("dim screen") ||
                    (t.contains("brightness") && (t.contains("decrease") || t.contains("down"))) ->
                AuraAction.BrightnessDown()

            // DND — check "off/disable" before generic match
            (t.contains("do not disturb") || t.contains("dnd")) &&
                    (t.contains("off") || t.contains("disable") || t.contains("stop")) ->
                AuraAction.DndOff()
            t.contains("do not disturb") || t.contains("dnd") -> AuraAction.DndOn()

            // Auto-rotate — check "off/lock/disable" before generic match
            (t.contains("auto rotat") || t.contains("screen rotation")) &&
                    (t.contains("off") || t.contains("disable") || t.contains("lock")) ->
                AuraAction.AutoRotateOff()
            t.contains("auto rotat") || t.contains("screen rotation") -> AuraAction.AutoRotateOn()

            // Bluetooth settings — only pure toggle/settings commands
            t.contains("bluetooth") && !t.contains("send") && !t.contains("transfer") ->
                AuraAction.OpenBluetoothSettings()

            // WiFi settings — only pure toggle/settings commands
            (t.contains("wifi") || t.contains("wi-fi")) && !t.contains("search") && !t.contains("find") ->
                AuraAction.OpenWifiSettings()

            // Timer
            (t.contains("timer") || t.contains("countdown")) &&
                    (t.contains("set") || t.contains("start") || t.contains("minute") || t.contains("second")) -> {
                val mins = Regex("""(\d+)\s*min""").find(t)?.groupValues?.get(1)?.toIntOrNull()
                val secs = Regex("""(\d+)\s*sec""").find(t)?.groupValues?.get(1)?.toIntOrNull()
                val total = (mins?.times(60) ?: 0) + (secs ?: 0)
                if (total > 0) AuraAction.SetTimer(durationSeconds = total.toString()) else null
            }

            // Alarm
            t.contains("alarm") && (t.contains("set") || t.contains("wake") || t.contains("create")) -> {
                val m = Regex("""(\d{1,2}):?(\d{2})?\s*(am|pm)?""").find(t)
                if (m != null) {
                    var h = m.groupValues[1].toIntOrNull() ?: 7
                    val min = m.groupValues[2].toIntOrNull() ?: 0
                    val ampm = m.groupValues[3]
                    if (ampm == "pm" && h < 12) h += 12 else if (ampm == "am" && h == 12) h = 0
                    AuraAction.SetAlarm(time = "%02d:%02d".format(h, min), label = "Alarm")
                } else null
            }

            // Open / launch app — only simple "open <appname>" (no compound instructions)
            t.startsWith("open ") ->
                t.removePrefix("open ").trim().takeIf { it.isNotEmpty() }?.let { AuraAction.OpenApp(appName = it) }
            t.startsWith("launch ") ->
                t.removePrefix("launch ").trim().takeIf { it.isNotEmpty() }?.let { AuraAction.OpenApp(appName = it) }

            else -> null
        }
    }

    private fun launchSetTimer(durationSeconds: String) {
        try {
            val seconds = durationSeconds.toInt()
            val intent = Intent(AlarmClock.ACTION_SET_TIMER).apply {
                putExtra(AlarmClock.EXTRA_LENGTH, seconds)
                putExtra(AlarmClock.EXTRA_SKIP_UI, false)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to set timer: $durationSeconds", e)
        }
    }
}
