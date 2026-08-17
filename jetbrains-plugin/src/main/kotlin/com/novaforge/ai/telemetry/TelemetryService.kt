package com.novaforge.ai.telemetry

import com.google.gson.Gson
import com.novaforge.ai.settings.NovaForgeSettings
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import java.time.Instant
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class TelemetryService {

    private val gson = Gson()
    private val client: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build()
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val eventQueue = ConcurrentLinkedQueue<TelemetryEvent>()
    private val sessionId: String = UUID.randomUUID().toString()
    private val flushIntervalMs = 30_000L

    init {
        startFlusher()
    }

    private fun startFlusher() {
        val thread = Thread({
            while (!Thread.currentThread().isInterrupted) {
                try {
                    Thread.sleep(flushIntervalMs)
                    flush()
                } catch (e: InterruptedException) {
                    Thread.currentThread().interrupt()
                    break
                } catch (e: Exception) {
                    // ignore flush errors
                }
            }
        }, "novaforge-telemetry-flusher")
        thread.isDaemon = true
        thread.start()
    }

    fun trackCommand(command: String, latencyMs: Long, success: Boolean) {
        val settings = NovaForgeSettings.getInstance()
        if (!settings.telemetryEnabled) return

        eventQueue.offer(TelemetryEvent(
            event = "command",
            data = mapOf(
                "command" to command,
                "latency_ms" to latencyMs,
                "success" to success
            ),
            sessionId = sessionId,
            timestamp = Instant.now().toString()
        ))
    }

    fun trackError(command: String, errorType: String, errorMessage: String) {
        val settings = NovaForgeSettings.getInstance()
        if (!settings.telemetryEnabled) return

        eventQueue.offer(TelemetryEvent(
            event = "error",
            data = mapOf(
                "command" to command,
                "error_type" to errorType,
                "message" to errorMessage
            ),
            sessionId = sessionId,
            timestamp = Instant.now().toString()
        ))
    }

    fun trackFeatureUsage(feature: String) {
        val settings = NovaForgeSettings.getInstance()
        if (!settings.telemetryEnabled) return

        eventQueue.offer(TelemetryEvent(
            event = "feature_usage",
            data = mapOf("feature" to feature),
            sessionId = sessionId,
            timestamp = Instant.now().toString()
        ))
    }

    fun trackSessionStart() {
        val settings = NovaForgeSettings.getInstance()
        if (!settings.telemetryEnabled) return

        eventQueue.offer(TelemetryEvent(
            event = "session_start",
            data = emptyMap(),
            sessionId = sessionId,
            timestamp = Instant.now().toString()
        ))
    }

    fun trackSessionEnd() {
        val settings = NovaForgeSettings.getInstance()
        if (!settings.telemetryEnabled) return

        eventQueue.offer(TelemetryEvent(
            event = "session_end",
            data = emptyMap(),
            sessionId = sessionId,
            timestamp = Instant.now().toString()
        ))
        flush()
    }

    private fun flush() {
        val events = mutableListOf<TelemetryEvent>()
        while (eventQueue.isNotEmpty()) {
            eventQueue.poll()?.let { events.add(it) }
        }
        if (events.isEmpty()) return

        val settings = NovaForgeSettings.getInstance()
        val apiUrl = settings.apiUrl
        if (apiUrl.isNullOrBlank()) return

        executor.submit {
            try {
                val body = gson.toJson(mapOf("events" to events))
                val uri = URI.create("${apiUrl.trimEnd('/')}/telemetry")
                val request = HttpRequest.newBuilder()
                    .uri(uri)
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build()
                client.send(request, HttpResponse.BodyHandlers.ofString())
            } catch (e: Exception) {
                // Silently ignore telemetry errors
            }
        }
    }

    fun shutdown() {
        flush()
        executor.shutdownNow()
    }

    data class TelemetryEvent(
        val event: String,
        val data: Map<String, Any>,
        val sessionId: String,
        val timestamp: String
    )
}
