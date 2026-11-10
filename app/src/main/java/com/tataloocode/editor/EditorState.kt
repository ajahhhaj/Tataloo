
package com.tataloocode.editor

data class EditorTab(
    val id: Int,
    val name: String,
    val content: String = "",
    val language: String = "python",
    val modified: Boolean = false
)

data class EditorState(
    val tabs: List<EditorTab> = listOf(
        EditorTab(1, "main.py", "print('Hello Tataloo Code')"),
    ),
    val selectedTabId: Int = 1,
    val sidebarVisible: Boolean = true,
    val terminalVisible: Boolean = false
) {
    val selectedTab: EditorTab?
        get() = tabs.find { it.id == selectedTabId }
}
