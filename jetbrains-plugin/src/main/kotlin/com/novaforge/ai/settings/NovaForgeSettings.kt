package com.novaforge.ai.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.components.service
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JLabel
import javax.swing.JTextField
import javax.swing.JCheckBox
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.awt.Insets

@State(
    name = "NovaForgeSettings",
    storages = [Storage("novaforge-settings.xml")]
)
class NovaForgeSettings : PersistentStateComponent<NovaForgeSettings.State> {

    data class State(
        var apiUrl: String = "https://api.novaforge.ai",
        var apiKey: String = "",
        var bearerToken: String = "",
        var defaultOrganization: String = "",
        var defaultRepository: String = "",
        var defaultModel: String = "gpt-4",
        var streamingEnabled: Boolean = true,
        var telemetryEnabled: Boolean = true,
        var reviewOnSave: Boolean = false,
        var autoExplainErrors: Boolean = false
    )

    private var myState = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    val apiUrl: String get() = myState.apiUrl
    val apiKey: String get() = myState.apiKey
    val bearerToken: String get() = myState.bearerToken
    val defaultOrganization: String get() = myState.defaultOrganization
    val defaultRepository: String get() = myState.defaultRepository
    val defaultModel: String get() = myState.defaultModel
    val streamingEnabled: Boolean get() = myState.streamingEnabled
    val telemetryEnabled: Boolean get() = myState.telemetryEnabled
    val reviewOnSave: Boolean get() = myState.reviewOnSave
    val autoExplainErrors: Boolean get() = myState.autoExplainErrors

    fun updateApiUrl(value: String) { myState.apiUrl = value }
    fun updateApiKey(value: String) { myState.apiKey = value }
    fun updateBearerToken(value: String) { myState.bearerToken = value }
    fun updateDefaultOrganization(value: String) { myState.defaultOrganization = value }
    fun updateDefaultRepository(value: String) { myState.defaultRepository = value }
    fun updateDefaultModel(value: String) { myState.defaultModel = value }
    fun updateStreamingEnabled(value: Boolean) { myState.streamingEnabled = value }
    fun updateTelemetryEnabled(value: Boolean) { myState.telemetryEnabled = value }
    fun updateReviewOnSave(value: Boolean) { myState.reviewOnSave = value }
    fun updateAutoExplainErrors(value: Boolean) { myState.autoExplainErrors = value }

    companion object {
        fun getInstance(): NovaForgeSettings = service()
    }
}

class NovaForgeConfigurable : Configurable {

    private var panel: NovaForgeSettingsPanel? = null

    override fun getDisplayName(): String = "NovaForge AI"

    override fun getHelpTopic(): String? = null

    override fun createComponent(): JComponent {
        panel = NovaForgeSettingsPanel()
        return panel!!.getComponent()
    }

    override fun isModified(): Boolean = panel?.isModified(NovaForgeSettings.getInstance()) ?: false

    override fun apply() {
        panel?.apply(NovaForgeSettings.getInstance())
    }

    override fun reset() {
        panel?.reset(NovaForgeSettings.getInstance())
    }

    override fun disposeUIResources() {
        panel = null
    }
}

class NovaForgeSettingsPanel {

    private val mainPanel = JPanel(GridBagLayout())
    private val apiUrlField = JTextField(40)
    private val apiKeyField = JTextField(40)
    private val orgField = JTextField(40)
    private val repoField = JTextField(40)
    private val modelField = JTextField(40)
    private val streamingCheckbox = JCheckBox("Enable streaming responses")
    private val telemetryCheckbox = JCheckBox("Enable anonymous telemetry")
    private val reviewOnSaveCheckbox = JCheckBox("Run code review on file save")
    private val autoExplainCheckbox = JCheckBox("Auto-explain errors")

    init {
        val gbc = GridBagConstraints()
        gbc.insets = Insets(4, 8, 4, 8)
        gbc.anchor = GridBagConstraints.WEST
        gbc.fill = GridBagConstraints.HORIZONTAL

        var row = 0

        addLabel("API URL:", row, gbc)
        addField(apiUrlField, row, 1, gbc); row++

        addLabel("API Key:", row, gbc)
        addField(apiKeyField, row, 1, gbc); row++

        addLabel("Default Organization:", row, gbc)
        addField(orgField, row, 1, gbc); row++

        addLabel("Default Repository:", row, gbc)
        addField(repoField, row, 1, gbc); row++

        addLabel("Default Model:", row, gbc)
        addField(modelField, row, 1, gbc); row++

        gbc.gridx = 0
        gbc.gridy = row
        gbc.gridwidth = 2
        mainPanel.add(streamingCheckbox, gbc); row++

        gbc.gridy = row
        mainPanel.add(telemetryCheckbox, gbc); row++

        gbc.gridy = row
        mainPanel.add(reviewOnSaveCheckbox, gbc); row++

        gbc.gridy = row
        mainPanel.add(autoExplainCheckbox, gbc)
    }

    private fun addLabel(text: String, row: Int, gbc: GridBagConstraints) {
        gbc.gridx = 0
        gbc.gridy = row
        gbc.gridwidth = 1
        gbc.weightx = 0.0
        mainPanel.add(JLabel(text), gbc)
    }

    private fun addField(field: JTextField, row: Int, col: Int, gbc: GridBagConstraints) {
        gbc.gridx = col
        gbc.gridy = row
        gbc.gridwidth = 1
        gbc.weightx = 1.0
        mainPanel.add(field, gbc)
    }

    fun getComponent(): JComponent = mainPanel

    fun isModified(settings: NovaForgeSettings): Boolean {
        return apiUrlField.text != settings.apiUrl ||
                apiKeyField.text != settings.apiKey ||
                orgField.text != settings.defaultOrganization ||
                repoField.text != settings.defaultRepository ||
                modelField.text != settings.defaultModel ||
                streamingCheckbox.isSelected != settings.streamingEnabled ||
                telemetryCheckbox.isSelected != settings.telemetryEnabled ||
                reviewOnSaveCheckbox.isSelected != settings.reviewOnSave ||
                autoExplainCheckbox.isSelected != settings.autoExplainErrors
    }

    fun apply(settings: NovaForgeSettings) {
        settings.updateApiUrl(apiUrlField.text.trim())
        settings.updateApiKey(apiKeyField.text.trim())
        settings.updateDefaultOrganization(orgField.text.trim())
        settings.updateDefaultRepository(repoField.text.trim())
        settings.updateDefaultModel(modelField.text.trim())
        settings.updateStreamingEnabled(streamingCheckbox.isSelected)
        settings.updateTelemetryEnabled(telemetryCheckbox.isSelected)
        settings.updateReviewOnSave(reviewOnSaveCheckbox.isSelected)
        settings.updateAutoExplainErrors(autoExplainCheckbox.isSelected)
    }

    fun reset(settings: NovaForgeSettings) {
        apiUrlField.text = settings.apiUrl
        apiKeyField.text = settings.apiKey
        orgField.text = settings.defaultOrganization
        repoField.text = settings.defaultRepository
        modelField.text = settings.defaultModel
        streamingCheckbox.isSelected = settings.streamingEnabled
        telemetryCheckbox.isSelected = settings.telemetryEnabled
        reviewOnSaveCheckbox.isSelected = settings.reviewOnSave
        autoExplainCheckbox.isSelected = settings.autoExplainErrors
    }
}
