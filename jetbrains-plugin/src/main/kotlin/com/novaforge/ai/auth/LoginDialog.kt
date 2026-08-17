package com.novaforge.ai.auth

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.ValidationInfo
import java.awt.BorderLayout
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.awt.Insets
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.JPasswordField
import javax.swing.JTextField

class LoginDialog(parent: JComponent?) : DialogWrapper(parent) {

    val email: String get() = emailField.text.trim()
    val password: String get() = String(passwordField.password)

    private val emailField = JTextField(30)
    private val passwordField = JPasswordField(30)

    init {
        title = "NovaForge AI Login"
        setOKButtonText("Login")
        init()
    }

    override fun createCenterPanel(): JComponent {
        val panel = JPanel(GridBagLayout())
        val gbc = GridBagConstraints()
        gbc.insets = Insets(4, 4, 4, 4)
        gbc.anchor = GridBagConstraints.WEST

        gbc.gridx = 0
        gbc.gridy = 0
        panel.add(JLabel("Email:"), gbc)
        gbc.gridx = 1
        gbc.fill = GridBagConstraints.HORIZONTAL
        panel.add(emailField, gbc)

        gbc.gridx = 0
        gbc.gridy = 1
        gbc.fill = GridBagConstraints.NONE
        panel.add(JLabel("Password:"), gbc)
        gbc.gridx = 1
        gbc.fill = GridBagConstraints.HORIZONTAL
        panel.add(passwordField, gbc)

        return panel
    }

    override fun doValidate(): ValidationInfo? {
        if (email.isBlank()) {
            return ValidationInfo("Email is required", emailField)
        }
        if (!email.contains("@")) {
            return ValidationInfo("Invalid email address", emailField)
        }
        if (password.isEmpty()) {
            return ValidationInfo("Password is required", passwordField)
        }
        return null
    }
}
