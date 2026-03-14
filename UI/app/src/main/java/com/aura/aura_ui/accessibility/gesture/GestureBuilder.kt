package com.aura.aura_ui.accessibility.gesture

import android.accessibilityservice.GestureDescription
import android.graphics.Path

class GestureBuilder {
    fun buildTap(
        x: Int,
        y: Int,
        durationMs: Long,
    ): GestureDescription {
        val duration = durationMs.coerceAtLeast(50L)
        val path =
            Path().apply {
                moveTo(x.toFloat(), y.toFloat())
            }
        return GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, duration))
            .build()
    }

    fun buildLongPress(
        x: Int,
        y: Int,
        durationMs: Long,
        holdMs: Long,
    ): GestureDescription {
        val duration = durationMs.coerceAtLeast(50L)
        val totalDuration = duration + holdMs.coerceAtLeast(400L)
        val path =
            Path().apply {
                moveTo(x.toFloat(), y.toFloat())
            }
        return GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, totalDuration))
            .build()
    }

    fun buildSwipe(
        startX: Int,
        startY: Int,
        endX: Int,
        endY: Int,
        durationMs: Long,
    ): GestureDescription {
        val duration = durationMs.coerceAtLeast(100L)
        val path =
            Path().apply {
                moveTo(startX.toFloat(), startY.toFloat())
                lineTo(endX.toFloat(), endY.toFloat())
            }
        return GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, duration))
            .build()
    }

    fun build(
        command: GestureCommand,
        start: ResolvedCoordinate,
        end: ResolvedCoordinate?,
    ): GestureDescription {
        return when (command.gestureType) {
            GestureType.TAP -> buildTap(start.x, start.y, command.options.durationMs)
            GestureType.LONG_PRESS ->
                buildLongPress(
                    start.x,
                    start.y,
                    command.options.durationMs,
                    command.options.holdMs,
                )
            GestureType.SWIPE, GestureType.SCROLL -> {
                val endCoord = end ?: start
                buildSwipe(start.x, start.y, endCoord.x, endCoord.y, command.options.durationMs)
            }
        }
    }
}
