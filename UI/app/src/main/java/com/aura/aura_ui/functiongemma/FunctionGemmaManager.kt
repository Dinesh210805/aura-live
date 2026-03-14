package com.aura.aura_ui.functiongemma

import android.content.Context
import android.os.Environment
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

private const val TAG = "FunctionGemmaManager"

/** Model filename stored locally. */
private const val MODEL_FILENAME = "mobile_actions_q8_ekv1024.litertlm"

/**
 * HuggingFace download URL — uses the exact commit hash from the Google Edge AI Gallery
 * allowlist so we get the identical binary. ?download=true bypasses the HuggingFace viewer
 * and returns the raw binary directly.
 */
private const val MODEL_DOWNLOAD_URL =
    "https://huggingface.co/litert-community/functiongemma-270m-ft-mobile-actions" +
    "/resolve/38942192c9b723af836d489074823ff33d4a3e7a/mobile_actions_q8_ekv1024.litertlm?download=true"

/** Google Edge AI Gallery app package id (applicationId in its build.gradle). */
private const val GALLERY_PKG = "com.google.aiedge.gallery"

/** Normalized model name used by the Gallery for directory naming. */
private const val GALLERY_MODEL_DIR = "MobileActions_270M"

/** Commit hash the Gallery pins this model to. */
private const val GALLERY_MODEL_VERSION = "38942192c9b723af836d489074823ff33d4a3e7a"

/** Approximate model size in bytes (~302 MB). */
const val MODEL_SIZE_BYTES = 302_000_000L

/** Current state of the model lifecycle. */
enum class ModelState {
    NOT_DOWNLOADED,
    DOWNLOADING,
    DOWNLOADED,
    INITIALIZING,
    READY,
    ERROR,
}

/**
 * Manages the Function Gemma model lifecycle: download, storage, engine init, and routing.
 */
class FunctionGemmaManager(private val context: Context) {

    private val _state = MutableStateFlow(ModelState.NOT_DOWNLOADED)
    val state: StateFlow<ModelState> = _state.asStateFlow()

    private val _downloadProgress = MutableStateFlow(0f)
    val downloadProgress: StateFlow<Float> = _downloadProgress.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private val prefs = context.getSharedPreferences("functiongemma_prefs", Context.MODE_PRIVATE)
    private val _pipelineEnabled = MutableStateFlow(prefs.getBoolean("pipeline_enabled", true))
    val pipelineEnabled: StateFlow<Boolean> = _pipelineEnabled.asStateFlow()

    fun setPipelineEnabled(enabled: Boolean) {
        prefs.edit().putBoolean("pipeline_enabled", enabled).apply()
        _pipelineEnabled.value = enabled
    }

    val engine = FunctionGemmaEngine()
    private var router: LocalCommandRouter? = null

    /** AURA's own downloaded copy inside internal storage. */
    private val modelDir: File get() = File(context.filesDir, "functiongemma")
    private val modelFile: File get() = File(modelDir, MODEL_FILENAME)

    /**
     * Path where the Google Edge AI Gallery stores this model on external storage.
     * Accessible on Android ≤10 with READ_EXTERNAL_STORAGE, or on Android 11+ only when
     * the manufacturer hasn't enforced the data isolation restriction (some OEMs don't).
     * On restricted devices this file will still .exists() == false, so we fall back silently.
     */
    private val galleryModelFile: File
        get() = File(
            Environment.getExternalStorageDirectory(),
            "Android/data/$GALLERY_PKG/files/$GALLERY_MODEL_DIR/$GALLERY_MODEL_VERSION/$MODEL_FILENAME"
        )

    /**
     * Returns whichever model file is available: Gallery's first (saves bandwidth),
     * then AURA's own download, then null (needs download).
     */
    private fun resolveModelFile(): File? {
        val gallery = galleryModelFile
        if (gallery.exists() && gallery.canRead() && gallery.length() > MODEL_SIZE_BYTES / 2) {
            Log.i(TAG, "Found model in Edge AI Gallery: ${gallery.absolutePath}")
            return gallery
        }
        val local = modelFile
        if (local.exists() && local.length() > MODEL_SIZE_BYTES / 2) {
            return local
        }
        return null
    }

