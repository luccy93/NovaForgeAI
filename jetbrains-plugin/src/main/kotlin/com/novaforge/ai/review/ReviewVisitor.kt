package com.novaforge.ai.review

import com.intellij.codeInspection.*
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiJavaFile
import com.novaforge.ai.client.NovaForgeApiClient
import com.novaforge.ai.settings.NovaForgeSettings
import com.novaforge.ai.auth.AuthManager
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.util.concurrent.atomic.AtomicBoolean

class NovaForgeReviewInspection : LocalInspectionTool() {

    private val client = NovaForgeApiClient()
    private val reviewing = AtomicBoolean(false)

    override fun getGroupDisplayName(): String = "Code style"

    override fun getShortName(): String = "NovaForgeReview"

    override fun isEnabledByDefault(): Boolean = false

    override fun buildVisitor(
        holder: ProblemsHolder,
        isOnTheFly: Boolean
    ): PsiElementVisitor {
        return object : PsiElementVisitor() {
            override fun visitElement(element: com.intellij.psi.PsiElement) {
                // We only inspect at the file level
            }
        }
    }

    override fun checkFile(file: PsiFile, manager: InspectionManager, isOnTheFly: Boolean): Array<ProblemDescriptor>? {
        val settings = NovaForgeSettings.getInstance()
        val auth = AuthManager.getInstance()

        if (!auth.isAuthenticated() && settings.apiKey.isNullOrBlank()) return null
        if (!settings.reviewOnSave) return null
        if (!reviewing.compareAndSet(false, true)) return null

        try {
            val language = file.language.id
            val code = file.text
            if (code.isBlank()) return null

            val filePath = file.virtualFile?.path ?: file.name
            val result = client.review(
                code = code,
                language = language,
                filePath = filePath,
                organizationId = auth.getOrganizationId() ?: settings.defaultOrganization,
                repositoryId = settings.defaultRepository
            )

            val findings = result.getAsJsonArray("findings")
                ?: result.getAsJsonArray("issues")
                ?: result.getAsJsonArray("results")
                ?: return null

            val problems = mutableListOf<ProblemDescriptor>()

            for (i in 0 until findings.size()) {
                val finding = findings[i].asJsonObject
                val line = finding.get("line")?.asInt ?: finding.get("start_line")?.asInt ?: continue
                val severity = finding.get("severity")?.asString ?: "warning"
                val message = finding.get("message")?.asString
                    ?: finding.get("description")?.asString
                    ?: finding.get("suggestion")?.asString
                    ?: continue
                val ruleId = finding.get("rule")?.asString
                    ?: finding.get("rule_id")?.asString
                    ?: "NovaForge"

                if (line < 1 || line > file.viewProvider.document.lineCount) continue

                val startOffset = file.viewProvider.document.getLineStartOffset(line - 1)
                val endOffset = file.viewProvider.document.getLineEndOffset(line - 1)
                if (startOffset >= endOffset) continue

                val element = file.viewProvider.psi.findElementAt(startOffset) ?: continue
                val problemSeverity = when (severity.lowercase()) {
                    "error" -> ProblemHighlightType.GENERIC_ERROR_OR_WARNING
                    "critical" -> ProblemHighlightType.GENERIC_ERROR_OR_WARNING
                    "info" -> ProblemHighlightType.INFORMATION
                    else -> ProblemHighlightType.WARNING
                }

                problems.add(manager.createProblemDescriptor(
                    element,
                    startOffset,
                    endOffset,
                    "NovaForge [$ruleId]: $message",
                    problemSeverity,
                    isOnTheFly
                ))
            }

            return problems.toTypedArray()
        } catch (e: Exception) {
            return null
        } finally {
            reviewing.set(false)
        }
    }
}
