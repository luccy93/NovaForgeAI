package com.novaforge.ai.toolwindow

import com.intellij.openapi.Disposable
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.testFramework.LightVirtualFile
import com.intellij.ui.EditorTextField
import com.intellij.ui.JBColor
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.ui.JBUI
import com.novaforge.ai.auth.AuthManager
import com.novaforge.ai.client.NovaForgeApiClient
import com.novaforge.ai.settings.NovaForgeSettings
import java.awt.BorderLayout
import java.awt.Color
import java.awt.Dimension
import java.awt.Font
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.awt.Insets
import java.awt.event.ActionEvent
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import javax.swing.*
import javax.swing.text.AttributeSet
import javax.swing.text.BadLocationException
import javax.swing.text.SimpleAttributeSet
import javax.swing.text.StyleConstants
import javax.swing.text.StyledDocument

class NovaForgeToolWindowPanel(private val project: Project) : Disposable {

    private val mainPanel = JPanel(BorderLayout())
    private val chatPane = JTextPane()
    private val inputField = JTextField()
    private val sendButton = JButton("Send")
    private val statusLabel = JLabel("Not connected")
    private val orgLabel = JLabel("Organization: --")
    private val sessionLabel = JLabel("Session: --")
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private val client = NovaForgeApiClient()
    private var currentSessionId: String? = null

    init {
        setupUI()
    }

    private fun setupUI() {
        val topPanel = JPanel(BorderLayout())
        topPanel.border = JBUI.Borders.empty(8)

        val infoPanel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints()
        gbc.anchor = GridBagConstraints.WEST
        gbc.insets = Insets(0, 4, 0, 4)

        gbc.gridx = 0
        gbc.gridy = 0
        statusLabel.foreground = JBColor.RED
        statusLabel.font = statusLabel.font.deriveFont(Font.BOLD)
        infoPanel.add(statusLabel, gbc)

        gbc.gridx = 1
        infoPanel.add(orgLabel, gbc)

        gbc.gridx = 2
        infoPanel.add(sessionLabel, gbc)

        topPanel.add(infoPanel, BorderLayout.NORTH)

        chatPane.isEditable = false
        chatPane.font = Font(Font.MONOSPACED, Font.PLAIN, 13)
        chatPane.border = JBUI.Borders.empty(8)
        val scrollPane = JBScrollPane(chatPane)
        scrollPane.preferredSize = Dimension(0, 400)

        val inputPanel = JPanel(BorderLayout())
        inputPanel.border = JBUI.Borders.empty(8)

        inputField.font = Font(Font.MONOSPACED, Font.PLAIN, 13)
        inputField.addKeyListener(object : KeyAdapter() {
            override fun keyPressed(e: KeyEvent) {
                if (e.keyChar == '\n' && !e.isShiftDown) {
                    e.consume()
                    sendMessage()
                }
            }
        })

        sendButton.addActionListener { _: ActionEvent -> sendMessage() }

        inputPanel.add(inputField, BorderLayout.CENTER)
        inputPanel.add(sendButton, BorderLayout.EAST)

        mainPanel.add(topPanel, BorderLayout.NORTH)
        mainPanel.add(scrollPane, BorderLayout.CENTER)
        mainPanel.add(inputPanel, BorderLayout.SOUTH)

        refreshStatus()
        appendSystemMessage("Welcome to NovaForge AI. Type a message to start chatting.")
    }

    fun getComponent(): JComponent = mainPanel

    private fun sendMessage() {
        val text = inputField.text.trim()
        if (text.isEmpty()) return

        val settings = NovaForgeSettings.getInstance()
        val auth = AuthManager.getInstance()

        if (!auth.isAuthenticated() && settings.apiKey.isNullOrBlank()) {
            appendSystemMessage("Please login or configure an API key first.")
            return
        }

        inputField.text = ""
        appendUserMessage(text)

        val model = settings.defaultModel
        val orgId = auth.getOrganizationId() ?: settings.defaultOrganization

        executor.submit {
            try {
                val result = client.chat(
                    sessionId = currentSessionId,
                    message = text,
                    model = model,
                    organizationId = orgId,
                    repositoryId = settings.defaultRepository,
                    context = null
                )
                currentSessionId = result.get("session_id")?.asString ?: currentSessionId
                val response = result.get("response")?.asString
                    ?: result.get("message")?.asString ?: ""
                SwingUtilities.invokeLater {
                    sessionLabel.text = "Session: ${currentSessionId ?: "--"}"
                    appendAssistantMessage(response)
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    appendErrorMessage("Error: ${e.message}")
                }
            }
        }
    }

    fun refreshStatus() {
        val auth = AuthManager.getInstance()
        if (auth.isAuthenticated()) {
            statusLabel.text = "Connected"
            statusLabel.foreground = JBColor.GREEN.darker()
            orgLabel.text = "Organization: ${auth.getOrganizationName() ?: "Default"}"
        } else {
            val settings = NovaForgeSettings.getInstance()
            if (!settings.apiKey.isNullOrBlank()) {
                statusLabel.text = "API Key configured"
                statusLabel.foreground = JBColor.YELLOW.darker()
            } else {
                statusLabel.text = "Not connected"
                statusLabel.foreground = JBColor.RED
            }
            orgLabel.text = "Organization: --"
        }
    }

    fun appendUserMessage(text: String) {
        val timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
        val doc: StyledDocument = chatPane.styledDocument
        val attrs = SimpleAttributeSet()
        StyleConstants.setForeground(attrs, JBColor(Color(0.2f, 0.4f, 0.8f), Color(0.5f, 0.6f, 0.9f)))
        StyleConstants.setBold(attrs, true)
        doc.insertString(doc.length, "You ($timestamp): ", attrs)
        val bodyAttrs = SimpleAttributeSet()
        StyleConstants.setForeground(bodyAttrs, JBColor.foreground())
        doc.insertString(doc.length, "$text\n\n", bodyAttrs)
        chatPane.caretPosition = doc.length
    }

    fun appendAssistantMessage(text: String) {
        val timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
        val doc: StyledDocument = chatPane.styledDocument
        val attrs = SimpleAttributeSet()
        StyleConstants.setForeground(attrs, JBColor(Color(0.1f, 0.6f, 0.3f), Color(0.4f, 0.8f, 0.5f)))
        StyleConstants.setBold(attrs, true)
        doc.insertString(doc.length, "NovaForge ($timestamp): ", attrs)
        val bodyAttrs = SimpleAttributeSet()
        StyleConstants.setForeground(bodyAttrs, JBColor.foreground())
        doc.insertString(doc.length, "$text\n\n", bodyAttrs)
        chatPane.caretPosition = doc.length
    }

    fun appendSystemMessage(text: String) {
        val doc: StyledDocument = chatPane.styledDocument
        val attrs = SimpleAttributeSet()
        StyleConstants.setForeground(attrs, JBColor.GRAY.darker())
        StyleConstants.setItalic(attrs, true)
        doc.insertString(doc.length, "System: $text\n\n", attrs)
        chatPane.caretPosition = doc.length
    }

    fun appendErrorMessage(text: String) {
        val doc: StyledDocument = chatPane.styledDocument
        val attrs = SimpleAttributeSet()
        StyleConstants.setForeground(attrs, JBColor.RED.darker())
        doc.insertString(doc.length, "Error: $text\n\n", attrs)
        chatPane.caretPosition = doc.length
    }

    fun clearChat() {
        chatPane.text = ""
        currentSessionId = null
        appendSystemMessage("Chat cleared.")
    }

    fun getSessionId(): String? = currentSessionId

    override fun dispose() {
        executor.shutdownNow()
    }
}
