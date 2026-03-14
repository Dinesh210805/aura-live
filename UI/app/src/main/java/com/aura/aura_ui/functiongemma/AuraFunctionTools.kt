package com.aura.aura_ui.functiongemma

import android.util.Log
import com.google.ai.edge.litertlm.Tool
import com.google.ai.edge.litertlm.ToolParam

private const val TAG = "AuraFunctionTools"

/**
 * The 7 phone-control functions the MobileActions-270M model was fine-tuned on.
 * Using ONLY these keeps the total prompt far below the model's 1024-token context limit.
 * All other device actions (volume, brightness, DND, rotation, alarms, app launch, etc.)
 * are handled by fast keyword matching in LocalCommandRouter before this model is invoked.
 *
 * Tool descriptions match the Gallery training data exactly (including trailing periods)
 * to maximise the model's recognition accuracy.
 */
class AuraFunctionTools(val onActionRecognized: (AuraAction) -> Unit) {

    @Tool(description = "Turns the flashlight on")
    fun turnOnFlashlight(): Map<String, String> {
        Log.d(TAG, "turnOnFlashlight")
        onActionRecognized(AuraAction.FlashlightOn())
        return mapOf("result" to "success")
    }

    @Tool(description = "Turns the flashlight off")
    fun turnOffFlashlight(): Map<String, String> {
        Log.d(TAG, "turnOffFlashlight")
        onActionRecognized(AuraAction.FlashlightOff())
        return mapOf("result" to "success")
    }

    @Tool(description = "Opens the WiFi settings.")
    fun openWifiSettings(): Map<String, String> {
        Log.d(TAG, "openWifiSettings")
        onActionRecognized(AuraAction.OpenWifiSettings())
        return mapOf("result" to "success")
    }

    @Tool(description = "Creates a contact in the phone's contact list.")
    fun createContact(
        @ToolParam(description = "The first name of the contact.") firstName: String,
        @ToolParam(description = "The last name of the contact.") lastName: String,
        @ToolParam(description = "The phone number of the contact.") phoneNumber: String,
        @ToolParam(description = "The email address of the contact.") email: String,
    ): Map<String, String> {
        Log.d(TAG, "createContact: $firstName $lastName")
        onActionRecognized(AuraAction.CreateContact(
            firstName = firstName, lastName = lastName,
            phoneNumber = phoneNumber, email = email,
        ))
        return mapOf("result" to "success")
    }

    @Tool(description = "Sends an email.")
    fun sendEmail(
        @ToolParam(description = "The email address of the recipient.") to: String,
        @ToolParam(description = "The subject of the email.") subject: String,
        @ToolParam(description = "The body of the email.") body: String,
    ): Map<String, String> {
        Log.d(TAG, "sendEmail to=$to")
        onActionRecognized(AuraAction.SendEmail(to = to, subject = subject, body = body))
        return mapOf("result" to "success")
    }

    @Tool(description = "Shows a location on the map.")
    fun showLocationOnMap(
        @ToolParam(description = "The location to search for. May be the name of a place, a business, or an address.")
        location: String,
    ): Map<String, String> {
        Log.d(TAG, "showLocationOnMap: $location")
        onActionRecognized(AuraAction.ShowLocationOnMap(location = location))
        return mapOf("result" to "success")
    }

    @Tool(description = "Creates a new calendar event.")
    fun createCalendarEvent(
        @ToolParam(description = "The date and time of the event in the format YYYY-MM-DDTHH:MM:SS.")
        datetime: String,
        @ToolParam(description = "The title of the event.") title: String,
    ): Map<String, String> {
        Log.d(TAG, "createCalendarEvent: $title @ $datetime")
        onActionRecognized(AuraAction.CreateCalendarEvent(datetime = datetime, title = title))
        return mapOf("result" to "success")
    }
}
