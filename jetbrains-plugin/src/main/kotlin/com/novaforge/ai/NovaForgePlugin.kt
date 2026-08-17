package com.novaforge.ai

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.telemetry.TelemetryService

class NovaForgeStartupActivity : ProjectActivity {
    override suspend fun execute(project: Project) {
        val plugin = NovaForgePlugin.getInstance()
        plugin.onProjectOpened(project)
    }
}

@State(
    name = "NovaForgePlugin",
    storages = [Storage("novaforge-plugin.xml")]
)
class NovaForgePlugin : PersistentStateComponent<NovaForgePlugin.State> {

    data class State(
        var initialized: Boolean = false,
        var lastStartup: Long = 0L,
        var totalCommands: Int = 0,
        var totalErrors: Int = 0
    )

    private var myState = State()
    private val logger = Logger.getInstance(NovaForgePlugin::class.java)

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    fun onProjectOpened(project: Project) {
        if (!myState.initialized) {
            initialize()
        }
        myState.lastStartup = System.currentTimeMillis()

        val telemetry = ApplicationManager.getApplication().getService(TelemetryService::class.java)
        telemetry?.trackSessionStart()
        logger.info("NovaForge AI plugin initialized for project: ${project.name}")
    }

    private fun initialize() {
        logger.info("NovaForge AI plugin initializing...")
        myState.initialized = true
    }

    fun onShutdown() {
        logger.info("NovaForge AI plugin shutting down...")
        val telemetry = ApplicationManager.getApplication().getService(TelemetryService::class.java)
        telemetry?.trackSessionEnd()
        telemetry?.shutdown()
    }

    fun incrementCommandCount() {
        myState.totalCommands++
    }

    fun incrementErrorCount() {
        myState.totalErrors++
    }

    companion object {
        fun getInstance(): NovaForgePlugin = service()

        private val LOG = Logger.getInstance(NovaForgePlugin::class.java)
    }
}
