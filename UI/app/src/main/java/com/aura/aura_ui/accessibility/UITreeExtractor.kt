package com.aura.aura_ui.accessibility

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Build
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import com.aura.aura_ui.utils.AgentLogger
import java.util.Locale

class UITreeExtractor(private val service: AccessibilityService) {
    
    companion object {
        // AURA package names to filter out from UI tree
        private val AURA_PACKAGES = setOf(
            "com.aura.aura_ui",
            "com.aura.aura_ui.debug",
            "com.aura.aura_ui.feature.debug"
        )
    }
    
    fun getUIElements(): List<UIElementData> {
        val elements = mutableListOf<UIElementData>()

        try {
            // Try to get UI tree from non-AURA window first
            val rootNode = getRootNodeExcludingAura()
            if (rootNode != null) {
                extractUIElements(rootNode, elements, parentNode = null)
                @Suppress("DEPRECATION")
                rootNode.recycle()
            } else {
                // Fallback to active window if no other window found
                val activeRoot = service.rootInActiveWindow
                if (activeRoot != null) {
                    extractUIElements(activeRoot, elements, parentNode = null)
                    @Suppress("DEPRECATION")
                    activeRoot.recycle()
                }
            }
        } catch (e: Exception) {
            AgentLogger.UI.e("Error extracting UI elements", e)
        }

        return elements
    }
    
