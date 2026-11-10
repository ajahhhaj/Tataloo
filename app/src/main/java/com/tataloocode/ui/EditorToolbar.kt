
package com.tataloocode.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
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
            .padding(8.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = fileName,
            modifier = Modifier.padding(8.dp),
            color = Color.White
        )

        Row {
            TextButton(onClick = onNew) {
                Text("NEW")
            }
            TextButton(onClick = onSave) {
                Text("SAVE")
            }
            TextButton(onClick = onRun) {
                Text("RUN", color = Color(0xFFE04460))
            }
            TextButton(onClick = onTerminal) {
                Text("TERM")
            }
        }
    }
}
