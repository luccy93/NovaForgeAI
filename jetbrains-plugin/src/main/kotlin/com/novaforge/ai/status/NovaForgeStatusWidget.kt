package com.novaforge.ai.status

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.StatusBarWidget
import com.intellij.openapi.wm.StatusBarWidgetFactory
import com.intellij.openapi.wm.WindowManager
import com.intellij.openapi.wm.StatusBar
import com.intellij.util.concurrency.AppExecutorUtil
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.settings.NovaForgeSettings
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import java.util.concurrent.TimeUnit
import javax.swing.Icon
import javax.swing.SwingUtilities

class NovaForgeStatusWidgetFactory : StatusBarWidgetFactory {

    override fun getId(): String = "NovaForgeStatusWidget"

    override fun getDisplayName(): String = "NovaForge AI"

    override fun isAvailable(project: Project): Boolean = true

    override fun createWidget(project: Project): StatusBarWidget {
        return NovaForgeStatusWidget(project)
    }

    override fun canBeEnabledOn(statusBar: StatusBar): Boolean = true
}

class NovaForgeStatusWidget(private val project: Project) : StatusBarWidget,
    StatusBarWidget.TextPresentation {

    companion object {
        private const val ID = "NovaForgeStatusWidget"
        private val CHECK_INTERVAL = 30L
    }

    private var statusBar: StatusBar? = null
    private val scheduler = AppExecutorUtil.getAppScheduledExecutorService()

    init {
        scheduler.scheduleWithFixedDelay({
            SwingUtilities.invokeLater { updateWidget() }
        }, 0, CHECK_INTERVAL, TimeUnit.SECONDS)
    }

    override fun ID(): String = ID

    override fun getPresentation(): StatusBarWidget.WidgetPresentation = this

    override fun install(statusBar: StatusBar) {
        this.statusBar = statusBar
    }

    override fun getText(): String {
        val auth = AuthManager.getInstance()
        val settings = NovaForgeSettings.getInstance()
        return when {
            auth.isAuthenticated() -> {
                val org = auth.getOrganizationName() ?: settings.defaultOrganization ?: ""
                if (org.isNotBlank()) "NovaForge: $org" else "NovaForge: connected"
            }
            !settings.apiKey.isNullOrBlank() -> "NovaForge: API key"
            else -> "NovaForge: offline"
        }
    }

    override fun getTooltipText(): String {
        val auth = AuthManager.getInstance()
        val settings = NovaForgeSettings.getInstance()
        return buildString {
            appendLine("NovaForge AI")
            appendLine("Status: ${if (auth.isAuthenticated()) "Connected" else "Offline"}")
            if (auth.isAuthenticated()) {
                appendLine("Email: ${auth.getEmail() ?: "unknown"}")
                appendLine("Organization: ${auth.getOrganizationName() ?: "Default"}")
            }
            if (!settings.apiKey.isNullOrBlank()) {
                appendLine("API Key: configured")
            }
            appendLine("API URL: ${settings.apiUrl}")
            appendLine("Click to open NovaForge panel")
        }
    }

    override fun getAlignment(): Float = 0.0f

    override fun getClickConsumer(): java.util.function.Consumer<MouseEvent>? {
        return java.util.function.Consumer { event ->
            val toolWindow = com.intellij.openapi.wm.ToolWindowManager.getInstance(project)
                .getToolWindow("NovaForge")
            if (toolWindow != null) {
                toolWindow.show()
            } else {
                com.intellij.notification.NotificationGroupManager.getInstance()
                    .getNotificationGroup("NovaForge")
                    .createNotification("NovaForge AI", "Tool window not available",
                        com.intellij.notification.NotificationType.WARNING)
                    .notify(project)
            }
        }
    }

    private fun updateWidget() {
        statusBar?.updateWidget(ID)
    }

    override fun dispose() {
        statusBar = null
    }
}
