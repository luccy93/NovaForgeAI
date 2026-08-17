package com.novaforge.ai.toolwindow

import com.intellij.openapi.project.Project

class NovaForgeToolWindowCondition : com.intellij.openapi.util.Condition<Project> {
    override fun value(project: Project): Boolean = true
}
