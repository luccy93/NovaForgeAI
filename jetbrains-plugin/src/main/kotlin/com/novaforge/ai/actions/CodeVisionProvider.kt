package com.novaforge.ai.actions

import com.intellij.codeInsight.daemon.NavigateAction
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.editor.actionSystem.ActionUpdateThread
import com.intellij.openapi.editor.actionSystem.EditorActionHandler
import com.intellij.openapi.editor.actionSystem.EditorActionHandlerBean
import com.intellij.openapi.editor.actions.EditorActionUtil
import com.intellij.openapi.project.DumbAwareAction
import com.intellij.util.concurrency.AppExecutorUtil
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.client.NovaForgeApiClient
import com.novaforge.ai.context.ContextCollector
import com.novaforge.ai.settings.NovaForgeSettings
import com.novaforge.ai.toolwindow.NovaForgeToolWindowPanel
import javax.swing.Icon
import javax.swing.SwingUtilities

class NovaForgeCodeActionProvider : com.intellij.codeInsight.codeVision.CodeVisionProvider {

    override val defaultAnchor: com.intellij.codeInsight.codeVision.CodeVisionAnchor
        get() = com.intellij.codeInsight.codeVision.CodeVisionAnchor.Default

    override val groupId: String = "NovaForgeAI"

    override val name: String = "NovaForge AI Code Vision"

    override val relativeOrdering: List<com.intellij.codeInsight.codeVision.CodeVisionRelativeOrdering>
        get() = emptyList()

    override fun computeCodeVision(editor: Editor, virtualFile: com.intellij.openapi.vfs.VirtualFile?): com.intellij.codeInsight.codeVision.CodeVisionState {
        return com.intellij.codeInsight.codeVision.CodeVisionState.Visible(
            emptyList(),
            com.intellij.codeInsight.codeVision.CodeVisionState.DefaultAuxContent
        )
    }
}

class NovaForgeExplainHandler : EditorActionHandler() {
    private val client = NovaForgeApiClient()

    override fun doExecute(editor: Editor, caretOffset: Int, dataContext: com.intellij.openapi.actionSystem.DataContext?) {
        val project = com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.getData(dataContext) ?: return
        val document = editor.document
        val selectionModel = editor.selectionModel

        val code = if (selectionModel.hasSelection()) {
            selectionModel.selectedText ?: ""
        } else {
            val start = maxOf(0, caretOffset - 500)
            val end = minOf(document.textLength, caretOffset + 500)
            document.getText(com.intellij.openapi.util.TextRange(start, end))
        }

        if (code.isBlank()) return

        val settings = NovaForgeSettings.getInstance()
        val auth = AuthManager.getInstance()

        val toolWindow = com.intellij.openapi.wm.ToolWindowManager.getInstance(project).getToolWindow("NovaForge")
        val panel = toolWindow?.contentManager?.getContent(0)?.component as? NovaForgeToolWindowPanel

        panel?.appendSystemMessage("Explaining code...")

        AppExecutorUtil.getAppExecutorService().submit {
            try {
                val psiFile = com.intellij.psi.PsiManager.getInstance(project).findFile(
                    com.intellij.openapi.fileEditor.FileDocumentManager.getInstance().getFile(document) ?: return@submit
                )
                val context = ContextCollector.collectContext(project, editor, psiFile)
                val language = psiFile?.language?.id ?: "Unknown"
                val result = client.codeAction(
                    action = "explain",
                    code = code,
                    language = language,
                    filePath = editor.virtualFile?.path,
                    lineStart = if (selectionModel.hasSelection())
                        document.getLineNumber(selectionModel.selectionStart) + 1 else null,
                    lineEnd = if (selectionModel.hasSelection())
                        document.getLineNumber(selectionModel.selectionEnd) + 1 else null,
                    model = settings.defaultModel,
                    context = context
                )
                val response = result.get("response")?.asString
                    ?: result.get("result")?.asString
                    ?: result.toString()
                SwingUtilities.invokeLater {
                    panel?.appendAssistantMessage("Explanation:\n$response")
                    toolWindow?.show()
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    panel?.appendErrorMessage("Explain failed: ${e.message}")
                }
            }
        }
    }
}