    /**
     * Get root node from a window that is NOT the AURA overlay.
     * This allows capturing the underlying app's UI tree while overlay is visible.
     */
    private fun getRootNodeExcludingAura(): AccessibilityNodeInfo? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            return service.rootInActiveWindow
        }
        
        try {
            val windows = service.windows
            if (windows.isNullOrEmpty()) {
                AgentLogger.UI.d("No windows available, falling back to active window")
                return service.rootInActiveWindow
            }
            
            AgentLogger.UI.d("📱 Found ${windows.size} windows")
            
            // Sort windows by layer - we want the app window, not system UI or overlay
            // TYPE_APPLICATION = 1 is what we want
            var bestWindow: AccessibilityWindowInfo? = null
            var bestRoot: AccessibilityNodeInfo? = null
            
            for (window in windows) {
                val root = window.root ?: continue
                val packageName = root.packageName?.toString() ?: ""
                val windowType = window.type
                
                AgentLogger.UI.d("  Window: pkg=$packageName, type=$windowType, layer=${window.layer}")
                
                // Skip AURA's own windows
                if (AURA_PACKAGES.contains(packageName)) {
                    AgentLogger.UI.d("  → Skipping AURA overlay window")
                    @Suppress("DEPRECATION")
                    root.recycle()
                    continue
                }
                
                // Skip system UI (status bar, navigation bar)
                if (packageName == "com.android.systemui") {
                    @Suppress("DEPRECATION")
                    root.recycle()
                    continue
                }
                
                // Prefer TYPE_APPLICATION (1) windows over others
                if (windowType == AccessibilityWindowInfo.TYPE_APPLICATION) {
                    // Found an app window - use it
                    bestRoot?.let { 
                        @Suppress("DEPRECATION")
                        it.recycle() 
                    }
                    bestWindow = window
                    bestRoot = root
                    AgentLogger.UI.d("  → Selected as target app window: $packageName")
                    break // Found app window, done
                } else if (bestRoot == null) {
                    // Keep as fallback if no better option
                    bestWindow = window
                    bestRoot = root
                }
            }
            
            if (bestRoot != null) {
                AgentLogger.UI.i("🎯 Using window: ${bestRoot.packageName}")
                return bestRoot
            }
            
        } catch (e: Exception) {
            AgentLogger.UI.e("Error getting windows, falling back to active window", e)
        }
        
        return service.rootInActiveWindow
    }

    private fun extractUIElements(
        node: AccessibilityNodeInfo?,
        elements: MutableList<UIElementData>,
        currentDepth: Int = 0,
        maxDepth: Int = 15,
        maxElements: Int = 150,
        parentNode: AccessibilityNodeInfo? = null,
    ) {
        if (node == null || currentDepth > maxDepth || elements.size >= maxElements) {
            return
        }

        try {
            val bounds = Rect()
            node.getBoundsInScreen(bounds)
            
            // Smart bounds handling: Use parent bounds if current node has text but 0x0 size
            val hasText = !node.text.isNullOrBlank() || !node.contentDescription.isNullOrBlank()
            val hasZeroSize = bounds.width() == 0 || bounds.height() == 0
            
            val finalBounds = if (hasZeroSize && hasText && parentNode != null) {
                // Try to use parent's bounds if child has text but no size
                val parentBounds = Rect()
                parentNode.getBoundsInScreen(parentBounds)
                if (parentBounds.width() > 5 && parentBounds.height() > 5) {
                    AgentLogger.UI.d("📍 Using parent bounds for text element: '${node.text ?: node.contentDescription}'")
                    parentBounds
                } else {
                    bounds
                }
            } else {
                bounds
            }
            
            // Include elements with valid bounds OR elements with text (even if 0x0, we'll use parent bounds)
            val shouldInclude = (finalBounds.width() > 5 && finalBounds.height() > 5) || 
                               (hasText && hasZeroSize && parentNode != null)

            if (shouldInclude) {
                val boundsData =
                    BoundsData(
                        left = finalBounds.left,
                        top = finalBounds.top,
                        right = finalBounds.right,
                        bottom = finalBounds.bottom,
                        centerX = finalBounds.centerX(),
                        centerY = finalBounds.centerY(),
                        width = finalBounds.width(),
                        height = finalBounds.height(),
                    )
                
                // Inherit clickability from parent if current node has text but not clickable
                val isClickable = node.isClickable || 
                                 (hasText && !node.isClickable && parentNode?.isClickable == true)

                // Extract available actions from node
                val actionsList = mutableListOf<String>()
                node.actionList?.forEach { action ->
                    when (action.id) {
                        AccessibilityNodeInfo.ACTION_CLICK -> actionsList.add("click")
                        AccessibilityNodeInfo.ACTION_LONG_CLICK -> actionsList.add("long_click")
                        AccessibilityNodeInfo.ACTION_SCROLL_FORWARD -> actionsList.add("scroll_forward")
                        AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD -> actionsList.add("scroll_backward")
                        AccessibilityNodeInfo.ACTION_SET_TEXT -> actionsList.add("set_text")
                        AccessibilityNodeInfo.ACTION_COPY -> actionsList.add("copy")
                        AccessibilityNodeInfo.ACTION_PASTE -> actionsList.add("paste")
                        AccessibilityNodeInfo.ACTION_CUT -> actionsList.add("cut")
                    }
                }
                
                val element =
                    UIElementData(
                        text = node.text?.toString(),
                        contentDescription = node.contentDescription?.toString(),
                        bounds = boundsData,
                        className = node.className?.toString(),
                        isClickable = isClickable,
                        isScrollable = node.isScrollable,
                        isEditable = node.isEditable || node.className?.toString()?.contains("EditText") == true,
                        isEnabled = node.isEnabled,
                        isFocused = node.isFocused,
                        actions = actionsList,
                        packageName = node.packageName?.toString(),
                        viewId = node.viewIdResourceName,
                    )

                elements.add(element)
            }

            if (elements.size >= maxElements) {
                return
            }

            val childCount = node.childCount
            for (i in 0 until childCount) {
                if (elements.size >= maxElements) break

                try {
                    val child = node.getChild(i)
                    extractUIElements(child, elements, currentDepth + 1, maxDepth, maxElements, node)
                    @Suppress("DEPRECATION")
                    child?.recycle()
                } catch (e: Exception) {
                    // Continue with other children if one fails
                }
            }
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error extracting UI element", e)
        }
    }

    fun findNodesByText(text: String): List<AccessibilityNodeInfo> {
        val matchingNodes = mutableListOf<AccessibilityNodeInfo>()
        try {
            val rootNode = service.rootInActiveWindow
            if (rootNode != null) {
                findNodesByTextRecursive(rootNode, text.lowercase(Locale.ROOT), matchingNodes)
            }
        } catch (e: Exception) {
            AgentLogger.UI.e("Error finding nodes by text", e)
        }
        return matchingNodes
    }

    private fun findNodesByTextRecursive(
        node: AccessibilityNodeInfo,
        searchText: String,
        results: MutableList<AccessibilityNodeInfo>,
    ) {
        try {
            val nodeText = node.text?.toString()?.lowercase(Locale.ROOT)
            val nodeDesc = node.contentDescription?.toString()?.lowercase(Locale.ROOT)

            if ((nodeText?.contains(searchText) == true) || (nodeDesc?.contains(searchText) == true)) {
                results.add(node)
            }

            for (i in 0 until node.childCount) {
                val child = node.getChild(i)
                if (child != null) {
                    findNodesByTextRecursive(child, searchText, results)
                }
            }
        } catch (e: Exception) {
            AgentLogger.UI.e("Error in recursive text search", e)
        }
    }

    fun safeGetRootInActiveWindow(maxRetries: Int = 3): AccessibilityNodeInfo? {
        repeat(maxRetries) { attempt ->
            try {
                val root = service.rootInActiveWindow
                if (root != null) {
                    return root
                }
                if (attempt < maxRetries - 1) {
                    Thread.sleep(50)
                }
            } catch (e: Exception) {
                AgentLogger.Auto.d("Attempt ${attempt + 1}/$maxRetries to get root node failed: ${e.message}")
                if (attempt < maxRetries - 1) {
                    Thread.sleep(50)
                }
            }
        }
        AgentLogger.Auto.d("⚠️ Could not access rootInActiveWindow after $maxRetries attempts")
        return null
    }

    fun getUITree(): Map<String, Any>? {
        return try {
            val uiElements = getUIElements()
            val (packageName, _) = getCurrentApp()
            
            // Validate UI tree before returning
            val validation = UITreeValidator.validate(uiElements, packageName)
            
            if (!validation.isValid) {
                AgentLogger.UI.w("UI tree validation failed: ${validation.reason}")
                // Return validation failure info instead of null
                return mapOf(
                    "validation_failed" to true,
                    "validation_reason" to (validation.reason ?: "Unknown"),
                    "elements_count" to validation.nodeCount,
                    "valid_bounds_ratio" to validation.validBoundsRatio,
                    "package_name" to (packageName ?: ""),
                    "app_category" to UITreeValidator.getAppCategory(packageName),
                    "requires_vision" to true,
                    "timestamp" to System.currentTimeMillis(),
                )
            }
            
            val treeMap = mutableMapOf<String, Any>()

            treeMap["validation_failed"] = false
            treeMap["elements_count"] = uiElements.size
            treeMap["clickable_count"] = uiElements.count { it.isClickable }
            treeMap["scrollable_count"] = uiElements.count { it.isScrollable }
            treeMap["editable_count"] = uiElements.count { it.isEditable }
            treeMap["package_name"] = packageName ?: ""
            treeMap["app_category"] = UITreeValidator.getAppCategory(packageName)
            treeMap["valid_bounds_ratio"] = validation.validBoundsRatio

            val elementsData =
                uiElements.map { elem ->
                    mapOf(
                        "text" to (elem.text ?: ""),
                        "contentDescription" to (elem.contentDescription ?: ""),
                        "className" to (elem.className ?: ""),
                        "bounds" to
                            mapOf(
                                "left" to elem.bounds.left,
                                "top" to elem.bounds.top,
                                "right" to elem.bounds.right,
                                "bottom" to elem.bounds.bottom,
                                "centerX" to elem.bounds.centerX,
                                "centerY" to elem.bounds.centerY,
                            ),
                        "isClickable" to elem.isClickable,
                        "isScrollable" to elem.isScrollable,
                        "isEditable" to elem.isEditable,
                        "isEnabled" to elem.isEnabled,
                        "isFocused" to elem.isFocused,
                        "actions" to elem.actions,
                        "viewId" to (elem.viewId ?: ""),
                    )
                }

            treeMap["elements"] = elementsData
            treeMap["timestamp"] = System.currentTimeMillis()

            AgentLogger.UI.d("UI tree validated: ${uiElements.size} elements, ${(validation.validBoundsRatio * 100).toInt()}% valid bounds")
            treeMap
        } catch (e: Exception) {
            AgentLogger.UI.e("Error getting UI tree", e)
            null
        }
    }

    fun getCurrentApp(): Pair<String, String> {
        return try {
            val rootNode = service.rootInActiveWindow
            val packageName = rootNode?.packageName?.toString() ?: ""
            val activityName = "unknown_activity"

            Pair(packageName, activityName)
        } catch (e: Exception) {
            AgentLogger.Auto.e("Error getting current app info", e)
            Pair("", "")
        }
    }
}
