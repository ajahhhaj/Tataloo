
package com.tataloocode.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun EditorToolbar(
    fileName: String,
    onNew: () -> Unit,
    onOpen: () -> Unit,
    onSave: () -> Unit,
    onUndo: () -> Unit,
    onRedo: () -> Unit,
    onSearch: () -> Unit,
    onRun: () -> Unit,
    onTerminal: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF151515))
            .horizontalScroll(rememberScrollState())
            .padding(6.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        val actions = listOf(
            "New" to onNew,
            "Open" to onOpen,
            "Save" to onSave,
            "Undo" to onUndo,
            "Redo" to onRedo,
            "Search" to onSearch,
            "Run" to onRun,
            "Terminal" to onTerminal
        )

        actions.forEach { (label, action) ->
            TextButton(onClick = action) {
                Text(label, color = Color(0xFFE04460))
            }
        }
    }
}
