package com.novaforge.ai.search

import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogBuilder
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.speedSearch.ListWithSpeedSearch
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.client.NovaForgeApiClient
import com.novaforge.ai.settings.NovaForgeSettings
import java.awt.BorderLayout
import java.awt.Dimension
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import javax.swing.DefaultListModel
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JTextField
import javax.swing.SwingUtilities

class SearchAction : AnAction("Search Repository", "Search your repository using natural language", null) {

    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val client = NovaForgeApiClient()

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val settings = NovaForgeSettings.getInstance()
        val auth = AuthManager.getInstance()

        if (!auth.isAuthenticated() && settings.apiKey.isNullOrBlank()) {
            com.intellij.notification.NotificationGroupManager.getInstance()
                .getNotificationGroup("NovaForge")
                .createNotification("NovaForge AI", "Please login or configure an API key first.",
                    com.intellij.notification.NotificationType.WARNING)
                .notify(project)
            return
        }

        val dialog = SearchDialog(project)
        if (!dialog.showAndGet()) return

        val query = dialog.getQuery()
        if (query.isBlank()) return

        val orgId = auth.getOrganizationId() ?: settings.defaultOrganization
        val repoId = settings.defaultRepository

        executor.submit {
            try {
                val result = client.search(query, repoId, orgId, 20)
                val results = result.getAsJsonArray("results") ?: result.getAsJsonArray("items")
                if (results == null || results.size() == 0) {
                    SwingUtilities.invokeLater {
                        com.intellij.notification.NotificationGroupManager.getInstance()
                            .getNotificationGroup("NovaForge")
                            .createNotification("NovaForge Search", "No results found.",
                                com.intellij.notification.NotificationType.INFORMATION)
                            .notify(project)
                    }
                    return@submit
                }
                val entries = mutableListOf<SearchEntry>()
                for (i in 0 until results.size()) {
                    val item = results[i].asJsonObject
                    entries.add(SearchEntry(
                        file = item.get("file")?.asString ?: item.get("path")?.asString ?: "unknown",
                        line = item.get("line")?.asInt,
                        snippet = item.get("snippet")?.asString ?: item.get("content")?.asString ?: "",
                        score = item.get("score")?.asDouble ?: 0.0
                    ))
                }
                SwingUtilities.invokeLater {
                    showResults(project, entries)
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    com.intellij.notification.NotificationGroupManager.getInstance()
                        .getNotificationGroup("NovaForge")
                        .createNotification("NovaForge Search", "Search failed: ${e.message}",
                            com.intellij.notification.NotificationType.ERROR)
                        .notify(project)
                }
            }
        }
    }

    private fun showResults(project: Project, entries: List<SearchEntry>) {
        val model = DefaultListModel<SearchEntry>()
        entries.forEach { model.addElement(it) }
        val list = ListWithSpeedSearch(model)
        list.cellRenderer = SearchResultRenderer()

        val dialogBuilder = DialogBuilder(project)
        dialogBuilder.setTitle("NovaForge Search Results")
        dialogBuilder.setCenterPanel(JBScrollPane(list).also {
            it.preferredSize = Dimension(600, 400)
        })
        dialogBuilder.addOkAction()
        dialogBuilder.setCancelAction()

        list.addListSelectionListener {
            val selected = list.selectedValue
            if (selected != null) {
                openFile(project, selected)
            }
        }

        dialogBuilder.showModal(true)
    }

    private fun openFile(project: Project, entry: SearchEntry) {
        val basePath = project.basePath ?: return
        val filePath = "$basePath/${entry.file}"
        val virtualFile = LocalFileSystem.getInstance().findFileByPath(filePath)
        if (virtualFile != null) {
            val fileEditorManager = com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project)
            fileEditorManager.openFile(virtualFile, true)
            if (entry.line != null && entry.line > 0) {
                val editor = fileEditorManager.selectedTextEditor
                if (editor != null) {
                    val document = editor.document
                    if (entry.line <= document.lineCount) {
                        val offset = document.getLineStartOffset(entry.line - 1)
                        editor.caretModel.moveToOffset(offset)
                        editor.scrollingModel.scrollToCaret(com.intellij.openapi.editor.ScrollType.CENTER)
                    }
                }
            }
        }
    }

    data class SearchEntry(
        val file: String,
        val line: Int?,
        val snippet: String,
        val score: Double
    ) {
        override fun toString(): String {
            val lineStr = line?.let { ":$it" } ?: ""
            return "$file$lineStr - $snippet"
        }
    }

    class SearchDialog(project: Project) : DialogWrapper(project) {
        private val queryField = JTextField(40)

        init {
            title = "NovaForge Search"
            setOKButtonText("Search")
            init()
        }

        override fun createCenterPanel(): javax.swing.JComponent {
            val panel = JPanel(BorderLayout())
            panel.border = javax.swing.BorderFactory.createEmptyBorder(8, 8, 8, 8)
            panel.add(JLabel("Search query: "), BorderLayout.WEST)
            panel.add(queryField, BorderLayout.CENTER)
            queryField.addActionListener { close(OK_EXIT_CODE) }
            return panel
        }

        fun getQuery(): String = queryField.text.trim()
    }

    class SearchResultRenderer : javax.swing.DefaultListCellRenderer() {
        override fun getListCellRendererComponent(
            list: javax.swing.JList<*>, value: Any?, index: Int,
            isSelected: Boolean, cellHasFocus: Boolean
        ): java.awt.Component {
            val component = super.getListCellRendererComponent(list, value, index, isSelected, cellHasFocus)
            if (value is SearchEntry) {
                text = value.toString()
            }
            return component
        }
    }
}
