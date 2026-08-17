package com.novaforge.ai.actions

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindowManager
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.client.NovaForgeApiClient
import com.novaforge.ai.context.ContextCollector
import com.novaforge.ai.settings.NovaForgeSettings
import com.novaforge.ai.toolwindow.NovaForgeToolWindowPanel
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import javax.swing.SwingUtilities

abstract class BaseCodeAction(text: String, description: String) : AnAction(text, description, null) {

    protected val executor: ExecutorService = Executors.newSingleThreadExecutor()
    protected val client = NovaForgeApiClient()

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val editor = event.getData(CommonDataKeys.EDITOR) ?: return
        val document = editor.document
        val selectionModel = editor.selectionModel

        val code = if (selectionModel.hasSelection()) {
            selectionModel.selectedText ?: ""
        } else {
            document.text
        }

        if (code.isBlank()) {
            showNotification(project, "No code selected or file is empty.", NotificationType.WARNING)
            return
        }

        val settings = NovaForgeSettings.getInstance()
        val auth = AuthManager.getInstance()

        if (!auth.isAuthenticated() && settings.apiKey.isNullOrBlank()) {
            showNotification(project, "Please login or configure an API key first.", NotificationType.WARNING)
            return
        }

        val psiFile = event.getData(CommonDataKeys.PSI_FILE)
        val language = psiFile?.language?.id ?: "Unknown"
        val filePath = event.getData(CommonDataKeys.VIRTUAL_FILE)?.path
        val lineStart = if (selectionModel.hasSelection())
            document.getLineNumber(selectionModel.selectionStart) + 1 else null
        val lineEnd = if (selectionModel.hasSelection())
            document.getLineNumber(selectionModel.selectionEnd) + 1 else null

        val toolWindow = ToolWindowManager.getInstance(project).getToolWindow("NovaForge")
        val panel = toolWindow?.contentManager?.getContent(0)?.component as? NovaForgeToolWindowPanel

        val actionName = getActionName()
        panel?.appendSystemMessage("Running $actionName...")

        executor.submit {
            try {
                val context = ContextCollector.collectContext(project, editor, psiFile)
                val result = client.codeAction(
                    action = actionName.lowercase(),
                    code = code,
                    language = language,
                    filePath = filePath,
                    lineStart = lineStart,
                    lineEnd = lineEnd,
                    model = settings.defaultModel,
                    context = context
                )
                val response = result.get("response")?.asString
                    ?: result.get("result")?.asString
                    ?: result.toString()
                SwingUtilities.invokeLater {
                    panel?.appendAssistantMessage("$actionName:\n$response")
                    toolWindow?.show()
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    panel?.appendErrorMessage("$actionName failed: ${e.message}")
                }
            }
        }
    }

    protected abstract fun getActionName(): String

    protected fun showNotification(project: Project, content: String, type: NotificationType) {
        NotificationGroupManager.getInstance()
            .getNotificationGroup("NovaForge")
            .createNotification("NovaForge AI", content, type)
            .notify(project)
    }
}

class ExplainAction : BaseCodeAction("Explain Code", "Explain the selected code using AI") {
    override fun getActionName(): String = "Explain"
}

class FixAction : BaseCodeAction("Fix Code", "Fix bugs in the selected code using AI") {
    override fun getActionName(): String = "Fix"
}

class RefactorAction : BaseCodeAction("Refactor Code", "Refactor the selected code using AI") {
    override fun getActionName(): String = "Refactor"
}

class GenerateTestsAction : BaseCodeAction("Generate Tests", "Generate unit tests for the selected code") {
    override fun getActionName(): String = "Generate Tests"
}

class GenerateDocsAction : BaseCodeAction("Generate Docs", "Generate documentation for the selected code") {
    override fun getActionName(): String = "Generate Docs"
}

class SecurityReviewAction : BaseCodeAction("Security Scan", "Scan selected code for security vulnerabilities") {
    override fun getActionName(): String = "Security Scan"
}

class ReviewAction : BaseCodeAction("Review Code", "AI-powered code review") {
    override fun getActionName(): String = "Review"
}
