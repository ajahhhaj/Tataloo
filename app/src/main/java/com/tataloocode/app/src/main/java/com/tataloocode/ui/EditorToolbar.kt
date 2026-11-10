
package com.tataloocode.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Code
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Terminal
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun EditorToolbar(
    fileName: String,
    onNew: () -> Unit,
    onSave: () -> Unit,
    onRun: () -> Unit,
    onTerminal: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF151515))
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        ToolbarButton("New", Icons.Default.Add, onNew)
        ToolbarButton("Save", Icons.Default.Save, onSave)
        ToolbarButton("Run", Icons.Default.PlayArrow, onRun)
        ToolbarButton("Terminal", Icons.Default.Terminal, onTerminal)

        Spacer(Modifier.width(8.dp))

        Text(
            text = fileName,
            color = Color(0xFFE04460),
            modifier = Modifier.padding(12.dp)
        )
    }
}

@Composable
private fun ToolbarButton(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit
) {
    TextButton(onClick = onClick) {
        Icon(
            imageVector = icon,
            contentDescription = label,
            tint = Color(0xFFE04460)
        )
        Spacer(Modifier.width(4.dp))
        Text(label, color = Color.White)
    }
}
