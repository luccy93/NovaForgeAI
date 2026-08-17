package com.novaforge.ai.auth

import com.intellij.credentialStore.Credentials
import com.intellij.credentialStore.generateServiceName
import com.intellij.ide.PasswordSafe
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.components.service
import com.novaforge.ai.client.NovaForgeApiClient
import com.novaforge.ai.settings.NovaForgeSettings
import javax.swing.SwingUtilities

@State(
    name = "NovaForgeAuth",
    storages = [Storage("novaforge-auth.xml")]
)
class AuthManager : PersistentStateComponent<AuthManager.State> {

    data class State(
        var token: String? = null,
        var refreshToken: String? = null,
        var expiresAt: Long = 0L,
        var email: String? = null,
        var organizationId: String? = null,
        var organizationName: String? = null
    )

    private var myState = State()

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    fun getToken(): String? {
        if (myState.token != null && isTokenExpired()) {
            val refreshed = refreshToken()
            if (!refreshed) {
                return null
            }
        }
        return myState.token
    }

    fun storeToken(authResult: NovaForgeApiClient.AuthResult, email: String) {
        myState.token = authResult.token
        myState.refreshToken = authResult.refreshToken
        myState.expiresAt = authResult.expiresAt
        myState.email = email
        storePassword(authResult.token)
    }

    fun clearTokens() {
        myState.token = null
        myState.refreshToken = null
        myState.expiresAt = 0L
        myState.email = null
        myState.organizationId = null
        myState.organizationName = null
        clearPassword()
    }

    fun isAuthenticated(): Boolean {
        return !myState.token.isNullOrBlank() && !isTokenExpired()
    }

    fun getEmail(): String? = myState.email

    fun getOrganizationId(): String? = myState.organizationId

    fun getOrganizationName(): String? = myState.organizationName

    fun setOrganization(id: String, name: String) {
        myState.organizationId = id
        myState.organizationName = name
    }

    fun login(parentComponent: java.awt.Component? = null) {
        val settings = NovaForgeSettings.getInstance()
        val apiUrl = settings.apiUrl
        if (apiUrl.isNullOrBlank()) {
            showNotification(
                "Please configure the NovaForge API URL in Settings first.",
                NotificationType.WARNING
            )
            openSettings()
            return
        }

        val dialog = LoginDialog(parentComponent)
        if (!dialog.showAndGet()) return

        val email = dialog.email
        val password = dialog.password

        if (email.isNullOrBlank() || password.isNullOrBlank()) {
            showNotification("Email and password are required.", NotificationType.WARNING)
            return
        }

        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val client = NovaForgeApiClient()
                val authResult = client.login(apiUrl, email, password)
                storeToken(authResult, email)
                SwingUtilities.invokeLater {
                    showNotification("Successfully logged in as $email", NotificationType.INFORMATION)
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    showNotification("Login failed: ${e.message}", NotificationType.ERROR)
                }
            }
        }
    }

    fun logout() {
        clearTokens()
        showNotification("Logged out from NovaForge.", NotificationType.INFORMATION)
    }

    fun refreshToken(): Boolean {
        val refreshToken = myState.refreshToken
        if (refreshToken.isNullOrBlank()) return false
        return try {
            val settings = NovaForgeSettings.getInstance()
            val apiUrl = settings.apiUrl
            if (apiUrl.isNullOrBlank()) return false
            val client = NovaForgeApiClient()
            val json = client.post("/auth/refresh", mapOf("refresh_token" to refreshToken))
            val newToken = json.get("token").asString
            val newRefresh = json.get("refresh_token")?.asString ?: refreshToken
            val expiresAt = json.get("expires_at")?.asLong ?: 0L
            myState.token = newToken
            myState.refreshToken = newRefresh
            myState.expiresAt = expiresAt
            storePassword(newToken)
            true
        } catch (e: Exception) {
            clearTokens()
            false
        }
    }

    private fun isTokenExpired(): Boolean {
        if (myState.expiresAt <= 0) return false
        return System.currentTimeMillis() >= myState.expiresAt
    }

    private fun storePassword(token: String) {
        val serviceName = generateServiceName("NovaForge AI", "auth-token")
        val credentials = Credentials("novaforge", token)
        PasswordSafe.instance.set(serviceName, credentials)
    }

    private fun clearPassword() {
        val serviceName = generateServiceName("NovaForge AI", "auth-token")
        PasswordSafe.instance.set(serviceName, null)
    }

    private fun openSettings() {
        com.intellij.openapi.options.ShowSettingsUtil.getInstance()
            .showSettingsDialog(null, NovaForgeSettings::class.java)
    }

    companion object {
        fun getInstance(): AuthManager = service()

        private fun showNotification(content: String, type: NotificationType) {
            NotificationGroupManager.getInstance()
                .getNotificationGroup("NovaForge")
                .createNotification("NovaForge AI", content, type)
                .notify(null)
        }
    }
}
