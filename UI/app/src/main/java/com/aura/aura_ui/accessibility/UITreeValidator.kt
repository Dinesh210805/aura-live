package com.aura.aura_ui.accessibility

/**
 * UI Tree validation result.
 */
data class UITreeValidationResult(
    val isValid: Boolean,
    val reason: String? = null,
    val nodeCount: Int = 0,
    val validBoundsRatio: Float = 0f,
    val packageName: String? = null,
)

/**
 * UI Tree validator - rejects garbage trees before sending to backend.
 * 
 * Implements validation rules from UI Perception Pipeline blueprint:
 * - Min node count check
 * - Valid bounds ratio check
 * - App category rejection (games, cameras, maps)
 */
object UITreeValidator {
    private const val MIN_NODE_COUNT = 3
    private const val MIN_VALID_BOUNDS_RATIO = 0.1f
    
    // Package patterns that should use vision-only mode (not UI tree)
    // ONLY for apps with canvas/OpenGL rendering where accessibility tree is garbage
    private val VISION_ONLY_PACKAGES = setOf(
        // Games (canvas-based rendering)
        "com.supercell",
        "com.king",
        "com.rovio",
        "com.gameloft",
        "com.ea.games",
        "com.activision",
        "com.mojang",
        "com.tencent.ig", // PUBG
        "com.dts.freefireth", // Free Fire
        // Cameras (viewfinder is not accessible)
        "com.google.android.GoogleCamera",
        "com.sec.android.app.camera",
        "com.oneplus.camera",
        "com.huawei.camera",
        "com.android.camera",
        "com.android.camera2",
        // Maps (canvas-based map tiles)
        "com.google.android.apps.maps",
        "com.waze",
        "com.here.app.maps",
        // Canvas/Drawing apps
        "com.adobe.spark",
        "com.canva.editor",
        "com.autodesk.sketchbook",
        // NOTE: Video players REMOVED - they have proper UI trees (play/pause, titles, etc.)
    )
    
    // Package pattern matchers
    private val VISION_ONLY_PATTERNS = listOf(
        Regex(".*\\.game\\..*"),
        Regex(".*\\.camera\\..*"),
        Regex(".*\\.games\\..*"),
        Regex("com\\.supercell\\..*"),
        Regex("com\\.king\\..*"),
        Regex("com\\.gameloft\\..*"),
        Regex("com\\.ea\\..*"),
        Regex("com\\.rovio\\..*"),
    )
    
    /**
     * Validate UI tree before sending to backend.
     * 
     * @param elements List of UI elements
     * @param packageName Current app package name
     * @return Validation result
     */
    fun validate(
        elements: List<UIElementData>,
        packageName: String?,
    ): UITreeValidationResult {
        // Check package first - reject canvas/game/camera apps
        if (packageName != null && isVisionOnlyApp(packageName)) {
            return UITreeValidationResult(
                isValid = false,
                reason = "App category requires vision mode: $packageName",
                nodeCount = elements.size,
                validBoundsRatio = 0f,
                packageName = packageName,
            )
        }
        
        // Check min node count
        if (elements.size < MIN_NODE_COUNT) {
            return UITreeValidationResult(
                isValid = false,
                reason = "Too few nodes: ${elements.size} < $MIN_NODE_COUNT",
                nodeCount = elements.size,
                validBoundsRatio = 0f,
                packageName = packageName,
            )
        }
        
        // Check valid bounds ratio
        val nodesWithValidBounds = elements.count { elem ->
            elem.bounds.width > 5 && elem.bounds.height > 5 &&
            elem.bounds.right > elem.bounds.left &&
            elem.bounds.bottom > elem.bounds.top
        }
        
        val validBoundsRatio = if (elements.isNotEmpty()) {
            nodesWithValidBounds.toFloat() / elements.size
        } else {
            0f
        }
        
        if (validBoundsRatio < MIN_VALID_BOUNDS_RATIO) {
            return UITreeValidationResult(
                isValid = false,
                reason = "Too few valid bounds: ${(validBoundsRatio * 100).toInt()}% < ${(MIN_VALID_BOUNDS_RATIO * 100).toInt()}%",
                nodeCount = elements.size,
                validBoundsRatio = validBoundsRatio,
                packageName = packageName,
            )
        }
        
        // All checks passed
        return UITreeValidationResult(
            isValid = true,
            reason = null,
            nodeCount = elements.size,
            validBoundsRatio = validBoundsRatio,
            packageName = packageName,
        )
    }
    
    /**
     * Check if app should use vision-only mode.
     */
    fun isVisionOnlyApp(packageName: String): Boolean {
        // Check exact matches
        if (VISION_ONLY_PACKAGES.any { packageName.startsWith(it) }) {
            return true
        }
        
        // Check patterns
        if (VISION_ONLY_PATTERNS.any { it.matches(packageName) }) {
            return true
        }
        
        return false
    }
    
    /**
     * Get app category for modality selection.
     * NOTE: Category is informational only - does NOT determine vision mode.
     * Only isVisionOnlyApp() determines if UI tree should be rejected.
     */
    fun getAppCategory(packageName: String?): String {
        if (packageName == null) return "unknown"
        
        return when {
            packageName.contains("game", ignoreCase = true) -> "game"
            packageName.contains("camera", ignoreCase = true) -> "camera"
            packageName.contains("map", ignoreCase = true) -> "map"
            isVisionOnlyApp(packageName) -> "vision_required"
            else -> "standard"
        }
    }
}
