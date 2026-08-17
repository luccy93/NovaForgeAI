package com.novaforge.ai.actions

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindowManager
import com.novaforge.ai.toolwindow.NovaForgeToolWindowPanel

class ChatAction : AnAction("Chat with NovaForge", "Open NovaForge AI chat panel", null) {

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("NovaForge")
        if (toolWindow != null) {
            toolWindow.show()
            val content = toolWindow.contentManager.getContent(0)
            val panel = content?.component as? NovaForgeToolWindowPanel
            panel?.refreshStatus()
        }
    }

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = event.project != null
    }
}
