
package com.tataloocode

import androidx.compose.runtime.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.tataloocode.ui.EditorScreen
import com.tataloocode.ui.EditorTheme

@Composable
fun TatalooCodeApp() {
    EditorTheme {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = Color(0xFF090909)
        ) {
            EditorScreen()
        }
    }
}
