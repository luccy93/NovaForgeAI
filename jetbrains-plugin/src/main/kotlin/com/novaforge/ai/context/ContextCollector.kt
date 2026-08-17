package com.novaforge.ai.context

import com.intellij.openapi.editor.Document
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiJavaFile
import com.intellij.psi.PsiManager
import com.intellij.psi.PsiImportList
import com.intellij.psi.PsiImportStatement

object ContextCollector {

    fun collectContext(project: Project, editor: Editor, psiFile: PsiFile?): Map<String, Any> {
        val context = mutableMapOf<String, Any>()
        val document = editor.document
        val selectionModel = editor.selectionModel

        context["project_name"] = project.name
        context["project_base_path"] = project.basePath ?: ""

        val virtualFile = FileDocumentManager.getInstance().getFile(document)
        if (virtualFile != null) {
            context["file_path"] = virtualFile.path
            context["file_name"] = virtualFile.name
            context["file_type"] = virtualFile.fileType.name
        }

        context["total_lines"] = document.lineCount

        if (selectionModel.hasSelection()) {
            val selectedText = selectionModel.selectedText
            if (!selectedText.isNullOrBlank()) {
                context["selected_code"] = selectedText
                context["selection_start_line"] = document.getLineNumber(selectionModel.selectionStart) + 1
                context["selection_end_line"] = document.getLineNumber(selectionModel.selectionEnd) + 1
            }
        }

        if (psiFile != null) {
            val imports = collectImports(psiFile)
            if (imports.isNotEmpty()) {
                context["imports"] = imports
            }
            context["language"] = psiFile.language.id
        }

        val caretOffset = editor.caretModel.offset
        val currentLine = document.getLineNumber(caretOffset) + 1
        context["cursor_line"] = currentLine
        context["cursor_offset"] = caretOffset

        val surroundingLines = 20
        val startLine = maxOf(0, currentLine - surroundingLines - 1)
        val endLine = minOf(document.lineCount, currentLine + surroundingLines)
        val startOffset = document.getLineStartOffset(startLine)
        val endOffset = document.getLineEndOffset(minOf(endLine, document.lineCount - 1))
        if (startOffset < endOffset) {
            context["surrounding_code"] = document.getText(com.intellij.openapi.util.TextRange(startOffset, endOffset))
            context["surrounding_start_line"] = startLine + 1
            context["surrounding_end_line"] = endLine
        }

        val packageName = extractPackageName(psiFile)
        if (!packageName.isNullOrBlank()) {
            context["package"] = packageName
        }

        return context
    }

    private fun collectImports(psiFile: PsiFile): List<String> {
        val imports = mutableListOf<String>()
        if (psiFile is PsiJavaFile) {
            val importList = psiFile.importList
            if (importList != null) {
                for (import in importList.importStatements) {
                    val importText = import.text?.removePrefix("import ")?.removeSuffix(";")?.trim()
                    if (!importText.isNullOrBlank()) {
                        imports.add(importText)
                    }
                }
            }
        }
        return imports
    }

    private fun extractPackageName(psiFile: PsiFile?): String? {
        if (psiFile is PsiJavaFile) {
            return psiFile.packageName
        }
        return null
    }

    fun collectFileContext(project: Project, file: VirtualFile): Map<String, Any> {
        val context = mutableMapOf<String, Any>()
        context["file_path"] = file.path
        context["file_name"] = file.name
        context["file_type"] = file.fileType.name
        context["file_size"] = file.length
        context["project_name"] = project.name
        context["project_base_path"] = project.basePath ?: ""
        return context
    }
}
