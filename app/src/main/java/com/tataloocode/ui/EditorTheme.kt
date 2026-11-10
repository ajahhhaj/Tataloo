
package com.tataloocode.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val TatalooColors = darkColorScheme(
    primary = Color(0xFFE04460),
    onPrimary = Color.White,
    secondary = Color(0xFFB51232),
    background = Color(0xFF090909),
    surface = Color(0xFF151515),
    onSurface = Color.White
)

@Composable
fun EditorTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = TatalooColors,
        content = content
    )
}
