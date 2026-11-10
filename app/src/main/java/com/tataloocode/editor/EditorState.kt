
package com.tataloocode.editor

data class EditorTab(
    val id: Int,
    val name: String,
    val content: String = "",
    val modified: Boolean = false
)