    init {
        if (resolveModelFile() != null) {
            _state.value = ModelState.DOWNLOADED
        }
    }

    val isModelReady: Boolean get() = _state.value == ModelState.READY && _pipelineEnabled.value
    val isModelDownloaded: Boolean get() = _state.value == ModelState.DOWNLOADED

    fun getRouter(): LocalCommandRouter? = router

    /**
     * Download the model file from HuggingFace. Reports progress via [downloadProgress].
     * HuggingFace issues 302 redirects to CDN; we follow them manually so we can
     * correctly attach the Range header on the final CDN URL (not on the HF redirect URL).
     *
     * @param hfToken Optional HuggingFace access token (required for gated models).
     *   Get one at https://huggingface.co/settings/tokens — a READ token is sufficient.
     */
    suspend fun downloadModel(hfToken: String? = null): Boolean = withContext(Dispatchers.IO) {
        if (_state.value == ModelState.DOWNLOADING) return@withContext false
        _state.value = ModelState.DOWNLOADING
        _downloadProgress.value = 0f
        _errorMessage.value = null

        val token = hfToken?.trim()?.takeIf { it.isNotEmpty() }

        try {
            modelDir.mkdirs()
            val tempFile = File(modelDir, "$MODEL_FILENAME.tmp")

            // Resolve all redirects first (HuggingFace redirects to CDN).
            // Pass the token on the HF URL so the redirect check is authenticated.
            val finalUrl = resolveRedirects(MODEL_DOWNLOAD_URL, token = token)
            Log.i(TAG, "Downloading from: $finalUrl")

            val connection = openConnection(finalUrl, tempFile, token = token)
            val responseCode = connection.responseCode

            if (responseCode != HttpURLConnection.HTTP_OK && responseCode != 206) {
                val msg = when (responseCode) {
                    401 -> "HTTP 401: Invalid or missing token. Get a READ token at huggingface.co/settings/tokens."
                    403 -> "HTTP 403: Access denied. Visit huggingface.co/litert-community/functiongemma-270m-ft-mobile-actions and click \"Agree and access repository\", then retry."
                    404 -> "HTTP 404: Model file not found. The URL may have changed."
                    else -> "HTTP $responseCode: Download failed."
                }
                Log.e(TAG, msg)
                _errorMessage.value = msg
                _state.value = ModelState.ERROR
                connection.disconnect()
                return@withContext false
            }

            val totalSize = if (responseCode == 206) {
                connection.getHeaderField("Content-Range")
                    ?.substringAfter("/")?.toLongOrNull() ?: MODEL_SIZE_BYTES
            } else {
                connection.contentLengthLong.takeIf { it > 0 } ?: MODEL_SIZE_BYTES
            }

            val append = responseCode == 206
            val startBytes = if (append) tempFile.length() else 0L

            connection.inputStream.use { input ->
                FileOutputStream(tempFile, append).use { output ->
                    val buffer = ByteArray(16_384)
                    var bytesRead: Int
                    var totalRead = startBytes
                    while (input.read(buffer).also { bytesRead = it } != -1) {
                        output.write(buffer, 0, bytesRead)
                        totalRead += bytesRead
                        _downloadProgress.value = (totalRead.toFloat() / totalSize).coerceIn(0f, 1f)
                    }
                }
            }
            connection.disconnect()

            if (modelFile.exists()) modelFile.delete()
            tempFile.renameTo(modelFile)

            _downloadProgress.value = 1f
            _state.value = ModelState.DOWNLOADED
            Log.i(TAG, "Model downloaded: ${modelFile.length()} bytes")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Download failed", e)
            _errorMessage.value = e.message ?: "Download failed"
            _state.value = ModelState.ERROR
            false
        }
    }

