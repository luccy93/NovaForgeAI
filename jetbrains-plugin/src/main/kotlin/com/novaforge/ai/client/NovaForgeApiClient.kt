package com.novaforge.ai.client

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.novaforge.ai.settings.NovaForgeSettings
import java.io.BufferedReader
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import java.util.concurrent.Flow
import java.util.concurrent.SubmissionPublisher

class NovaForgeApiClient {

    private val gson = Gson()
    private val client: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(15))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build()

    private val settings: NovaForgeSettings
        get() = NovaForgeSettings.getInstance()

    private fun baseUrl(): String {
        val url = settings.apiUrl.trimEnd('/')
        return if (url.endsWith("/api")) url else "$url/api"
    }

    private fun buildHeaders(): MutableMap<String, String> {
        val headers = mutableMapOf(
            "Content-Type" to "application/json",
            "Accept" to "application/json"
        )
        val token = settings.bearerToken
        if (!token.isNullOrBlank()) {
            headers["Authorization"] = "Bearer $token"
        }
        val apiKey = settings.apiKey
        if (!apiKey.isNullOrBlank()) {
            headers["X-API-Key"] = apiKey
        }
        return headers
    }

    private fun post(path: String, body: Any?): JsonObject {
        val uri = URI.create("${baseUrl()}$path")
        val jsonBody = if (body != null) gson.toJson(body) else "{}"
        val requestBuilder = HttpRequest.newBuilder()
            .uri(uri)
            .timeout(Duration.ofSeconds(60))
            .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
        buildHeaders().forEach { (k, v) -> requestBuilder.header(k, v) }
        val response = client.send(requestBuilder.build(), HttpResponse.BodyHandlers.ofString())
        if (response.statusCode() >= 400) {
            throw NovaForgeApiException(
                response.statusCode(),
                "API error ${response.statusCode()}: ${response.body()}"
            )
        }
        return JsonParser.parseString(response.body()).asJsonObject
    }

    private fun get(path: String): JsonObject {
        val uri = URI.create("${baseUrl()}$path")
        val requestBuilder = HttpRequest.newBuilder()
            .uri(uri)
            .timeout(Duration.ofSeconds(30))
            .GET()
        buildHeaders().forEach { (k, v) -> requestBuilder.header(k, v) }
        val response = client.send(requestBuilder.build(), HttpResponse.BodyHandlers.ofString())
        if (response.statusCode() >= 400) {
            throw NovaForgeApiException(
                response.statusCode(),
                "API error ${response.statusCode()}: ${response.body()}"
            )
        }
        return JsonParser.parseString(response.body()).asJsonObject
    }

    fun login(apiUrl: String, email: String, password: String): AuthResult {
        val uri = URI.create("${apiUrl.trimEnd('/')}/api/auth/login")
        val body = gson.toJson(mapOf("email" to email, "password" to password))
        val request = HttpRequest.newBuilder()
            .uri(uri)
            .timeout(Duration.ofSeconds(30))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build()
        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        if (response.statusCode() != 200) {
            throw NovaForgeApiException(response.statusCode(), "Login failed: ${response.body()}")
        }
        val json = JsonParser.parseString(response.body()).asJsonObject
        return AuthResult(
            token = json.get("token").asString,
            refreshToken = json.get("refresh_token")?.asString,
            expiresAt = json.get("expires_at")?.asLong ?: 0L
        )
    }

    fun whoami(): JsonObject = get("/auth/whoami")

    fun status(): JsonObject = get("/status")

    fun chat(
        sessionId: String?,
        message: String,
        model: String?,
        organizationId: String?,
        repositoryId: String?,
        context: Map<String, Any>?
    ): JsonObject {
        val body = mutableMapOf<String, Any>(
            "message" to message
        )
        sessionId?.let { body["session_id"] = it }
        model?.let { body["model"] = it }
        organizationId?.let { body["organization_id"] = it }
        repositoryId?.let { body["repository_id"] = it }
        context?.let { body["context"] = it }
        return post("/chat", body)
    }

    fun chatStream(
        sessionId: String?,
        message: String,
        model: String?,
        organizationId: String?,
        repositoryId: String?,
        context: Map<String, Any>?
    ): Flow<StreamChunk> {
        val publisher = SubmissionPublisher<StreamChunk>()
        Thread {
            try {
                val uri = URI.create("${baseUrl()}/chat/stream")
                val body = mutableMapOf<String, Any>("message" to message)
                sessionId?.let { body["session_id"] = it }
                model?.let { body["model"] = it }
                organizationId?.let { body["organization_id"] = it }
                repositoryId?.let { body["repository_id"] = it }
                context?.let { body["context"] = it }
                val requestBuilder = HttpRequest.newBuilder()
                    .uri(uri)
                    .timeout(Duration.ofSeconds(120))
                    .header("Content-Type", "application/json")
                    .header("Accept", "text/event-stream")
                    .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(body)))
                buildHeaders().forEach { (k, v) -> requestBuilder.header(k, v) }
                val response = client.send(
                    requestBuilder.build(),
                    HttpResponse.BodyHandlers.ofBufferedReader()
                )
                val reader: BufferedReader = response.body()
                var currentEvent = ""
                reader.use { br ->
                    var line: String? = br.readLine()
                    while (line != null) {
                        if (line.startsWith("event: ")) {
                            currentEvent = line.removePrefix("event: ").trim()
                        } else if (line.startsWith("data: ")) {
                            val data = line.removePrefix("data: ").trim()
                            if (data == "[DONE]") {
                                publisher.submit(StreamChunk(event = "done", data = ""))
                                break
                            }
                            try {
                                val json = JsonParser.parseString(data).asJsonObject
                                val chunk = StreamChunk(
                                    event = currentEvent.ifBlank { json.get("event")?.asString ?: "message" },
                                    data = json.get("content")?.asString ?: data,
                                    sessionId = json.get("session_id")?.asString,
                                    done = json.get("done")?.asBoolean ?: false
                                )
                                publisher.submit(chunk)
                                if (chunk.done) break
                            } catch (e: Exception) {
                                publisher.submit(StreamChunk(event = currentEvent, data = data))
                            }
                        }
                        line = br.readLine()
                    }
                }
            } catch (e: Exception) {
                publisher.submit(StreamChunk(event = "error", data = e.message ?: "Unknown error"))
            } finally {
                publisher.close()
            }
        }.start()
        return publisher
    }

    fun search(
        query: String,
        repositoryId: String?,
        organizationId: String?,
        limit: Int?
    ): JsonObject {
        val body = mutableMapOf<String, Any>("query" to query)
        repositoryId?.let { body["repository_id"] = it }
        organizationId?.let { body["organization_id"] = it }
        limit?.let { body["limit"] = it }
        return post("/search", body)
    }

    fun codeAction(
        action: String,
        code: String,
        language: String,
        filePath: String?,
        lineStart: Int?,
        lineEnd: Int?,
        model: String?,
        context: Map<String, Any>?
    ): JsonObject {
        val body = mutableMapOf<String, Any>(
            "action" to action,
            "code" to code,
            "language" to language
        )
        filePath?.let { body["file_path"] = it }
        lineStart?.let { body["line_start"] = it }
        lineEnd?.let { body["line_end"] = it }
        model?.let { body["model"] = it }
        context?.let { body["context"] = it }
        return post("/code/action", body)
    }

    fun review(
        code: String,
        language: String,
        filePath: String?,
        organizationId: String?,
        repositoryId: String?
    ): JsonObject {
        val body = mutableMapOf<String, Any>(
            "code" to code,
            "language" to language
        )
        filePath?.let { body["file_path"] = it }
        organizationId?.let { body["organization_id"] = it }
        repositoryId?.let { body["repository_id"] = it }
        return post("/code/review", body)
    }

    fun runAgent(
        agentType: String,
        prompt: String,
        organizationId: String?,
        repositoryId: String?,
        config: Map<String, Any>?
    ): JsonObject {
        val body = mutableMapOf<String, Any>(
            "agent_type" to agentType,
            "prompt" to prompt
        )
        organizationId?.let { body["organization_id"] = it }
        repositoryId?.let { body["repository_id"] = it }
        config?.let { body["config"] = it }
        return post("/agents/run", body)
    }

    fun runWorkflow(
        workflowId: String,
        inputs: Map<String, Any>?,
        organizationId: String?
    ): JsonObject {
        val body = mutableMapOf<String, Any>(
            "workflow_id" to workflowId
        )
        inputs?.let { body["inputs"] = it }
        organizationId?.let { body["organization_id"] = it }
        return post("/workflows/run", body)
    }

    fun createSession(
        title: String?,
        organizationId: String?,
        repositoryId: String?,
        model: String?
    ): JsonObject {
        val body = mutableMapOf<String, Any>()
        title?.let { body["title"] = it }
        organizationId?.let { body["organization_id"] = it }
        repositoryId?.let { body["repository_id"] = it }
        model?.let { body["model"] = it }
        return post("/chat/sessions", body)
    }

    data class AuthResult(
        val token: String,
        val refreshToken: String?,
        val expiresAt: Long
    )

    data class StreamChunk(
        val event: String = "",
        val data: String = "",
        val sessionId: String? = null,
        val done: Boolean = false
    )

    class NovaForgeApiException(val statusCode: Int, message: String) : RuntimeException(message)
}
