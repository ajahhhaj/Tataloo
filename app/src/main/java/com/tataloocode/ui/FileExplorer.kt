
package com.tataloocode.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun FileExplorer(
    files: List<String>,
    selectedFile: String,
    onFileSelected: (String) -> Unit
) {
    Column(
        modifier = Modifier
            .width(115.dp)
            .fillMaxHeight()
            .background(Color(0xFF111111))
            .verticalScroll(rememberScrollState())
            .padding(6.dp)
    ) {
        Text(
            "EXPLORER",
            color = Color(0xFFE04460),
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(6.dp)
        )

        files.forEach { file ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        if (file == selectedFile)
                            Color(0xFF302025)
                        else Color.Transparent
                    )
                    .clickable { onFileSelected(file) }
                    .padding(7.dp)
            ) {
                Icon(
                    Icons.Default.Description,
                    contentDescription = null,
                    tint = Color(0xFFE04460),
                    modifier = Modifier.size(16.dp)
                )

                Spacer(Modifier.width(5.dp))

                Text(
                    file,
                    color = Color.White,
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1
                )
            }
        }
    }
}
