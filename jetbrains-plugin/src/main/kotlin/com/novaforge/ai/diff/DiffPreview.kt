package com.novaforge.ai.diff

import com.intellij.diff.DiffContentFactory
import com.intellij.diff.DiffManager
import com.intellij.diff.requests.SimpleDiffRequest
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import java.io.File

object DiffPreview {

    fun showDiff(project: Project, original: String, proposed: String, title: String = "NovaForge Changes") {
        val contentFactory = DiffContentFactory.getInstance()
        val originalContent = contentFactory.create(original, "Original")
        val proposedContent = contentFactory.create(proposed, "Proposed")

        val request = SimpleDiffRequest(
            title,
            originalContent,
            proposedContent,
            "Original",
            "Proposed"
        )

        DiffManager.getInstance().showDiff(project, request)
    }

    fun showFileDiff(project: Project, filePath: String, proposed: String, title: String = "NovaForge Changes") {
        val contentFactory = DiffContentFactory.getInstance()
        val virtualFile = LocalFileSystem.getInstance().findFileByPath(filePath)
        val originalContent = if (virtualFile != null) {
            contentFactory.create(virtualFile)
        } else {
            val file = File(filePath)
            val text = if (file.exists()) file.readText() else ""
            contentFactory.create(text, "Original")
        }
        val proposedContent = contentFactory.create(proposed, "Proposed")

        val request = SimpleDiffRequest(
            title,
            originalContent,
            proposedContent,
            "Original",
            "Proposed"
        )

        DiffManager.getInstance().showDiff(project, request)
    }

    fun showUnifiedDiff(project: Project, diffText: String, title: String = "NovaForge Diff") {
        val contentFactory = DiffContentFactory.getInstance()
        val originalText = extractOriginalFromDiff(diffText)
        val proposedText = extractProposedFromDiff(diffText)
        val originalContent = contentFactory.create(originalText, "Original")
        val proposedContent = contentFactory.create(proposedText, "Proposed")

        val request = SimpleDiffRequest(
            title,
            originalContent,
            proposedContent,
            "Original",
            "Proposed"
        )

        DiffManager.getInstance().showDiff(project, request)
    }

    private fun extractOriginalFromDiff(diffText: String): String {
        val lines = diffText.lines()
        val result = mutableListOf<String>()
        for (line in lines) {
            when {
                line.startsWith("@@") -> continue
                line.startsWith("---") -> continue
                line.startsWith("+++") -> continue
                line.startsWith("-") -> result.add(line.removePrefix("-"))
                line.startsWith("+") -> continue
                line.startsWith(" ") -> result.add(line.removePrefix(" "))
                line.isBlank() -> continue
                else -> result.add(line)
            }
        }
        return result.joinToString("\n")
    }

    private fun extractProposedFromDiff(diffText: String): String {
        val lines = diffText.lines()
        val result = mutableListOf<String>()
        for (line in lines) {
            when {
                line.startsWith("@@") -> continue
                line.startsWith("---") -> continue
                line.startsWith("+++") -> continue
                line.startsWith("-") -> continue
                line.startsWith("+") -> result.add(line.removePrefix("+"))
                line.startsWith(" ") -> result.add(line.removePrefix(" "))
                line.isBlank() -> continue
                else -> result.add(line)
            }
        }
        return result.joinToString("\n")
    }
}
