package com.novaforge.ai.actions

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindowManager
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.toolwindow.NovaForgeToolWindowPanel

class LoginAction : AnAction("Login", "Login to NovaForge", null) {

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project
        val component = event.inputEvent?.component
        AuthManager.getInstance().login(component)
        if (project != null) {
            refreshToolWindow(project)
        }
    }

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = !AuthManager.getInstance().isAuthenticated()
    }

    private fun refreshToolWindow(project: Project) {
        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("NovaForge") ?: return
        val panel = toolWindow.contentManager.getContent(0)?.component as? NovaForgeToolWindowPanel
        panel?.refreshStatus()
    }
}

class LogoutAction : AnAction("Logout", "Logout from NovaForge", null) {

    override fun actionPerformed(event: AnActionEvent) {
        AuthManager.getInstance().logout()
        val project = event.project ?: return
        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("NovaForge") ?: return
        val panel = toolWindow.contentManager.getContent(0)?.component as? NovaForgeToolWindowPanel
        panel?.refreshStatus()
        panel?.appendSystemMessage("Logged out from NovaForge.")
    }

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = AuthManager.getInstance().isAuthenticated()
    }
}

class StatusAction : AnAction("Status", "Check NovaForge connection status", null) {

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val auth = AuthManager.getInstance()
        val status = if (auth.isAuthenticated()) {
            "Connected as ${auth.getEmail() ?: "unknown"}\nOrganization: ${auth.getOrganizationName() ?: "Default"}"
        } else {
            "Not authenticated"
        }
        NotificationGroupManager.getInstance()
            .getNotificationGroup("NovaForge")
            .createNotification("NovaForge Status", status, NotificationType.INFORMATION)
            .notify(project)
    }
}

class SettingsAction : AnAction("Settings", "Open NovaForge settings", null) {

    override fun actionPerformed(event: AnActionEvent) {
        com.intellij.openapi.options.ShowSettingsUtil.getInstance()
            .showSettingsDialog(event.project, "NovaForge AI")
    }
}

class OpenDashboardAction : AnAction("Open Dashboard", "Open NovaForge dashboard in browser", null) {

    override fun actionPerformed(event: AnActionEvent) {
        val settings = com.novaforge.ai.settings.NovaForgeSettings.getInstance()
        val url = settings.apiUrl.trimEnd('/').replace("/api", "") + "/dashboard"
        com.intellij.ide.BrowserUtil.browse(url)
    }
}

class RunAgentAction : AnAction("Run Agent", "Run an autonomous AI agent", null) {

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("NovaForge")
        toolWindow?.show()
        val panel = toolWindow?.contentManager?.getContent(0)?.component as? NovaForgeToolWindowPanel
        panel?.appendSystemMessage("Enter the agent prompt in the chat. Use /agent <type> <prompt> to run an agent.")
    }
}
