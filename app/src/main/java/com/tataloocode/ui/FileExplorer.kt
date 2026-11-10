
package com.tataloocode.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
            .fillMaxHeight()
            .width(145.dp)
            .background(Color(0xFF111111))
            .padding(8.dp)
    ) {
        Text(
            "EXPLORER",
            color = Color(0xFFE04460),
            modifier = Modifier.padding(8.dp)
        )

        HorizontalDivider(color = Color.DarkGray)

        LazyColumn {
            items(files) { file ->
                Text(
                    text = "  $file",
                    color = if (file == selectedFile)
                        Color(0xFFE04460) else Color.LightGray,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onFileSelected(file) }
                        .padding(vertical = 12.dp)
                )
            }
        }
    }
}
