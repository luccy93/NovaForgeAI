package com.novaforge.ai.toolwindow

import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.novaforge.ai.auth.AuthManager

class NovaForgeToolWindowFactory : ToolWindowFactory, DumbAware {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = NovaForgeToolWindowPanel(project)
        val content = ContentFactory.getInstance().createContent(panel.getComponent(), "Chat", false)
        toolWindow.contentManager.addContent(content)
    }

    override fun isDumbAware(): Boolean = true
}