    /**
     * Follow HTTP 301/302/307/308 redirects manually and return the final URL.
     * The auth token is sent only on the initial HF URL; CDN redirect URLs don't need it.
     */
    private fun resolveRedirects(startUrl: String, maxHops: Int = 10, token: String? = null): String {
        var url = startUrl
        var isFirst = true
        repeat(maxHops) {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.instanceFollowRedirects = false
            conn.requestMethod = "HEAD"
            conn.setRequestProperty("User-Agent", "AuraAgent/2.0")
            if (isFirst && token != null) {
                conn.setRequestProperty("Authorization", "Bearer $token")
            }
            conn.connectTimeout = 15_000
            conn.readTimeout = 15_000
            conn.connect()
            val code = conn.responseCode
            val location = conn.getHeaderField("Location")
            conn.disconnect()
            isFirst = false
            if (code in 301..308 && location != null) {
                url = location
            } else {
                return url
            }
        }
        return url
    }

    private fun openConnection(url: String, tempFile: File, token: String? = null): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.instanceFollowRedirects = false
        conn.connectTimeout = 30_000
        conn.readTimeout = 120_000
        conn.setRequestProperty("User-Agent", "AuraAgent/2.0")
        if (token != null) {
            conn.setRequestProperty("Authorization", "Bearer $token")
        }
        if (tempFile.exists() && tempFile.length() > 0) {
            conn.setRequestProperty("Range", "bytes=${tempFile.length()}-")
            // Prevent compressed response so Range header works correctly
            conn.setRequestProperty("Accept-Encoding", "identity")
        }
        conn.connect()
        return conn
    }

    /**
     * Initialize the engine with the downloaded model. Call after download completes.
     * Uses the Gallery model if accessible, otherwise AURA's own downloaded copy.
     */
    suspend fun initializeEngine(): Boolean = withContext(Dispatchers.IO) {
        val file = resolveModelFile()
        if (file == null) {
            _errorMessage.value = "Model not found. Please download it."
            _state.value = ModelState.ERROR
            return@withContext false
        }

        _state.value = ModelState.INITIALIZING
        Log.i(TAG, "Initializing engine from: ${file.absolutePath}")
        val error = engine.initialize(file.absolutePath)

        if (error.isEmpty()) {
            router = LocalCommandRouter(context, engine)
            _state.value = ModelState.READY
            Log.i(TAG, "Engine ready")
            true
        } else {
            _errorMessage.value = error
            _state.value = ModelState.ERROR
            false
        }
    }

    /**
     * Download (if needed) and initialize. Convenience method.
     */
    suspend fun downloadAndInitialize(hfToken: String? = null): Boolean {
        if (_state.value == ModelState.READY) return true
        if (_state.value != ModelState.DOWNLOADED) {
            if (!downloadModel(hfToken)) return false
        }
        return initializeEngine()
    }

    /**
     * Delete AURA's own downloaded model copy. If the Gallery model was being used,
     * the state goes back to DOWNLOADED (Gallery model still accessible).
     */
    fun deleteModel() {
        engine.cleanup()
        router = null
        modelFile.delete()
        File(modelDir, "$MODEL_FILENAME.tmp").delete()
        // Check if Gallery model still available as fallback
        _state.value = if (resolveModelFile() != null) ModelState.DOWNLOADED else ModelState.NOT_DOWNLOADED
        _downloadProgress.value = 0f
        _errorMessage.value = null
        Log.i(TAG, "Local model deleted")
    }

    /** Returns true when the Gallery model is being used (no local copy needed). */
    fun isUsingGalleryModel(): Boolean {
        val gallery = galleryModelFile
        return gallery.exists() && gallery.canRead() && gallery.length() > MODEL_SIZE_BYTES / 2
    }

    fun cleanup() {
        engine.cleanup()
        router = null
        if (_state.value == ModelState.READY || _state.value == ModelState.INITIALIZING) {
            _state.value = ModelState.DOWNLOADED
        }
    }

    /** Model file size on disk in bytes, or 0 if not available anywhere. */
    fun getModelSizeOnDisk(): Long = resolveModelFile()?.length() ?: 0L
}
