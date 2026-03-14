package com.aura.aura_ui.functiongemma

import android.content.Context
import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.SamplerConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.withContext
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

private const val TAG = "FunctionGemmaEngine"
private const val MAX_TOKENS = 1024

/**
 * Wraps LiteRT-LM Engine + Conversation for Function Gemma inference.
 * Handles initialization, command processing, and cleanup.
 */
class FunctionGemmaEngine {

    private var engine: Engine? = null
    private var conversation: Conversation? = null
    private var lastRecognizedAction: AuraAction? = null
    private var tools: AuraFunctionTools? = null

    val isReady: Boolean get() = engine != null && conversation != null

    /**
     * Initialize the LiteRT-LM engine with the downloaded model.
     * Must be called from a background thread.
     */
    fun initialize(modelPath: String): String {
        return try {
            Log.d(TAG, "Initializing engine with model: $modelPath")

            val engineConfig = EngineConfig(
                modelPath = modelPath,
                backend = Backend.CPU,
                maxNumTokens = MAX_TOKENS,
            )

            val newEngine = Engine(engineConfig)
            newEngine.initialize()

            tools = AuraFunctionTools { action ->
                lastRecognizedAction = action
            }

            val newConversation = newEngine.createConversation(
                ConversationConfig(
                    samplerConfig = SamplerConfig(
                        topK = 64,
                        topP = 0.95,
                        temperature = 0.0,
                    ),
                    systemInstruction = buildSystemPrompt(),
                    tools = listOf(tools!!),
                )
            )

            engine = newEngine
            conversation = newConversation
            Log.d(TAG, "Engine initialized successfully")
            ""
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize engine", e)
            e.message ?: "Unknown initialization error"
        }
    }

    /**
     * Process a user command and return the recognized action, or null if not recognized.
     */
    suspend fun processCommand(userText: String): AuraAction? = withContext(Dispatchers.Default) {
        val conv = conversation ?: return@withContext null
        lastRecognizedAction = null

        try {
            val contents = mutableListOf<Content>()
            contents.add(Content.Text(userText))

            val responseBuilder = StringBuilder()
            conv.sendMessageAsync(Contents.of(contents))
                .catch { e ->
                    Log.e(TAG, "Inference error", e)
                }
                .onCompletion {
                    // Reset conversation after each inference (stateless classifier)
                    resetConversation()
                }
                .collect { chunk ->
                    responseBuilder.append(chunk.toString())
                }

            Log.d(TAG, "Model raw response: $responseBuilder")
            lastRecognizedAction
        } catch (e: Exception) {
            Log.e(TAG, "processCommand failed", e)
            resetConversation()
            null
        }
    }

    private fun resetConversation() {
        try {
            conversation?.close()
            val t = tools ?: return
            val e = engine ?: return
            conversation = e.createConversation(
                ConversationConfig(
                    samplerConfig = SamplerConfig(topK = 64, topP = 0.95, temperature = 0.0),
                    systemInstruction = buildSystemPrompt(),
                    tools = listOf(t),
                )
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to reset conversation", e)
        }
    }

    fun cleanup() {
        try { conversation?.close() } catch (e: Exception) { Log.e(TAG, "close conversation", e) }
        try { engine?.close() } catch (e: Exception) { Log.e(TAG, "close engine", e) }
        conversation = null
        engine = null
        tools = null
        Log.d(TAG, "Cleanup done")
    }

    private fun buildSystemPrompt(): Contents {
        val now = LocalDateTime.now()
        val dateTimeStr = now.format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"))
        val dayOfWeek = now.format(DateTimeFormatter.ofPattern("EEEE"))
        return Contents.of(
            listOf(
                "You are a model that can do function calling with the following functions",
                "Current date and time given in YYYY-MM-DDTHH:MM:SS format: $dateTimeStr\nDay of week is $dayOfWeek",
            ).map { Content.Text(it) }
        )
    }
}
