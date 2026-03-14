package com.aura.aura_ui.agent

import com.aura.aura_ui.accessibility.UIDataRequirement

data class CommanderDecision(
    val action: String,
    val uiRequirement: UIDataRequirement,
    val parameters: Map<String, Any> = emptyMap(),
)

interface CommanderAgent {
    suspend fun parseIntent(userInput: String): CommanderDecision
}

class RuleBasedCommander : CommanderAgent {
    override suspend fun parseIntent(userInput: String): CommanderDecision {
        val lowercaseInput = userInput.lowercase()

        return when {
            lowercaseInput.contains("what") ||
                lowercaseInput.contains("show") ||
                lowercaseInput.contains("see") ||
                lowercaseInput.contains("describe") -> {
                CommanderDecision(
                    action = "analyze_screen",
                    uiRequirement = UIDataRequirement.FULL_UI_DATA,
                )
            }

            lowercaseInput.contains("click") ||
                lowercaseInput.contains("tap") ||
                lowercaseInput.contains("press") ||
                lowercaseInput.contains("open") -> {
                CommanderDecision(
                    action = "click_element",
                    uiRequirement =
                        UIDataRequirement.UI_TREE_ONLY.copy(
                            requestReason = "element_interaction",
                        ),
                )
            }

            lowercaseInput.contains("scroll") ||
                lowercaseInput.contains("swipe") ||
                lowercaseInput.contains("back") ||
                lowercaseInput.contains("home") -> {
                CommanderDecision(
                    action = "gesture",
                    uiRequirement = UIDataRequirement.NONE,
                )
            }

            else -> {
                CommanderDecision(
                    action = "unknown",
                    uiRequirement = UIDataRequirement.UI_TREE_ONLY,
                )
            }
        }
    }
}
