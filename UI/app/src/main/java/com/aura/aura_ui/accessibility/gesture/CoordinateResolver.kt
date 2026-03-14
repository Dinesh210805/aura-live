package com.aura.aura_ui.accessibility.gesture

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import com.aura.aura_ui.utils.AgentLogger

class CoordinateResolver(private val service: AccessibilityService) {
    val screenWidth: Int = service.resources.displayMetrics.widthPixels
    val screenHeight: Int = service.resources.displayMetrics.heightPixels

    fun resolve(target: GestureTarget): ResolvedCoordinate? {
        return when (target) {
            is GestureTarget.Coordinates -> resolveCoordinates(target)
            is GestureTarget.UIElement -> resolveUIElement(target)
            is GestureTarget.Direction -> null
        }
    }

    fun resolveDirection(target: GestureTarget.Direction): Pair<ResolvedCoordinate, ResolvedCoordinate> {
        val centerX = screenWidth / 2
        val centerY = screenHeight / 2
        val distanceX = (screenWidth * target.distanceRatio).toInt()
        val distanceY = (screenHeight * target.distanceRatio).toInt()

        return when (target.direction) {
            SwipeDirection.UP ->
                Pair(
                    ResolvedCoordinate(centerX, centerY + distanceY / 2),
                    ResolvedCoordinate(centerX, centerY - distanceY / 2),
                )
            SwipeDirection.DOWN ->
                Pair(
                    ResolvedCoordinate(centerX, centerY - distanceY / 2),
                    ResolvedCoordinate(centerX, centerY + distanceY / 2),
                )
            SwipeDirection.LEFT ->
                Pair(
                    ResolvedCoordinate(centerX + distanceX / 2, centerY),
                    ResolvedCoordinate(centerX - distanceX / 2, centerY),
                )
            SwipeDirection.RIGHT ->
                Pair(
                    ResolvedCoordinate(centerX - distanceX / 2, centerY),
                    ResolvedCoordinate(centerX + distanceX / 2, centerY),
                )
        }
    }

    fun isWithinBounds(
        x: Int,
        y: Int,
    ): Boolean {
        return x in 0..screenWidth && y in 0..screenHeight
    }

    private fun resolveCoordinates(target: GestureTarget.Coordinates): ResolvedCoordinate {
        val x: Int
        val y: Int
        if (target.normalized) {
            x = (target.x * screenWidth).toInt().coerceIn(0, screenWidth)
            y = (target.y * screenHeight).toInt().coerceIn(0, screenHeight)
        } else {
            x = target.x.toInt().coerceIn(0, screenWidth)
            y = target.y.toInt().coerceIn(0, screenHeight)
        }
        return ResolvedCoordinate(x, y)
    }

    private fun resolveUIElement(target: GestureTarget.UIElement): ResolvedCoordinate? {
        val rootNode =
            service.rootInActiveWindow ?: run {
                AgentLogger.Auto.w("No active window for UI element search")
                return null
            }

        try {
            val matches = mutableListOf<AccessibilityNodeInfo>()
            searchNodes(rootNode, target, matches, 0)

            if (matches.isEmpty()) {
                AgentLogger.Auto.w(
                    "UI element not found",
                    mapOf(
                        "text" to (target.text ?: ""),
                        "resourceId" to (target.resourceId ?: ""),
                        "contentDesc" to (target.contentDesc ?: ""),
                    ),
                )
                return null
            }

            val targetIndex = target.index.coerceIn(0, matches.size - 1)
            val node = matches[targetIndex]
            val bounds = Rect()
            node.getBoundsInScreen(bounds)

            val result =
                ResolvedCoordinate(
                    x = bounds.centerX(),
                    y = bounds.centerY(),
                    confidence = 1.0f,
                    elementText = node.text?.toString(),
                    bounds = bounds,
                )

            matches.forEach {
                @Suppress("DEPRECATION")
                it.recycle()
            }
            return result
        } finally {
            @Suppress("DEPRECATION")
            rootNode.recycle()
        }
    }

    private fun searchNodes(
        node: AccessibilityNodeInfo,
        target: GestureTarget.UIElement,
        matches: MutableList<AccessibilityNodeInfo>,
        depth: Int,
    ) {
        if (depth > 25) return

        if (matchesTarget(node, target)) {
            matches.add(AccessibilityNodeInfo.obtain(node))
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            searchNodes(child, target, matches, depth + 1)
            @Suppress("DEPRECATION")
            child.recycle()
        }
    }

    private fun matchesTarget(
        node: AccessibilityNodeInfo,
        target: GestureTarget.UIElement,
    ): Boolean {
        val nodeText = node.text?.toString()?.lowercase() ?: ""
        val nodeDesc = node.contentDescription?.toString()?.lowercase() ?: ""
        val nodeId = node.viewIdResourceName?.lowercase() ?: ""

        target.text?.let { text ->
            if (nodeText.contains(text.lowercase())) return true
        }
        target.contentDesc?.let { desc ->
            if (nodeDesc.contains(desc.lowercase())) return true
        }
        target.resourceId?.let { id ->
            if (nodeId.contains(id.lowercase())) return true
        }
        return false
    }
}
